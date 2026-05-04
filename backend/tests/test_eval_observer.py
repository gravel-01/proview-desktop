import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.eval_observer import EvalObserver


class MockLLMClient:
    def __init__(self, response_delay=0.01):
        self.response_delay = response_delay
        self.call_count = 0

    def generate(self, messages, timeout=None):
        self.call_count += 1
        time.sleep(self.response_delay)
        return '{"strength": "亮点", "weakness": "不足", "note": "观察"}'


class BlockingLLMClient:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.call_count = 0

    def generate(self, messages, timeout=None):
        self.call_count += 1
        self.started.set()
        self.release.wait(timeout=5)
        return '{"strength": "晚到结果", "weakness": "不应落库", "note": "late"}'


class MockDataClient:
    def __init__(self):
        self.save_calls = []

    def save_eval_draft(self, session_id, draft):
        self.save_calls.append((session_id, draft))
        return True


class MockStructuredDataClient(MockDataClient):
    def __init__(self):
        super().__init__()
        self.turns = {
            "turn-1": {
                "turn_id": "turn-1",
                "session_id": "session-structured",
                "turn_no": 2,
                "question_text": "请讲一个性能优化案例",
                "answer_text": "我定位到接口慢，增加缓存后 P95 从 800ms 降到 180ms。",
                "status": "answered",
            }
        }
        self.turn = self.turns["turn-1"]
        self.metadata_by_turn = {}
        self.default_metadata = {
            "turn_id": "turn-1",
            "dimensions": [
                {
                    "name": "性能优化",
                    "rubric": "是否能说明瓶颈、动作和量化结果",
                    "pass_criteria": "至少说明一个瓶颈、一个优化动作、一个指标",
                },
                {
                    "name": "问题定位",
                    "rubric": "是否能给出清晰的定位路径和证据",
                    "pass_criteria": "至少说明定位步骤和关键证据",
                }
            ],
        }
        self.evaluations = []
        self.events = []
        self.status_updates = []

    def add_turn(self, turn_id, *, status="answered", answer_text="回答内容", turn_no=1):
        self.turns[turn_id] = {
            "turn_id": turn_id,
            "session_id": "session-structured",
            "turn_no": turn_no,
            "question_text": "请讲一个项目案例",
            "answer_text": answer_text,
            "status": status,
        }

    def get_interview_turn(self, turn_id):
        return self.turns.get(turn_id)

    def list_interview_turns(self, session_id):
        return sorted(self.turns.values(), key=lambda item: item["turn_no"])

    def get_question_metadata(self, turn_id):
        return self.metadata_by_turn.get(turn_id) or dict(self.default_metadata, turn_id=turn_id)

    def upsert_turn_evaluation(self, **kwargs):
        self.evaluations.append(kwargs)
        return kwargs

    def update_interview_turn_status(self, turn_id, status):
        self.status_updates.append((turn_id, status))
        self.turns[turn_id]["status"] = status
        return dict(self.turns[turn_id])

    def record_agent_event(self, session_id, event_type, **kwargs):
        self.events.append((session_id, event_type, kwargs))
        return True


class BrokenStructuredLLMClient:
    def generate(self, messages, timeout=None):
        return "not json"


class StructuredLLMClient:
    def __init__(self):
        self.call_count = 0

    def generate(self, messages, timeout=None):
        self.call_count += 1
        prompt = messages[-1]["content"]
        if "考察维度：问题定位" in prompt:
            return (
                '{"dimension":"问题定位","score":7,"pass_level":"pass",'
                '"evidence":"说明了接口慢和 P95 指标",'
                '"suggestion":"追问如何确认根因",'
                '"strength":"定位有证据","weakness":null,"note":"定位路径基本清晰"}'
            )
        return (
            '{"dimension":"性能优化","score":8,"pass_level":"pass",'
            '"evidence":"说明了接口慢、缓存和 P95 指标",'
            '"suggestion":"追问缓存一致性",'
            '"strength":"有量化结果","weakness":null,"note":"优化过程清晰"}'
        )


def make_history(turn: int):
    history = []
    for idx in range(1, turn + 1):
        history.extend([
            {"role": "assistant", "content": f"question-{idx}"},
            {"role": "user", "content": f"answer-{idx}"},
        ])
    return history


class EvalObserverTests(unittest.TestCase):
    def test_observe_async_updates_draft_and_pushes_callback(self):
        data_client = MockDataClient()
        observer = EvalObserver("session-1", MockLLMClient(), data_client=data_client)
        pushed = []
        observer.set_push_callback(pushed.append)

        accepted = observer.observe_async(make_history(1))

        self.assertTrue(accepted)
        draft = observer.shutdown(wait=True, timeout=1.0)
        self.assertEqual(draft["last_turn"], 1)
        self.assertEqual(len(draft["strengths"]), 1)
        self.assertEqual(len(data_client.save_calls), 1)
        self.assertEqual(len(pushed), 1)
        self.assertEqual(pushed[0]["type"], "eval_update")
        self.assertEqual(pushed[0]["turn"], 1)

    def test_duplicate_turn_is_deduplicated(self):
        observer = EvalObserver("session-2", MockLLMClient())

        first = observer.observe_async(make_history(1))
        second = observer.observe_async(make_history(1))

        self.assertTrue(first)
        self.assertFalse(second)

        draft = observer.shutdown(wait=True, timeout=1.0)
        self.assertEqual(draft["last_turn"], 1)
        self.assertEqual(len(draft["strengths"]), 1)

    def test_shutdown_waits_for_inflight_work_within_timeout(self):
        observer = EvalObserver("session-3", MockLLMClient(response_delay=0.05))

        observer.observe_async(make_history(1))
        draft = observer.shutdown(wait=True, timeout=1.0)

        self.assertEqual(draft["last_turn"], 1)
        self.assertEqual(len(draft["strengths"]), 1)

    def test_shutdown_freezes_observer_and_blocks_late_update(self):
        llm_client = BlockingLLMClient()
        data_client = MockDataClient()
        pushed = []
        observer = EvalObserver("session-4", llm_client, data_client=data_client)
        observer.set_push_callback(pushed.append)

        observer.observe_async(make_history(1))
        self.assertTrue(llm_client.started.wait(timeout=1.0))

        draft = observer.shutdown(wait=True, timeout=0.01)
        self.assertEqual(draft["last_turn"], 0)

        llm_client.release.set()
        time.sleep(0.05)

        frozen = observer.get_draft()
        self.assertEqual(frozen["last_turn"], 0)
        self.assertEqual(len(frozen["strengths"]), 0)
        self.assertEqual(len(data_client.save_calls), 0)
        self.assertEqual(len(pushed), 0)

    def test_shutdown_rejects_new_work(self):
        observer = EvalObserver("session-5", MockLLMClient())

        observer.shutdown(wait=False)
        accepted = observer.observe_async(make_history(1))

        self.assertFalse(accepted)
        self.assertEqual(observer.get_draft()["last_turn"], 0)

    def test_observe_async_with_turn_id_writes_structured_evaluation(self):
        data_client = MockStructuredDataClient()
        llm_client = StructuredLLMClient()
        observer = EvalObserver("session-structured", llm_client, data_client=data_client)

        accepted = observer.observe_async("turn-1")

        self.assertTrue(accepted)
        draft = observer.shutdown(wait=True, timeout=1.0)
        self.assertEqual(draft["last_turn"], 2)
        self.assertEqual(data_client.evaluations[0]["turn_id"], "turn-1")
        self.assertEqual(data_client.evaluations[0]["dimension"], "性能优化")
        self.assertEqual(data_client.evaluations[0]["score"], 8)
        self.assertEqual(data_client.evaluations[1]["dimension"], "问题定位")
        self.assertEqual(data_client.evaluations[1]["score"], 7)
        self.assertEqual(llm_client.call_count, 2)
        self.assertEqual(
            data_client.status_updates,
            [("turn-1", "evaluating"), ("turn-1", "evaluated")],
        )
        self.assertEqual(len(data_client.save_calls), 1)

    def test_observe_async_marks_turn_failed_when_all_dimensions_fail(self):
        data_client = MockStructuredDataClient()
        observer = EvalObserver("session-structured", BrokenStructuredLLMClient(), data_client=data_client)

        accepted = observer.observe_async("turn-1")

        self.assertTrue(accepted)
        draft = observer.shutdown(wait=True, timeout=1.0)
        self.assertEqual(draft["last_turn"], 0)
        self.assertEqual(data_client.evaluations, [])
        self.assertEqual(
            data_client.status_updates,
            [("turn-1", "evaluating"), ("turn-1", "evaluation_failed")],
        )
        self.assertTrue(any(event[1] == "turn_evaluation_failed" for event in data_client.events))

    def test_observe_async_does_not_evaluate_skipped_turn(self):
        data_client = MockStructuredDataClient()
        data_client.turn["status"] = "skipped"
        llm_client = StructuredLLMClient()
        observer = EvalObserver("session-structured", llm_client, data_client=data_client)

        accepted = observer.observe_async("turn-1")

        self.assertTrue(accepted)
        draft = observer.shutdown(wait=True, timeout=1.0)
        self.assertEqual(draft["last_turn"], 0)
        self.assertEqual(llm_client.call_count, 0)
        self.assertEqual(data_client.evaluations, [])
        self.assertEqual(data_client.status_updates, [])

    def test_retry_failed_turn_evaluations_submits_only_failed_answered_turns(self):
        data_client = MockStructuredDataClient()
        data_client.add_turn("turn-2", status="evaluation_failed", answer_text="补充了量化指标。", turn_no=3)
        data_client.add_turn("turn-3", status="answered", answer_text="已回答但未失败。", turn_no=4)
        data_client.add_turn("turn-4", status="evaluation_failed", answer_text="", turn_no=5)
        llm_client = StructuredLLMClient()
        observer = EvalObserver("session-structured", llm_client, data_client=data_client)

        submitted = observer.retry_failed_turn_evaluations()

        self.assertEqual(submitted, 1)
        draft = observer.shutdown(wait=True, timeout=1.0)
        self.assertEqual(draft["last_turn"], 3)
        self.assertEqual(llm_client.call_count, 2)
        self.assertEqual(
            data_client.status_updates,
            [("turn-2", "evaluating"), ("turn-2", "evaluated")],
        )
        self.assertEqual({item["turn_id"] for item in data_client.evaluations}, {"turn-2"})


if __name__ == "__main__":
    unittest.main()

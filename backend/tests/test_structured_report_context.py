import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module


class MockStructuredReportDataClient:
    def list_interview_turns(self, session_id):
        return [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "question_text": "请讲一个性能优化案例。",
                "answer_text": "我通过缓存把 P95 从 800ms 降到 180ms。",
                "status": "answered",
            }
        ]

    def list_question_metadata(self, session_id):
        return [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "dimensions": [
                    {
                        "name": "性能优化",
                        "rubric": "是否能说明瓶颈、动作和量化结果",
                        "pass_criteria": "至少说明一个瓶颈、一个优化动作、一个指标",
                    }
                ],
            }
        ]

    def list_turn_evaluations(self, session_id):
        return [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "dimension": "性能优化",
                "score": 8,
                "pass_level": "pass",
                "evidence": "说明了缓存和 P95 指标",
                "suggestion": "追问缓存一致性",
            }
        ]


class MockAgent:
    def get_chat_history(self):
        return [
            {"role": "assistant", "content": "旧内存问题"},
            {"role": "user", "content": "旧内存回答"},
        ]


class MockEndSessionDataClient(MockStructuredReportDataClient):
    def __init__(self):
        self.calls = []
        self.turns = [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "question_text": "请讲一个性能优化案例。",
                "answer_text": "我通过缓存把 P95 从 800ms 降到 180ms。",
                "status": "answered",
            },
            {
                "turn_id": "turn-2",
                "turn_no": 2,
                "question_text": "能补充优化前后的具体指标吗？",
                "answer_text": "",
                "status": "pending",
            },
        ]

    def list_interview_turns(self, session_id):
        return list(self.turns)

    def skip_pending_turns(self, session_id):
        self.calls.append("skip_pending_turns")
        skipped = 0
        for turn in self.turns:
            if turn.get("status") == "pending" and not (turn.get("answer_text") or "").strip():
                turn["status"] = "skipped"
                skipped += 1
        return skipped

    def end_session(self, session_id):
        self.calls.append("end_session")
        return True

    def save_evaluation(self, session_id, dimension, score, comment=""):
        self.calls.append("save_evaluation")
        return True

    def get_session_statistics(self, session_id):
        self.calls.append("get_session_statistics")
        return {"evaluations": []}

    def save_eval_summary(self, session_id, strengths="", weaknesses="", summary=""):
        self.calls.append("save_eval_summary")
        return True


class MockEndAgent:
    def evaluate_interview(self, draft=None):
        return {
            "evaluations": [],
            "strengths": "有量化结果",
            "weaknesses": "待继续追问",
            "summary": "整体表现可继续观察",
        }


class MockEndObserver:
    def __init__(self):
        self.calls = []

    def retry_failed_turn_evaluations(self, session_id):
        self.calls.append("retry_failed_turn_evaluations")
        return 1

    def shutdown(self, wait=False, timeout=None):
        self.calls.append("shutdown")
        return {"strengths": [], "weaknesses": [], "turn_notes": [], "last_turn": 0}


class StructuredReportContextTests(unittest.TestCase):
    def setUp(self):
        self.original_storage_available = app_module.STORAGE_AVAILABLE
        self.original_data_client = app_module.data_client
        self.original_agents = dict(app_module._agents)
        self.original_observers = dict(app_module._observers)
        app_module.STORAGE_AVAILABLE = True
        app_module.data_client = MockStructuredReportDataClient()

    def tearDown(self):
        app_module.STORAGE_AVAILABLE = self.original_storage_available
        app_module.data_client = self.original_data_client
        app_module._agents.clear()
        app_module._agents.update(self.original_agents)
        app_module._observers.clear()
        app_module._observers.update(self.original_observers)

    def test_eval_prompt_prefers_structured_turn_metadata_and_evaluations(self):
        prompt = app_module._build_eval_prompt(MockAgent(), session_id="session-1")

        self.assertIn("【结构化面试记录】", prompt)
        self.assertIn("性能优化", prompt)
        self.assertIn("P95 从 800ms 降到 180ms", prompt)
        self.assertIn("说明了缓存和 P95 指标", prompt)
        self.assertNotIn("旧内存问题", prompt)

    def test_fallback_eval_result_aggregates_turn_evaluations(self):
        result = app_module._build_fallback_eval_result_from_structured_data(
            "session-1",
            draft={"strengths": [{"turn": 1, "text": "有量化结果"}], "weaknesses": []},
        )

        self.assertEqual(result["source"], "structured_fallback")
        self.assertEqual(result["evaluations"][0]["dimension"], "性能优化")
        self.assertEqual(result["evaluations"][0]["score"], 8)
        self.assertIn("有量化结果", result["strengths"])
        self.assertEqual(result["overall_score"], 8)
        self.assertEqual(result["hire_recommendation"], "recommend")
        self.assertEqual(result["dimension_scores"][0]["dimension"], "性能优化")
        self.assertEqual(result["evidence"][0]["turn_no"], 1)

    def test_normalized_final_report_adds_evidence_schema_and_legacy_fields(self):
        result = app_module._normalize_final_eval_result(
            {
                "overall_score": 7.5,
                "hire_recommendation": "weak_recommend",
                "strengths": ["表达清楚"],
                "weaknesses": ["一致性细节不足"],
                "summary": "整体可继续观察",
            },
            session_id="session-1",
        )

        self.assertEqual(result["overall_score"], 7.5)
        self.assertEqual(result["hire_recommendation"], "weak_recommend")
        self.assertEqual(result["dimension_scores"][0]["dimension"], "性能优化")
        self.assertEqual(result["evidence"][0]["evidence"], "说明了缓存和 P95 指标")
        self.assertEqual(result["report"]["strengths"], ["表达清楚"])
        self.assertIn("表达清楚", result["strengths"])
        self.assertEqual(result["evaluations"][0]["dimension"], "性能优化")

    def test_eval_prompt_requests_new_report_schema_with_legacy_compatibility(self):
        prompt = app_module._build_eval_prompt(MockAgent(), session_id="session-1")

        self.assertIn('"overall_score"', prompt)
        self.assertIn('"hire_recommendation"', prompt)
        self.assertIn('"dimension_scores"', prompt)
        self.assertIn('"evidence"', prompt)
        self.assertIn('"next_training_plan"', prompt)
        self.assertIn('"evaluations"', prompt)

    def test_end_session_marks_unanswered_pending_turns_as_skipped_before_ending(self):
        client = MockEndSessionDataClient()
        app_module.data_client = client
        app_module._agents["session-1"] = MockEndAgent()

        with app_module.app.test_request_context("/api/end", method="POST", json={"save_history": True}):
            response = app_module.end_interview.__wrapped__(session_id="session-1")
        payload = response.get_json()

        self.assertEqual(payload["status"], "success")
        self.assertEqual(client.calls[:2], ["skip_pending_turns", "end_session"])
        self.assertFalse([turn for turn in client.turns if turn["status"] == "pending"])
        self.assertEqual(client.turns[1]["status"], "skipped")

    def test_end_session_retries_failed_turn_evaluations_before_shutdown(self):
        client = MockEndSessionDataClient()
        observer = MockEndObserver()
        app_module.data_client = client
        app_module._agents["session-1"] = MockEndAgent()
        app_module._observers["session-1"] = observer

        with app_module.app.test_request_context("/api/end", method="POST", json={"save_history": True}):
            response = app_module.end_interview.__wrapped__(session_id="session-1")
        payload = response.get_json()

        self.assertEqual(payload["status"], "success")
        self.assertEqual(observer.calls[:2], ["retry_failed_turn_evaluations", "shutdown"])


if __name__ == "__main__":
    unittest.main()

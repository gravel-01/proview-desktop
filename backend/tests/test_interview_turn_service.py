import os
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from direct_store import DirectDataStore
from services.interview_turn_service import InterviewTurnService


class InterviewTurnServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(__file__).resolve().parent / ".codex_tmp_turn_service"
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.store = DirectDataStore(
            db_url=f"sqlite:///{(self.temp_dir / 'turns.sqlite3').as_posix()}",
            upload_dir=str(self.temp_dir / "uploads"),
            secret_key="test-secret",
        )
        self.user = self.store.get_or_create_local_user("本地用户")
        self.session_id = "session-turn-service"
        self.store.create_session(
            self.session_id,
            candidate_name="求职者",
            position="后端工程师",
            interview_style="strict",
            metadata={},
            user_id=self.user["id"],
        )
        self.service = InterviewTurnService(self.store)

    def tearDown(self):
        self.store.engine.dispose()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_pairs_visible_messages_with_pending_turn(self):
        question_message = self.service.append_message(self.session_id, "assistant", "请先做自我介绍。")
        pending = self.service.create_pending_turn(
            self.session_id,
            question_message=question_message,
            question_text="请先做自我介绍。",
            question_type="opening",
        )
        answer_message = self.service.append_message(self.session_id, "user", "我是后端开发，做过网关项目。")
        answered = self.service.answer_pending_turn(
            self.session_id,
            answer_message=answer_message,
            answer_text="我是后端开发，做过网关项目。",
        )

        self.assertEqual(pending["turn_no"], 1)
        self.assertEqual(answered["turn_id"], pending["turn_id"])
        self.assertEqual(str(question_message["id"]), answered["question_message_id"])
        self.assertEqual(str(answer_message["id"]), answered["answer_message_id"])
        self.assertEqual(answered["status"], "answered")

    def test_delete_session_removes_structured_turn_data(self):
        question_message = self.service.append_message(self.session_id, "assistant", "请先做自我介绍。")
        pending = self.service.create_pending_turn(
            self.session_id,
            question_message=question_message,
            question_text="请先做自我介绍。",
            question_type="opening",
        )
        self.store.record_agent_event(self.session_id, "test_event", turn_id=pending["turn_id"])

        deleted = self.store.delete_session(self.session_id, self.user["id"])

        self.assertTrue(deleted)
        self.assertEqual(self.store.list_interview_turns(self.session_id), [])

    def test_list_agent_events_filters_and_returns_latest_payloads(self):
        self.store.record_agent_event(self.session_id, "context_compacted", payload={"context_version": 1})
        self.store.record_agent_event(self.session_id, "turn_evaluation_failed", payload={"reason": "boom"})
        self.store.record_agent_event(self.session_id, "context_compacted", payload={"context_version": 2})

        rows = self.store.list_agent_events(self.session_id, event_type="context_compacted", limit=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "context_compacted")
        self.assertEqual(rows[0]["payload"]["context_version"], 2)

    def test_skip_pending_turns_marks_only_unanswered_pending_turns(self):
        first_message = self.service.append_message(self.session_id, "assistant", "请先做自我介绍。")
        first = self.service.create_pending_turn(
            self.session_id,
            question_message=first_message,
            question_text="请先做自我介绍。",
            question_type="opening",
        )
        answer_message = self.service.append_message(self.session_id, "user", "我是后端开发。")
        self.service.answer_pending_turn(
            self.session_id,
            answer_message=answer_message,
            answer_text="我是后端开发。",
        )
        second_message = self.service.append_message(self.session_id, "assistant", "请讲一个性能优化案例。")
        second = self.service.create_pending_turn(
            self.session_id,
            question_message=second_message,
            question_text="请讲一个性能优化案例。",
            question_type="followup",
        )

        skipped_count = self.store.skip_pending_turns(self.session_id)
        turns = {turn["turn_id"]: turn for turn in self.store.list_interview_turns(self.session_id)}

        self.assertEqual(skipped_count, 1)
        self.assertEqual(turns[first["turn_id"]]["status"], "answered")
        self.assertEqual(turns[second["turn_id"]]["status"], "skipped")
        self.assertEqual(turns[second["turn_id"]]["answer_text"], "")
        self.assertFalse([turn for turn in turns.values() if turn["status"] == "pending"])

    def test_turn_evaluation_upsert_keeps_one_row_per_dimension_version(self):
        question_message = self.service.append_message(self.session_id, "assistant", "请讲一个性能优化案例。")
        pending = self.service.create_pending_turn(
            self.session_id,
            question_message=question_message,
            question_text="请讲一个性能优化案例。",
            question_type="followup",
        )
        answer_message = self.service.append_message(self.session_id, "user", "我优化了缓存命中率。")
        answered = self.service.answer_pending_turn(
            self.session_id,
            answer_message=answer_message,
            answer_text="我优化了缓存命中率。",
        )
        self.store.update_interview_turn_status(answered["turn_id"], "evaluation_failed")

        first = self.store.upsert_turn_evaluation(
            session_id=self.session_id,
            turn_id=pending["turn_id"],
            turn_no=pending["turn_no"],
            dimension="性能优化",
            score=4,
            pass_level="fail",
            evidence="第一次失败前的弱证据",
            suggestion="补充指标",
            evaluator_version="eval_observer_v1",
        )
        second = self.store.upsert_turn_evaluation(
            session_id=self.session_id,
            turn_id=pending["turn_id"],
            turn_no=pending["turn_no"],
            dimension="性能优化",
            score=8,
            pass_level="pass",
            evidence="重试后补充了缓存命中率和延迟指标",
            suggestion="继续追问一致性",
            evaluator_version="eval_observer_v1",
        )

        rows = self.store.list_turn_evaluations(self.session_id)

        self.assertEqual(first["evaluation_id"], second["evaluation_id"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["score"], 8)
        self.assertIn("重试后", rows[0]["evidence"])

    def test_evaluation_coverage_metrics_summarize_structured_turn_status(self):
        first_message = self.service.append_message(self.session_id, "assistant", "请讲一个性能优化案例。")
        first = self.service.create_pending_turn(
            self.session_id,
            question_message=first_message,
            question_text="请讲一个性能优化案例。",
            question_type="followup",
        )
        first_answer = self.service.append_message(self.session_id, "user", "我把 P95 降到了 180ms。")
        self.service.answer_pending_turn(
            self.session_id,
            answer_message=first_answer,
            answer_text="我把 P95 降到了 180ms。",
        )
        self.store.upsert_turn_evaluation(
            session_id=self.session_id,
            turn_id=first["turn_id"],
            turn_no=first["turn_no"],
            dimension="性能优化",
            score=8,
            pass_level="pass",
            evidence="有 P95 指标",
            suggestion="追问一致性",
        )
        self.store.update_interview_turn_status(first["turn_id"], "evaluated")

        second_message = self.service.append_message(self.session_id, "assistant", "请讲一个排障案例。")
        second = self.service.create_pending_turn(
            self.session_id,
            question_message=second_message,
            question_text="请讲一个排障案例。",
            question_type="followup",
        )
        second_answer = self.service.append_message(self.session_id, "user", "我排查过网关超时。")
        self.service.answer_pending_turn(
            self.session_id,
            answer_message=second_answer,
            answer_text="我排查过网关超时。",
        )
        self.store.update_interview_turn_status(second["turn_id"], "evaluation_failed")
        self.store.record_agent_event(
            self.session_id,
            "turn_evaluation_failed",
            turn_id=second["turn_id"],
            agent_role="evaluator",
            payload={"reason": "json_parse_failed"},
        )

        third_message = self.service.append_message(self.session_id, "assistant", "可以补充一下指标吗？")
        self.service.create_pending_turn(
            self.session_id,
            question_message=third_message,
            question_text="可以补充一下指标吗？",
            question_type="followup",
        )
        self.store.skip_pending_turns(self.session_id)

        metrics = self.store.get_evaluation_coverage_metrics(hours=24, limit=10)
        summary = metrics["summary"]
        session = metrics["sessions"][0]

        self.assertEqual(summary["session_count"], 1)
        self.assertEqual(summary["turn_count"], 3)
        self.assertEqual(summary["answered_turn_count"], 2)
        self.assertEqual(summary["evaluated_turn_count"], 1)
        self.assertEqual(summary["failed_evaluation_count"], 1)
        self.assertEqual(summary["skipped_turn_count"], 1)
        self.assertEqual(summary["turn_evaluation_count"], 1)
        self.assertEqual(summary["evaluation_failure_event_count"], 1)
        self.assertEqual(summary["coverage_rate"], 0.5)
        self.assertEqual(summary["failure_rate"], 0.5)
        self.assertEqual(session["status_counts"]["skipped"], 1)

    def test_question_metadata_uses_keyword_inference(self):
        question_message = self.service.append_message(self.session_id, "assistant", "请讲一个性能优化案例。")
        pending = self.service.create_pending_turn(
            self.session_id,
            question_message=question_message,
            question_text="请讲一个性能优化案例，说明瓶颈、优化动作和量化结果。",
            question_type="followup",
            difficulty="mid",
        )

        metadata = self.store.get_question_metadata(pending["turn_id"])

        self.assertEqual(metadata["difficulty"], "mid")
        self.assertEqual(metadata["question_type"], "followup")
        self.assertEqual(metadata["dimensions"][0]["name"], "性能优化")
        self.assertIn("量化", metadata["dimensions"][0]["rubric"])

    def test_followup_metadata_inherits_previous_dimension(self):
        first_message = self.service.append_message(self.session_id, "assistant", "请讲一个性能优化案例。")
        first = self.service.create_pending_turn(
            self.session_id,
            question_message=first_message,
            question_text="请讲一个性能优化案例，说明瓶颈和优化结果。",
            question_type="followup",
        )
        answer_message = self.service.append_message(self.session_id, "user", "我通过缓存优化了接口。")
        self.service.answer_pending_turn(
            self.session_id,
            answer_message=answer_message,
            answer_text="我通过缓存优化了接口。",
        )
        second_message = self.service.append_message(self.session_id, "assistant", "可以再具体展开一下吗？")
        second = self.service.create_pending_turn(
            self.session_id,
            question_message=second_message,
            question_text="可以再具体展开一下吗？",
            question_type="followup",
        )

        first_metadata = self.store.get_question_metadata(first["turn_id"])
        second_metadata = self.store.get_question_metadata(second["turn_id"])

        self.assertEqual(first_metadata["dimensions"][0]["name"], "性能优化")
        self.assertEqual(second_metadata["dimensions"][0]["name"], "性能优化")
        self.assertEqual(second_metadata["source"], "followup")

    def test_question_metadata_prefers_matching_rag_candidate(self):
        question_message = self.service.append_message(self.session_id, "assistant", "你会如何设计高并发订单系统？")
        pending = self.service.create_pending_turn(
            self.session_id,
            question_message=question_message,
            question_text="你会如何设计高并发订单系统，并处理一致性问题？",
            question_type="system_design",
            source="interviewer_llm",
            rag_candidates=[
                {
                    "id": "rag-question-1",
                    "document": "高并发订单系统设计 一致性 限流 降级",
                    "metadata": {
                        "dimension": "系统设计",
                        "rubric_5": "能完整拆解系统边界、数据流、一致性和降级策略。",
                        "rubric_3": "能说明核心模块和至少一个关键取舍。",
                        "rubric_1": "只能泛泛描述技术名词。",
                    },
                }
            ],
        )

        metadata = self.store.get_question_metadata(pending["turn_id"])

        self.assertEqual(metadata["dimensions"][0]["name"], "系统设计")
        self.assertEqual(metadata["dimensions"][0]["rubric"], "能完整拆解系统边界、数据流、一致性和降级策略。")
        self.assertEqual(metadata["dimensions"][0]["pass_criteria"], "能说明核心模块和至少一个关键取舍。")
        self.assertEqual(metadata["source"], "rag")
        self.assertEqual(metadata["metadata_refs"][0]["id"], "rag-question-1")

    def test_opening_question_ignores_rag_candidates(self):
        question_message = self.service.append_message(self.session_id, "assistant", "请先做自我介绍。")
        pending = self.service.create_pending_turn(
            self.session_id,
            question_message=question_message,
            question_text="请先做自我介绍。",
            question_type="opening",
            rag_candidates=[
                {
                    "id": "rag-question-2",
                    "document": "自我介绍后追问高并发系统设计",
                    "metadata": {"dimension": "系统设计", "rubric_5": "系统设计优秀标准"},
                }
            ],
        )

        metadata = self.store.get_question_metadata(pending["turn_id"])

        self.assertEqual(metadata["question_type"], "opening")
        self.assertNotEqual(metadata["dimensions"][0]["name"], "系统设计")
        self.assertEqual(metadata["metadata_refs"], [])


if __name__ == "__main__":
    unittest.main()

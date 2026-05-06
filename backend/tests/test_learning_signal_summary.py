import os
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask

from direct_store import DirectDataStore
from learning.routes import learning_bp, set_data_client_provider


class MockLearningClient:
    def __init__(self, metrics=None):
        self.calls = []
        self.metrics = metrics or {
            "status": "ok",
            "summary": {
                "session_count": 1,
                "evaluation_count": 2,
            },
            "dimensions": [],
            "alerts": [],
        }

    def get_learning_signal_summary_metrics(self, *, hours=None, limit=None):
        self.calls.append({"hours": hours, "limit": limit})
        return self.metrics


class MockLearningLLMClient:
    def __init__(self, raw):
        self.raw = raw
        self.calls = []

    def generate(self, messages, timeout=None):
        self.calls.append({"messages": messages, "timeout": timeout})
        return self.raw


class LearningSignalSummaryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(__file__).resolve().parent / ".codex_tmp_learning"
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.store = DirectDataStore(
            db_url=f"sqlite:///{(self.temp_dir / 'learning.sqlite3').as_posix()}",
            upload_dir=str(self.temp_dir / "uploads"),
            secret_key="test-secret",
        )
        self.session_id = "session-learning"
        self.store.create_session(
            self.session_id,
            candidate_name="hidden candidate name should not be returned",
            position="hidden position should not be returned",
            interview_style="strict",
            metadata={"resume_summary": "hidden resume summary"},
        )
        self._learning_env_keys = [
            "PROVIEW_LEARNING_LLM_ENABLED",
            "PROVIEW_LEARNING_LLM_TIMEOUT_SECONDS",
            "PROVIEW_LEARNING_LLM_MODEL",
            "PROVIEW_LEARNING_LLM_API_KEY",
            "PROVIEW_LEARNING_LLM_BASE_URL",
        ]
        self._learning_env = {
            key: os.environ.get(key)
            for key in self._learning_env_keys
        }
        for key in self._learning_env_keys:
            os.environ.pop(key, None)

    def tearDown(self):
        set_data_client_provider(None)
        for key, value in self._learning_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.store.engine.dispose()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_direct_store_learning_signal_summary_aggregates_safe_categories(self):
        first = self.store.create_interview_turn(
            session_id=self.session_id,
            turn_id="turn-low",
            turn_no=1,
            question_text="hidden question text should not be returned",
        )
        self.store.save_question_metadata(
            session_id=self.session_id,
            turn_id=first["turn_id"],
            turn_no=1,
            question_text="hidden question metadata text should not be returned",
            dimensions=[
                {
                    "name": "系统设计",
                    "rubric": "hidden rubric should not be returned",
                    "pass_criteria": "hidden pass criteria should not be returned",
                }
            ],
            question_type="system_design",
            source="rag",
            metadata_refs=[{"document": "hidden RAG document should not be returned"}],
        )
        self.store.answer_interview_turn(
            first["turn_id"],
            answer_text="hidden low score answer should not be returned",
        )
        self.store.upsert_turn_evaluation(
            session_id=self.session_id,
            turn_id=first["turn_id"],
            turn_no=1,
            dimension="系统设计",
            score=4,
            pass_level="fail",
            evidence="",
            suggestion="hidden suggestion should not be returned",
        )

        second = self.store.create_interview_turn(
            session_id=self.session_id,
            turn_id="turn-pass",
            turn_no=2,
            question_text="another hidden question should not be returned",
        )
        self.store.save_question_metadata(
            session_id=self.session_id,
            turn_id=second["turn_id"],
            turn_no=2,
            question_text="another hidden metadata text should not be returned",
            dimensions=[{"name": "性能优化", "rubric": "hidden performance rubric"}],
            question_type="followup",
            source="interviewer_llm",
        )
        self.store.answer_interview_turn(
            second["turn_id"],
            answer_text="hidden strong answer should not be returned",
        )
        self.store.upsert_turn_evaluation(
            session_id=self.session_id,
            turn_id=second["turn_id"],
            turn_no=2,
            dimension="性能优化",
            score=8,
            pass_level="pass",
            evidence="hidden evidence raw text should not be returned but is long enough",
            suggestion="",
        )

        self.store.record_agent_event(
            self.session_id,
            "turn_evaluation_failed",
            turn_id=first["turn_id"],
            agent_role="evaluator",
            payload={"candidate_answer": "hidden answer in event", "reason": "json_parse_failed"},
        )
        self.store.record_agent_event(
            self.session_id,
            "rag_retrieval_missed",
            agent_role="rag",
            payload={"stage": "opening", "status": "missed", "query": "hidden query"},
        )
        self.store.record_agent_event(
            self.session_id,
            "rag_retrieval_failed",
            agent_role="rag",
            payload={"stage": "opening", "status": "failed", "error_type": "RuntimeError"},
        )
        self.store.record_agent_event(
            self.session_id,
            "final_report_generation_failed",
            agent_role="reporter",
            payload={"route": "end", "reason": "RuntimeError", "raw_report": "hidden report"},
        )
        self.store.record_agent_event(
            self.session_id,
            "final_report_generation_succeeded",
            agent_role="reporter",
            payload={"route": "end", "source": "structured_fallback", "fallback_used": True},
        )

        metrics = self.store.get_learning_signal_summary_metrics(hours=24, limit=20)
        summary = metrics["summary"]
        metrics_text = str(metrics)
        dimensions = {item["dimension"]: item for item in metrics["dimensions"]}
        question_types = {item["question_type"]: item for item in metrics["question_types"]}
        question_sources = {item["source"]: item for item in metrics["question_sources"]}
        alert_codes = {item["code"] for item in metrics["alerts"]}

        self.assertEqual(metrics["status"], "degraded")
        self.assertEqual(summary["session_count"], 1)
        self.assertEqual(summary["turn_count"], 2)
        self.assertEqual(summary["question_metadata_count"], 2)
        self.assertEqual(summary["evaluation_count"], 2)
        self.assertEqual(summary["low_score_count"], 1)
        self.assertEqual(summary["low_score_rate"], 0.5)
        self.assertEqual(summary["evidence_missing_or_short_count"], 1)
        self.assertEqual(summary["suggestion_present_count"], 1)
        self.assertEqual(summary["rag_miss_count"], 1)
        self.assertEqual(summary["rag_failure_count"], 1)
        self.assertEqual(summary["report_failure_count"], 1)
        self.assertEqual(summary["report_fallback_success_count"], 1)
        self.assertGreaterEqual(summary["agent_failure_event_count"], 1)
        self.assertEqual(dimensions["系统设计"]["average_score"], 4.0)
        self.assertEqual(dimensions["系统设计"]["low_score_count"], 1)
        self.assertEqual(dimensions["系统设计"]["evidence_missing_or_short_count"], 1)
        self.assertEqual(dimensions["性能优化"]["average_score"], 8.0)
        self.assertEqual(question_types["system_design"]["question_count"], 1)
        self.assertEqual(question_sources["rag"]["question_count"], 1)
        self.assertEqual(metrics["rag_retrieval"]["summary"]["failure_count"], 1)
        self.assertEqual(metrics["report_generation"]["summary"]["fallback_success_count"], 1)
        self.assertTrue(metrics["agent_failures"]["failure_event_types"])
        self.assertIn("learning_low_score_rate_high", alert_codes)
        self.assertIn("learning_rag_failures_present", alert_codes)

        for forbidden in (
            "hidden candidate name",
            "hidden position",
            "hidden resume summary",
            "hidden question",
            "hidden question metadata text",
            "hidden rubric",
            "hidden pass criteria",
            "hidden low score answer",
            "hidden strong answer",
            "hidden suggestion",
            "hidden evidence raw text",
            "hidden answer in event",
            "hidden query",
            "hidden RAG document",
            "hidden report",
            "raw_report",
            "candidate_answer",
            "query",
        ):
            self.assertNotIn(forbidden, metrics_text)

    def test_learning_signal_route_returns_database_metrics(self):
        app = Flask(__name__)
        app.register_blueprint(learning_bp)
        client = app.test_client()
        learning_client = MockLearningClient()
        set_data_client_provider(lambda: learning_client)

        response = client.get("/api/learning/signal-summary?hours=12&limit=7")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "learning_signals")
        self.assertEqual(payload["data"]["summary"]["session_count"], 1)
        self.assertEqual(learning_client.calls, [{"hours": 12, "limit": 7}])

    def test_learning_signal_route_handles_missing_data_client(self):
        app = Flask(__name__)
        app.register_blueprint(learning_bp)
        client = app.test_client()
        set_data_client_provider(lambda: None)

        response = client.get("/api/learning/signal-summary")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "learning_signals")
        self.assertIsNone(payload["data"])

    def test_learning_suggestions_default_off_returns_deterministic_fallback_without_hidden_fields(self):
        metrics = {
            "status": "degraded",
            "summary": {
                "session_count": 1,
                "evaluation_count": 2,
                "low_score_count": 1,
                "low_score_rate": 0.5,
                "evidence_missing_or_short_rate": 0.5,
                "rag_success_count": 1,
                "rag_miss_count": 3,
                "rag_failure_count": 0,
                "report_failure_count": 0,
                "report_fallback_success_count": 1,
                "agent_failure_event_count": 1,
            },
            "dimensions": [
                {
                    "dimension": "系统设计",
                    "low_score_count": 1,
                    "evidence_missing_or_short_count": 1,
                    "hidden_evidence": "secret evidence should not be returned",
                }
            ],
            "question_types": [
                {
                    "question_type": "system_design",
                    "low_score_count": 1,
                    "hidden_question": "secret question should not be returned",
                }
            ],
            "rag_retrieval": {
                "summary": {"success_count": 1, "miss_count": 3, "failure_count": 0},
                "error_types": [],
            },
            "report_generation": {
                "summary": {"success_count": 1, "failure_count": 0, "fallback_success_count": 1},
                "failure_reasons": [],
            },
            "agent_failures": {
                "summary": {"failure_event_count": 1},
                "failure_event_types": [
                    {
                        "event_type": "turn_evaluation_failed",
                        "count": 1,
                        "raw_payload": "hidden payload should not be returned",
                    }
                ],
            },
            "alerts": [
                {
                    "code": "learning_low_score_rate_high",
                    "severity": "warning",
                    "message": "Low-score evaluations are common in the selected learning window.",
                    "hidden_answer": "secret answer should not be returned",
                },
                {
                    "code": "learning_rag_misses_exceed_hits",
                    "severity": "warning",
                    "message": "RAG misses exceed successful retrievals in the selected window.",
                },
                {
                    "code": "learning_report_fallbacks_present",
                    "severity": "info",
                    "message": "Fallback final reports were used and may warrant quality review.",
                },
            ],
        }
        app = Flask(__name__)
        app.register_blueprint(learning_bp)
        client = app.test_client()
        learning_client = MockLearningClient(metrics)
        set_data_client_provider(lambda: learning_client)

        response = client.get("/api/learning/suggestions?hours=12&limit=7")
        payload = response.get_json()
        payload_text = str(payload)
        areas = {item["area"] for item in payload["data"]["suggestions"]}

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "learning_suggestions")
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertTrue(payload["data"]["fallback_used"])
        self.assertIn("question_quality", areas)
        self.assertIn("rag_coverage", areas)
        self.assertIn("report_generation", areas)
        self.assertTrue(all(item["requires_human_review"] for item in payload["data"]["suggestions"]))
        self.assertEqual(learning_client.calls, [{"hours": 12, "limit": 7}])
        self.assertIn("deterministic fallback", payload["message"])
        for forbidden in (
            "secret evidence",
            "secret question",
            "hidden payload",
            "secret answer",
            "hidden_answer",
            "hidden_evidence",
            "hidden_question",
            "raw_payload",
        ):
            self.assertNotIn(forbidden, payload_text)

    def test_learning_suggestions_uses_llm_when_enabled_and_configured(self):
        os.environ["PROVIEW_LEARNING_LLM_ENABLED"] = "1"
        os.environ["PROVIEW_LEARNING_LLM_TIMEOUT_SECONDS"] = "0.5"
        metrics = {
            "status": "degraded",
            "summary": {
                "session_count": 1,
                "evaluation_count": 2,
                "rag_success_count": 1,
                "rag_miss_count": 3,
            },
            "dimensions": [
                {
                    "dimension": "系统设计",
                    "low_score_count": 1,
                    "candidate_answer": "secret answer should not enter prompt",
                }
            ],
            "question_types": [],
            "rag_retrieval": {
                "summary": {"success_count": 1, "miss_count": 3, "failure_count": 0},
                "stages": [{"stage": "opening", "count": 4, "query": "secret query should not enter prompt"}],
            },
            "report_generation": {"summary": {"success_count": 1, "failure_count": 0}},
            "agent_failures": {"summary": {"failure_event_count": 0}},
            "alerts": [
                {
                    "code": "learning_rag_misses_exceed_hits",
                    "severity": "warning",
                    "message": "RAG misses exceed hits.",
                    "raw_payload": "hidden payload should not enter prompt",
                }
            ],
        }
        llm_payload = {
            "status": "degraded",
            "suggestions": [
                {
                    "area": "rag_coverage",
                    "severity": "warning",
                    "summary": "RAG misses exceed hits in the aggregate window.",
                    "candidate_improvement": "Review title aliases and question-bank tags offline.",
                    "requires_human_review": False,
                }
            ],
            "fallback_used": False,
        }
        llm_client = MockLearningLLMClient(json.dumps(llm_payload))
        app = Flask(__name__)
        app.register_blueprint(learning_bp)
        client = app.test_client()
        set_data_client_provider(lambda: MockLearningClient(metrics))

        with patch(
            "learning.routes._build_learning_llm_client",
            return_value=(llm_client, ""),
        ):
            response = client.get("/api/learning/suggestions")

        payload = response.get_json()
        prompt_text = str(llm_client.calls)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "learning_suggestions")
        self.assertFalse(payload["data"]["fallback_used"])
        self.assertEqual(payload["data"]["suggestions"][0]["area"], "rag_coverage")
        self.assertTrue(payload["data"]["suggestions"][0]["requires_human_review"])
        self.assertEqual(llm_client.calls[0]["timeout"], 0.5)
        self.assertIn("aggregate summary", prompt_text.lower())
        for forbidden in (
            "secret answer",
            "secret query",
            "hidden payload",
            "candidate_answer",
            "raw_payload",
        ):
            self.assertNotIn(forbidden, prompt_text)

    def test_learning_suggestions_falls_back_when_llm_output_is_invalid(self):
        os.environ["PROVIEW_LEARNING_LLM_ENABLED"] = "1"
        metrics = {
            "status": "degraded",
            "summary": {
                "session_count": 1,
                "evaluation_count": 2,
                "report_failure_count": 2,
            },
            "dimensions": [],
            "question_types": [],
            "rag_retrieval": {"summary": {}},
            "report_generation": {
                "summary": {"success_count": 0, "failure_count": 2},
                "failure_reasons": [{"reason": "RuntimeError", "count": 2}],
            },
            "agent_failures": {"summary": {}},
            "alerts": [
                {
                    "code": "learning_report_failures_present",
                    "severity": "warning",
                    "message": "Final report generation failures are present.",
                }
            ],
        }
        app = Flask(__name__)
        app.register_blueprint(learning_bp)
        client = app.test_client()
        set_data_client_provider(lambda: MockLearningClient(metrics))

        with patch(
            "learning.routes._build_learning_llm_client",
            return_value=(MockLearningLLMClient("not json"), ""),
        ):
            response = client.get("/api/learning/suggestions")

        payload = response.get_json()
        areas = {item["area"] for item in payload["data"]["suggestions"]}

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertTrue(payload["data"]["fallback_used"])
        self.assertIn("report_generation", areas)
        self.assertIn("invalid JSON", payload["message"])


if __name__ == "__main__":
    unittest.main()

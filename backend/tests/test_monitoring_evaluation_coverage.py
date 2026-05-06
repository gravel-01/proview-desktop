import json
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monitoring.routes import monitoring_bp, set_data_client_provider

from flask import Flask


class MockLangfuseStatus:
    def __init__(self, configured=False, available=False, message=""):
        self.configured = configured
        self.available = available
        self.message = message


class MockLangfuseClient:
    status_value = MockLangfuseStatus(
        configured=False,
        available=False,
        message="Monitoring is disabled",
    )

    def status(self):
        return self.status_value


class MockCoverageClient:
    def __init__(self):
        self.calls = []

    def get_evaluation_coverage_metrics(self, *, hours=None, limit=None):
        self.calls.append({"hours": hours, "limit": limit})
        return {
            "summary": {
                "session_count": 1,
                "turn_count": 2,
                "answered_turn_count": 2,
                "evaluated_turn_count": 1,
                "failed_evaluation_count": 1,
                "skipped_turn_count": 0,
                "pending_turn_count": 0,
                "turn_evaluation_count": 1,
                "evaluation_failure_event_count": 1,
                "coverage_rate": 0.5,
                "failure_rate": 0.5,
                "pending_rate": 0.0,
            },
            "sessions": [],
        }


class MockHealthClient:
    def __init__(
        self,
        *,
        coverage_rate=1.0,
        failure_rate=0.0,
        answered_turn_count=3,
        failure_event_count=0,
        compacted_event_count=1,
        summary_failure_event_count=0,
        latest_context_version=2,
        agent_event_failure_count=0,
        report_success_count=1,
        report_failure_count=0,
        report_fallback_success_count=0,
        rag_success_count=1,
        rag_miss_count=0,
        rag_failure_count=0,
    ):
        self.calls = []
        self.coverage_rate = coverage_rate
        self.failure_rate = failure_rate
        self.answered_turn_count = answered_turn_count
        self.failure_event_count = failure_event_count
        self.compacted_event_count = compacted_event_count
        self.summary_failure_event_count = summary_failure_event_count
        self.latest_context_version = latest_context_version
        self.agent_event_failure_count = agent_event_failure_count
        self.report_success_count = report_success_count
        self.report_failure_count = report_failure_count
        self.report_fallback_success_count = report_fallback_success_count
        self.rag_success_count = rag_success_count
        self.rag_miss_count = rag_miss_count
        self.rag_failure_count = rag_failure_count

    def get_evaluation_coverage_metrics(self, *, hours=None, limit=None):
        self.calls.append(("evaluation", {"hours": hours, "limit": limit}))
        return {
            "summary": {
                "answered_turn_count": self.answered_turn_count,
                "coverage_rate": self.coverage_rate,
                "failure_rate": self.failure_rate,
                "evaluation_failure_event_count": self.failure_event_count,
            },
            "sessions": [
                {
                    "session_id": "session-1",
                    "candidate_answer": "secret answer",
                    "evidence": "hidden evidence",
                    "suggestion": "hidden suggestion",
                }
            ],
        }

    def get_context_compaction_metrics(self, *, hours=None, limit=None):
        self.calls.append(("context", {"hours": hours, "limit": limit}))
        return {
            "summary": {
                "context_compacted_event_count": self.compacted_event_count,
                "context_summary_failure_event_count": self.summary_failure_event_count,
                "latest_context_version": self.latest_context_version,
            },
            "sessions": [
                {
                    "session_id": "session-1",
                    "recent_turns": ["hidden recent turn"],
                    "candidate_facts": ["hidden fact"],
                    "risk_signals": ["hidden risk"],
                    "open_threads": ["hidden thread"],
                    "checkpoint_payload": {"hidden_memory_card": "secret"},
                }
            ],
        }

    def get_agent_event_rollup_metrics(self, *, hours=None, limit=None):
        self.calls.append(("agent_events", {"hours": hours, "limit": limit}))
        return {
            "summary": {
                "total_event_count": 4,
                "failure_event_count": self.agent_event_failure_count,
            },
            "failure_event_types": [
                {
                    "event_type": "turn_evaluation_failed",
                    "count": self.agent_event_failure_count,
                    "latest_created_at": "2026-05-05T00:00:00",
                    "raw_payload": "hidden payload should not be returned",
                }
            ] if self.agent_event_failure_count else [],
            "event_type_agent_role_rollups": [
                {
                    "event_type": "turn_evaluation_failed",
                    "agent_role": "evaluator",
                    "count": self.agent_event_failure_count,
                    "checkpoint_payload": "hidden checkpoint should not be returned",
                }
            ],
        }

    def get_report_generation_metrics(self, *, hours=None, limit=None):
        self.calls.append(("report_generation", {"hours": hours, "limit": limit}))
        total = self.report_success_count + self.report_failure_count
        return {
            "summary": {
                "success_count": self.report_success_count,
                "failure_count": self.report_failure_count,
                "fallback_success_count": self.report_fallback_success_count,
                "success_rate": round(self.report_success_count / total, 4) if total else None,
            },
            "failure_reasons": [
                {
                    "reason": "RuntimeError",
                    "count": self.report_failure_count,
                    "latest_created_at": "2026-05-05T00:00:00",
                    "raw_report": "hidden report should not be returned",
                }
            ] if self.report_failure_count else [],
        }

    def get_rag_retrieval_metrics(self, *, hours=None, limit=None):
        self.calls.append(("rag_retrieval", {"hours": hours, "limit": limit}))
        total = self.rag_success_count + self.rag_miss_count + self.rag_failure_count
        return {
            "summary": {
                "total_event_count": total,
                "success_count": self.rag_success_count,
                "miss_count": self.rag_miss_count,
                "failure_count": self.rag_failure_count,
                "hit_rate": round(self.rag_success_count / total, 4) if total else None,
                "miss_rate": round(self.rag_miss_count / total, 4) if total else None,
                "failure_rate": round(self.rag_failure_count / total, 4) if total else None,
                "jobs_count": 1 if self.rag_success_count else 0,
                "questions_count": 2 if self.rag_success_count else 0,
                "scripts_count": 1 if self.rag_success_count else 0,
            },
            "error_types": [
                {
                    "error_type": "RuntimeError",
                    "count": self.rag_failure_count,
                    "latest_created_at": "2026-05-05T00:00:00",
                    "query": "hidden query should not be returned",
                    "resume_text": "hidden resume should not be returned",
                    "document": "hidden RAG document should not be returned",
                }
            ] if self.rag_failure_count else [],
        }


class MockContextCompactionClient:
    def __init__(self):
        self.calls = []

    def get_context_compaction_metrics(self, *, hours=None, limit=None):
        self.calls.append({"hours": hours, "limit": limit})
        return {
            "summary": {
                "session_count": 1,
                "compacted_session_count": 1,
                "context_compacted_event_count": 2,
                "context_summary_failure_event_count": 1,
                "latest_context_version": 3,
                "max_context_version": 3,
                "latest_compacted_at": "2026-05-05T00:00:00",
                "summary_failure_rate": 0.3333,
            },
            "sessions": [
                {
                    "session_id": "session-1",
                    "candidate_name": "求职者",
                    "position": "后端工程师",
                    "status": "active",
                    "latest_context_version": 3,
                    "last_turn_no": 8,
                    "estimated_tokens": 6200,
                    "threshold_tokens": 4800,
                    "open_thread_count": 2,
                    "context_compacted_event_count": 2,
                    "context_summary_failure_event_count": 1,
                    "has_context_checkpoint": True,
                }
            ],
            "failure_reasons": [{"reason": "timeout", "count": 1}],
        }


class MockAgentEventRollupClient:
    def __init__(self):
        self.calls = []

    def get_agent_event_rollup_metrics(self, *, hours=None, limit=None):
        self.calls.append({"hours": hours, "limit": limit})
        return {
            "summary": {
                "total_event_count": 3,
                "failure_event_count": 2,
                "distinct_session_count": 1,
                "event_type_count": 3,
                "agent_role_count": 2,
                "latest_event_at": "2026-05-05T00:00:00",
            },
            "event_types": [
                {
                    "event_type": "turn_evaluation_failed",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                    "failure": True,
                }
            ],
            "agent_roles": [
                {
                    "agent_role": "evaluator",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                }
            ],
            "failure_event_types": [
                {
                    "event_type": "turn_evaluation_failed",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                },
                {
                    "event_type": "context_summary_failed",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                },
            ],
            "event_type_agent_role_rollups": [
                {
                    "event_type": "turn_evaluation_failed",
                    "agent_role": "evaluator",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                    "failure": True,
                }
            ],
        }


class MockReportGenerationClient:
    def __init__(self):
        self.calls = []

    def get_report_generation_metrics(self, *, hours=None, limit=None):
        self.calls.append({"hours": hours, "limit": limit})
        return {
            "summary": {
                "total_event_count": 3,
                "success_count": 2,
                "failure_count": 1,
                "fallback_success_count": 1,
                "success_rate": 0.6667,
                "latest_report_event_at": "2026-05-05T00:00:00",
                "latest_success_at": "2026-05-05T00:00:00",
                "latest_failure_at": "2026-05-05T00:00:00",
            },
            "sources": [
                {
                    "source": "structured_fallback",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                }
            ],
            "failure_reasons": [
                {
                    "reason": "RuntimeError",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                }
            ],
            "routes": [
                {
                    "route": "end",
                    "count": 3,
                    "latest_created_at": "2026-05-05T00:00:00",
                }
            ],
        }


class MockRagRetrievalClient:
    def __init__(self):
        self.calls = []

    def get_rag_retrieval_metrics(self, *, hours=None, limit=None):
        self.calls.append({"hours": hours, "limit": limit})
        return {
            "summary": {
                "total_event_count": 3,
                "success_count": 1,
                "miss_count": 1,
                "failure_count": 1,
                "hit_rate": 0.3333,
                "miss_rate": 0.3333,
                "failure_rate": 0.3333,
                "latest_retrieval_at": "2026-05-05T00:00:00",
                "latest_success_at": "2026-05-05T00:00:00",
                "latest_miss_at": "2026-05-05T00:00:00",
                "latest_failure_at": "2026-05-05T00:00:00",
                "job_title_matched_count": 1,
                "title_candidate_count": 3,
                "title_candidates_examined_count": 3,
                "jobs_count": 1,
                "questions_count": 5,
                "scripts_count": 2,
            },
            "stages": [
                {
                    "stage": "opening",
                    "count": 3,
                    "latest_created_at": "2026-05-05T00:00:00",
                }
            ],
            "statuses": [
                {
                    "status": "succeeded",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                }
            ],
            "error_types": [
                {
                    "error_type": "RuntimeError",
                    "count": 1,
                    "latest_created_at": "2026-05-05T00:00:00",
                }
            ],
        }


class MockDiagnosticLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, messages, timeout=None):
        self.calls.append({"messages": messages, "timeout": timeout})
        return self.response


class MonitoringEvaluationCoverageRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(monitoring_bp)
        self.client = self.app.test_client()
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=False,
            available=False,
            message="Monitoring is disabled",
        )
        self._diagnostic_env_keys = [
            "PROVIEW_MONITORING_DIAGNOSTIC_LLM_ENABLED",
            "PROVIEW_MONITORING_DIAGNOSTIC_LLM_TIMEOUT_SECONDS",
            "PROVIEW_MONITORING_DIAGNOSTIC_LLM_MODEL",
            "PROVIEW_MONITORING_DIAGNOSTIC_LLM_API_KEY",
            "PROVIEW_MONITORING_DIAGNOSTIC_LLM_BASE_URL",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
        ]
        self._diagnostic_env = {
            key: os.environ.get(key)
            for key in self._diagnostic_env_keys
        }
        for key in self._diagnostic_env_keys:
            os.environ.pop(key, None)

    def tearDown(self):
        set_data_client_provider(None)
        for key, value in self._diagnostic_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_evaluation_coverage_route_returns_database_metrics(self):
        coverage_client = MockCoverageClient()
        set_data_client_provider(lambda: coverage_client)

        response = self.client.get("/api/monitoring/evaluation-coverage?hours=12&limit=5")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertEqual(payload["data"]["summary"]["coverage_rate"], 0.5)
        self.assertEqual(coverage_client.calls, [{"hours": 12, "limit": 5}])

    def test_evaluation_coverage_route_handles_missing_data_client(self):
        set_data_client_provider(lambda: None)

        response = self.client.get("/api/monitoring/evaluation-coverage")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertIsNone(payload["data"])

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_returns_ok_without_hidden_fields(self):
        health_client = MockHealthClient()
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/health-summary?hours=8&limit=4")
        payload = response.get_json()
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "monitoring_health")
        self.assertEqual(payload["data"]["status"], "ok")
        self.assertEqual(payload["data"]["evaluation"]["coverage_rate"], 1.0)
        self.assertEqual(payload["data"]["evaluation"]["failure_rate"], 0.0)
        self.assertEqual(
            payload["data"]["context_compaction"]["context_compacted_event_count"],
            1,
        )
        self.assertEqual(payload["data"]["rag_retrieval"]["success_count"], 1)
        self.assertEqual(payload["data"]["rag_retrieval"]["questions_count"], 2)
        self.assertEqual(payload["data"]["alerts"], [])
        self.assertEqual(
            health_client.calls,
            [
                ("evaluation", {"hours": 8, "limit": 4}),
                ("context", {"hours": 8, "limit": 4}),
                ("agent_events", {"hours": 8, "limit": 4}),
                ("report_generation", {"hours": 8, "limit": 4}),
                ("rag_retrieval", {"hours": 8, "limit": 4}),
            ],
        )
        for forbidden in (
            "candidate_answer",
            "secret answer",
            "evidence",
            "hidden evidence",
            "suggestion",
            "hidden suggestion",
            "recent_turns",
            "candidate_facts",
            "risk_signals",
            "open_threads",
            "checkpoint_payload",
            "hidden_memory_card",
            "raw_payload",
            "hidden payload should not be returned",
            "hidden checkpoint should not be returned",
            "raw_report",
            "hidden report should not be returned",
            "hidden query should not be returned",
            "hidden resume should not be returned",
            "hidden RAG document should not be returned",
        ):
            self.assertNotIn(forbidden, payload_text)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_degrades_for_high_evaluation_failure_rate(self):
        health_client = MockHealthClient(
            coverage_rate=0.8,
            failure_rate=0.25,
            failure_event_count=2,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertIn("evaluation_failure_rate_high", alert_codes)
        self.assertEqual(
            payload["data"]["evaluation"]["evaluation_failure_event_count"],
            2,
        )

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_degrades_when_langfuse_configured_but_unavailable(self):
        health_client = MockHealthClient()
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=False,
            message="langfuse package is not installed",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertTrue(payload["data"]["langfuse"]["configured"])
        self.assertFalse(payload["data"]["langfuse"]["available"])
        self.assertIn("langfuse_unavailable", alert_codes)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_degrades_for_context_summary_failures(self):
        health_client = MockHealthClient(
            compacted_event_count=1,
            summary_failure_event_count=2,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertIn("context_summary_failures_high", alert_codes)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_includes_agent_event_failure_categories(self):
        health_client = MockHealthClient(agent_event_failure_count=2)
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]
        agent_events = payload["data"]["agent_events"]
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertEqual(agent_events["failure_event_count"], 2)
        self.assertEqual(
            agent_events["top_failure_event_types"][0]["event_type"],
            "turn_evaluation_failed",
        )
        self.assertIn("agent_event_failures_present", alert_codes)
        self.assertNotIn("raw_payload", payload_text)
        self.assertNotIn("hidden payload should not be returned", payload_text)
        self.assertNotIn("checkpoint_payload", payload_text)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_degrades_for_report_generation_failures(self):
        health_client = MockHealthClient(
            report_success_count=1,
            report_failure_count=2,
            report_fallback_success_count=1,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]
        report_generation = payload["data"]["report_generation"]
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertEqual(report_generation["success_count"], 1)
        self.assertEqual(report_generation["failure_count"], 2)
        self.assertEqual(report_generation["fallback_success_count"], 1)
        self.assertEqual(report_generation["top_failure_reasons"][0]["reason"], "RuntimeError")
        self.assertIn("report_generation_failures_high", alert_codes)
        self.assertNotIn("raw_report", payload_text)
        self.assertNotIn("hidden report should not be returned", payload_text)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_degrades_for_rag_failures(self):
        health_client = MockHealthClient(
            rag_success_count=1,
            rag_miss_count=0,
            rag_failure_count=2,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]
        rag_retrieval = payload["data"]["rag_retrieval"]
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertEqual(rag_retrieval["success_count"], 1)
        self.assertEqual(rag_retrieval["failure_count"], 2)
        self.assertEqual(rag_retrieval["top_error_types"][0]["error_type"], "RuntimeError")
        self.assertIn("rag_retrieval_failures_high", alert_codes)
        self.assertNotIn("hidden query should not be returned", payload_text)
        self.assertNotIn("hidden resume should not be returned", payload_text)
        self.assertNotIn("hidden RAG document should not be returned", payload_text)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_degrades_for_rag_misses(self):
        health_client = MockHealthClient(
            rag_success_count=1,
            rag_miss_count=2,
            rag_failure_count=0,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertIn("rag_retrieval_misses_high", alert_codes)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_health_summary_handles_missing_data_client(self):
        set_data_client_provider(lambda: None)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=False,
            available=False,
            message="Monitoring is disabled",
        )

        response = self.client.get("/api/monitoring/health-summary")
        payload = response.get_json()
        alert_codes = [item["code"] for item in payload["data"]["alerts"]]

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["data"]["status"], "unavailable")
        self.assertIn("database_metrics_unavailable", alert_codes)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_diagnostic_summary_default_off_returns_deterministic_fallback_without_hidden_fields(self):
        health_client = MockHealthClient(
            coverage_rate=0.5,
            failure_rate=0.25,
            failure_event_count=2,
            rag_success_count=1,
            rag_miss_count=3,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )

        response = self.client.get("/api/monitoring/diagnostic-summary?hours=8&limit=4")
        payload = response.get_json()
        payload_text = str(payload)
        areas = {item["area"] for item in payload["data"]["diagnosis"]}

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "monitoring_diagnostic")
        self.assertEqual(payload["data"]["status"], "degraded")
        self.assertTrue(payload["data"]["fallback_used"])
        self.assertIn("evaluation", areas)
        self.assertIn("rag", areas)
        self.assertIn("deterministic fallback", payload["message"])
        self.assertEqual(
            health_client.calls,
            [
                ("evaluation", {"hours": 8, "limit": 4}),
                ("context", {"hours": 8, "limit": 4}),
                ("agent_events", {"hours": 8, "limit": 4}),
                ("report_generation", {"hours": 8, "limit": 4}),
                ("rag_retrieval", {"hours": 8, "limit": 4}),
            ],
        )
        for forbidden in (
            "candidate_answer",
            "secret answer",
            "evidence",
            "hidden evidence",
            "suggestion",
            "hidden suggestion",
            "recent_turns",
            "candidate_facts",
            "risk_signals",
            "open_threads",
            "checkpoint_payload",
            "hidden_memory_card",
            "raw_payload",
            "hidden payload should not be returned",
            "hidden checkpoint should not be returned",
            "raw_report",
            "hidden report should not be returned",
            "hidden query should not be returned",
            "hidden resume should not be returned",
            "hidden RAG document should not be returned",
        ):
            self.assertNotIn(forbidden, payload_text)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_diagnostic_summary_uses_llm_when_enabled_and_configured(self):
        os.environ["PROVIEW_MONITORING_DIAGNOSTIC_LLM_ENABLED"] = "1"
        os.environ["PROVIEW_MONITORING_DIAGNOSTIC_LLM_TIMEOUT_SECONDS"] = "0.5"
        health_client = MockHealthClient(
            rag_success_count=1,
            rag_miss_count=3,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )
        llm_payload = {
            "status": "degraded",
            "diagnosis": [
                {
                    "area": "rag",
                    "severity": "warning",
                    "summary": "RAG misses exceed successful retrievals in the aggregate window.",
                    "suggested_next_step": "Review title aliases and question-bank tags offline.",
                }
            ],
        }
        llm_client = MockDiagnosticLLMClient(json.dumps(llm_payload))

        with patch(
            "monitoring.routes._build_monitoring_diagnostic_llm_client",
            return_value=(llm_client, ""),
        ):
            response = self.client.get("/api/monitoring/diagnostic-summary")

        payload = response.get_json()
        prompt_text = str(llm_client.calls)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertFalse(payload["data"]["fallback_used"])
        self.assertEqual(payload["data"]["diagnosis"][0]["area"], "rag")
        self.assertEqual(llm_client.calls[0]["timeout"], 0.5)
        self.assertIn("Aggregate health summary", prompt_text)
        self.assertNotIn("hidden query should not be returned", prompt_text)
        self.assertNotIn("secret answer", prompt_text)
        self.assertNotIn("checkpoint_payload", prompt_text)

    @patch("monitoring.routes.LangfuseMonitoringClient", MockLangfuseClient)
    def test_diagnostic_summary_falls_back_when_llm_output_is_invalid(self):
        os.environ["PROVIEW_MONITORING_DIAGNOSTIC_LLM_ENABLED"] = "1"
        health_client = MockHealthClient(
            report_success_count=0,
            report_failure_count=2,
        )
        set_data_client_provider(lambda: health_client)
        MockLangfuseClient.status_value = MockLangfuseStatus(
            configured=True,
            available=True,
            message="Langfuse monitoring is configured",
        )
        llm_client = MockDiagnosticLLMClient("not json")

        with patch(
            "monitoring.routes._build_monitoring_diagnostic_llm_client",
            return_value=(llm_client, ""),
        ):
            response = self.client.get("/api/monitoring/diagnostic-summary")

        payload = response.get_json()
        areas = {item["area"] for item in payload["data"]["diagnosis"]}

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertTrue(payload["data"]["fallback_used"])
        self.assertIn("report_generation", areas)
        self.assertIn("invalid JSON", payload["message"])

    def test_context_compaction_route_returns_database_metrics_without_hidden_memory(self):
        context_client = MockContextCompactionClient()
        set_data_client_provider(lambda: context_client)

        response = self.client.get("/api/monitoring/context-compaction?hours=6&limit=3")
        payload = response.get_json()
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertEqual(payload["data"]["summary"]["context_compacted_event_count"], 2)
        self.assertEqual(payload["data"]["summary"]["context_summary_failure_event_count"], 1)
        self.assertEqual(payload["data"]["sessions"][0]["latest_context_version"], 3)
        self.assertEqual(context_client.calls, [{"hours": 6, "limit": 3}])
        self.assertNotIn("candidate_facts", payload_text)
        self.assertNotIn("risk_signals", payload_text)
        self.assertNotIn("recent_turns", payload_text)
        self.assertNotIn("open_threads", payload_text)

    def test_context_compaction_route_handles_missing_data_client(self):
        set_data_client_provider(lambda: None)

        response = self.client.get("/api/monitoring/context-compaction")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertIsNone(payload["data"])

    def test_agent_event_rollup_route_returns_database_metrics(self):
        rollup_client = MockAgentEventRollupClient()
        set_data_client_provider(lambda: rollup_client)

        response = self.client.get("/api/monitoring/agent-events/rollup?hours=6&limit=3")
        payload = response.get_json()
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertEqual(payload["data"]["summary"]["total_event_count"], 3)
        self.assertEqual(payload["data"]["summary"]["failure_event_count"], 2)
        self.assertEqual(
            payload["data"]["failure_event_types"][0]["event_type"],
            "turn_evaluation_failed",
        )
        self.assertEqual(rollup_client.calls, [{"hours": 6, "limit": 3}])
        self.assertNotIn("payload_json", payload_text)
        self.assertNotIn("candidate_answer", payload_text)
        self.assertNotIn("evidence", payload_text)
        self.assertNotIn("suggestion", payload_text)

    def test_agent_event_rollup_route_handles_missing_data_client(self):
        set_data_client_provider(lambda: None)

        response = self.client.get("/api/monitoring/agent-events/rollup")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertIsNone(payload["data"])

    def test_report_generation_route_returns_database_metrics(self):
        report_client = MockReportGenerationClient()
        set_data_client_provider(lambda: report_client)

        response = self.client.get("/api/monitoring/report-generation?hours=6&limit=3")
        payload = response.get_json()
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertEqual(payload["data"]["summary"]["success_count"], 2)
        self.assertEqual(payload["data"]["summary"]["failure_count"], 1)
        self.assertEqual(payload["data"]["summary"]["fallback_success_count"], 1)
        self.assertEqual(payload["data"]["failure_reasons"][0]["reason"], "RuntimeError")
        self.assertEqual(report_client.calls, [{"hours": 6, "limit": 3}])
        self.assertNotIn("raw_report", payload_text)
        self.assertNotIn("candidate_answer", payload_text)
        self.assertNotIn("evidence", payload_text)
        self.assertNotIn("suggestion", payload_text)

    def test_report_generation_route_handles_missing_data_client(self):
        set_data_client_provider(lambda: None)

        response = self.client.get("/api/monitoring/report-generation")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertIsNone(payload["data"])

    def test_rag_retrieval_route_returns_database_metrics(self):
        rag_client = MockRagRetrievalClient()
        set_data_client_provider(lambda: rag_client)

        response = self.client.get("/api/monitoring/rag-retrieval?hours=6&limit=3")
        payload = response.get_json()
        payload_text = str(payload)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["configured"])
        self.assertTrue(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertEqual(payload["data"]["summary"]["success_count"], 1)
        self.assertEqual(payload["data"]["summary"]["miss_count"], 1)
        self.assertEqual(payload["data"]["summary"]["failure_count"], 1)
        self.assertEqual(payload["data"]["summary"]["questions_count"], 5)
        self.assertEqual(payload["data"]["error_types"][0]["error_type"], "RuntimeError")
        self.assertEqual(rag_client.calls, [{"hours": 6, "limit": 3}])
        self.assertNotIn("hidden query should not be returned", payload_text)
        self.assertNotIn("hidden resume should not be returned", payload_text)
        self.assertNotIn("hidden RAG document should not be returned", payload_text)
        self.assertNotIn("hidden answer should not be returned", payload_text)

    def test_rag_retrieval_route_handles_missing_data_client(self):
        set_data_client_provider(lambda: None)

        response = self.client.get("/api/monitoring/rag-retrieval")
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["configured"])
        self.assertFalse(payload["available"])
        self.assertEqual(payload["source"], "database")
        self.assertIsNone(payload["data"])


if __name__ == "__main__":
    unittest.main()

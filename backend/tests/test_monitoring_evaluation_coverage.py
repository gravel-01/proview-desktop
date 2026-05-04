import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from monitoring.routes import monitoring_bp, set_data_client_provider

from flask import Flask


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


class MonitoringEvaluationCoverageRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(monitoring_bp)
        self.client = self.app.test_client()

    def tearDown(self):
        set_data_client_provider(None)

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


if __name__ == "__main__":
    unittest.main()

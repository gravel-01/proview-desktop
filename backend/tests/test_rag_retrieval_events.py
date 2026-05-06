import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module


class MockRagDataClient:
    def __init__(self):
        self.events = []

    def storage_capabilities(self):
        return {"agent_events": True}

    def record_agent_event(self, session_id, event_type, *, turn_id="", agent_role="", payload=None):
        self.events.append({
            "session_id": session_id,
            "event_type": event_type,
            "turn_id": turn_id,
            "agent_role": agent_role,
            "payload": payload or {},
        })
        return True

    def search_job_descriptions(self, query, top_k=1, difficulty=None, interview_type=None):
        return [
            {
                "id": "job-1",
                "document": "hidden JD document should not enter event payload",
                "metadata": {
                    "job_name": "后端工程师",
                    "must_have_skills": ["Python"],
                    "tech_tags": ["API"],
                },
            }
        ]

    def search_questions(
        self,
        query,
        job_filter=None,
        top_k=5,
        difficulty=None,
        interview_type=None,
        style=None,
        stage=None,
    ):
        return [
            {
                "id": "question-1",
                "document": "hidden question content should not enter event payload",
                "metadata": {"dimension": "系统设计", "score_5": "hidden rubric"},
            }
        ]

    def search_hr_scripts(self, query, stage=None, top_k=2, interview_type=None, style=None):
        return [
            {
                "id": "script-1",
                "document": "hidden script content should not enter event payload",
                "metadata": {"stage": "开场"},
            }
        ]


class RagRetrievalEventTests(unittest.TestCase):
    def setUp(self):
        self.original_storage_available = app_module.STORAGE_AVAILABLE
        self.original_data_client = app_module.data_client
        self.original_turn_service_client = getattr(app_module.turn_service, "data_client", None)
        app_module.STORAGE_AVAILABLE = True

    def tearDown(self):
        app_module.STORAGE_AVAILABLE = self.original_storage_available
        app_module.data_client = self.original_data_client
        app_module.turn_service.set_data_client(self.original_turn_service_client)

    def test_retrieve_rag_context_records_safe_machine_payload(self):
        client = MockRagDataClient()
        app_module.data_client = client

        rag_context, debug = app_module._retrieve_rag_context(
            session_id="session-rag",
            job_title="后端工程师",
            difficulty="mid",
            interview_type="technical",
            style="strict",
            resume_text="hidden resume OCR text",
            stage="opening",
        )

        self.assertIn("岗位画像", rag_context)
        self.assertEqual(debug["status"], "matched")
        self.assertEqual(len(client.events), 1)
        event = client.events[0]
        payload = event["payload"]
        payload_text = str(payload)

        self.assertEqual(event["event_type"], "rag_retrieval_succeeded")
        self.assertEqual(event["agent_role"], "rag")
        self.assertEqual(payload["stage"], "opening")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["jobs_count"], 1)
        self.assertEqual(payload["questions_count"], 1)
        self.assertEqual(payload["scripts_count"], 1)
        self.assertTrue(payload["job_title_matched"])
        self.assertNotIn("hidden resume OCR text", payload_text)
        self.assertNotIn("hidden JD document", payload_text)
        self.assertNotIn("hidden question content", payload_text)
        self.assertNotIn("hidden script content", payload_text)
        self.assertNotIn("query", payload_text)
        self.assertNotIn("document", payload_text)


if __name__ == "__main__":
    unittest.main()

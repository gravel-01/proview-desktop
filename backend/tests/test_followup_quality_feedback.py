import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module


RAW_SUGGESTION = "请逐字追问：缓存一致性和 Redis 热 key 处理方案"


class MockFollowupDataClient:
    def __init__(self, evaluations=None, turn_status="evaluated"):
        self.turn_status = turn_status
        self.evaluations = evaluations if evaluations is not None else [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "dimension": "性能优化",
                "score": 6,
                "pass_level": "weak_pass",
                "evidence": "说明了缓存方案，但缺少优化前后的指标。",
                "suggestion": RAW_SUGGESTION,
            }
        ]
        self.visible_messages = []
        self.created_turns = []
        self.answered_turn = None
        self.pending_turn = {
            "turn_id": "turn-1",
            "turn_no": 1,
            "question_text": "请讲一个性能优化案例。",
            "answer_text": "",
            "status": "pending",
        }

    def storage_capabilities(self):
        return {
            "structured_turns": True,
            "question_metadata": False,
            "agent_events": False,
        }

    def list_turn_evaluations(self, session_id):
        return list(self.evaluations)

    def list_interview_turns(self, session_id):
        return [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "status": self.turn_status,
            }
        ]

    def append_message(self, session_id, role, content):
        message = {
            "id": f"msg-{len(self.visible_messages) + 1}",
            "session_id": session_id,
            "role": role,
            "content": content,
            "timestamp": "",
        }
        self.visible_messages.append(message)
        return message

    def get_latest_pending_turn(self, session_id):
        return dict(self.pending_turn) if self.pending_turn else None

    def answer_interview_turn(self, turn_id, **kwargs):
        self.answered_turn = {
            **self.pending_turn,
            "turn_id": turn_id,
            "answer_message_id": kwargs.get("answer_message_id", ""),
            "answer_text": kwargs.get("answer_text", ""),
            "status": "answered",
        }
        self.pending_turn = None
        return dict(self.answered_turn)

    def get_next_turn_no(self, session_id):
        return 2

    def create_interview_turn(self, **kwargs):
        turn = {
            "turn_id": kwargs.get("turn_id"),
            "session_id": kwargs.get("session_id"),
            "turn_no": kwargs.get("turn_no"),
            "question_text": kwargs.get("question_text", ""),
            "answer_text": "",
            "status": kwargs.get("status", "pending"),
        }
        self.created_turns.append(turn)
        return dict(turn)


class MockFollowupAgent:
    def __init__(self, response):
        self.response = response
        self.calls = []
        self.chat_history = []
        self.tools = []
        self.agent_executor = None
        self.prompt = "interviewer prompt"
        self.model_name = "mock-model"

    def run(self, query, context=None, trace_context=None):
        self.calls.append({
            "query": query,
            "context": context or "",
            "trace_context": trace_context or {},
        })
        self.chat_history.append({"role": "user", "content": query})
        self.chat_history.append({"role": "assistant", "content": self.response})
        return self.response, []

    def get_chat_history(self):
        return list(self.chat_history)


class FollowupQualityFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.original_storage_available = app_module.STORAGE_AVAILABLE
        self.original_data_client = app_module.data_client
        self.original_agents = dict(app_module._agents)
        self.original_observers = dict(app_module._observers)
        self.original_turn_service_client = getattr(app_module.turn_service, "data_client", None)
        app_module.STORAGE_AVAILABLE = True
        app_module._agents.clear()
        app_module._observers.clear()

    def tearDown(self):
        app_module.STORAGE_AVAILABLE = self.original_storage_available
        app_module.data_client = self.original_data_client
        app_module.turn_service.set_data_client(self.original_turn_service_client)
        app_module._agents.clear()
        app_module._agents.update(self.original_agents)
        app_module._observers.clear()
        app_module._observers.update(self.original_observers)

    def test_hidden_followup_context_does_not_reuse_raw_suggestion(self):
        app_module.data_client = MockFollowupDataClient()

        context = app_module._build_followup_quality_context("session-1")

        self.assertIn("隐藏面试官笔记", context)
        self.assertIn("性能优化", context)
        self.assertNotIn(RAW_SUGGESTION, context)
        self.assertNotIn("Redis 热 key", context)

    def test_suggestion_is_not_saved_or_returned_as_candidate_visible_message(self):
        data_client = MockFollowupDataClient()
        agent = MockFollowupAgent("能补充一下优化前后的具体指标吗？")
        app_module.data_client = data_client
        app_module._agents["session-1"] = agent

        with app_module.app.test_request_context(
            "/api/chat",
            method="POST",
            json={"message": "我用了缓存优化接口性能。"},
        ):
            response = app_module.chat.__wrapped__(session_id="session-1")
        payload = response.get_json()

        visible_text = "\n".join(item["content"] for item in data_client.visible_messages)
        self.assertEqual(payload["response"], agent.response)
        self.assertIn("我用了缓存优化接口性能。", visible_text)
        self.assertIn(agent.response, visible_text)
        self.assertNotIn(RAW_SUGGESTION, visible_text)
        self.assertNotIn(RAW_SUGGESTION, payload["response"])
        self.assertNotIn(RAW_SUGGESTION, data_client.created_turns[0]["question_text"])
        self.assertIn("隐藏面试官笔记", agent.calls[0]["context"])
        self.assertNotIn(RAW_SUGGESTION, agent.calls[0]["context"])

    def test_chat_flow_continues_without_evaluation_rows(self):
        data_client = MockFollowupDataClient(evaluations=[])
        agent = MockFollowupAgent("我们换个角度看，你能说说当时怎么定位瓶颈的吗？")
        app_module.data_client = data_client
        app_module._agents["session-1"] = agent

        with app_module.app.test_request_context(
            "/api/chat",
            method="POST",
            json={"message": "我先看了日志和监控。"},
        ):
            response = app_module.chat.__wrapped__(session_id="session-1")
        payload = response.get_json()

        self.assertEqual(payload["response"], agent.response)
        self.assertEqual(agent.calls[0]["context"], "")
        self.assertEqual(len(data_client.visible_messages), 2)
        self.assertEqual(data_client.created_turns[0]["question_text"], agent.response)

    def test_skipped_or_failed_turn_evaluations_are_not_used_for_followup_context(self):
        for status in ("pending", "skipped", "evaluation_failed"):
            with self.subTest(status=status):
                app_module.data_client = MockFollowupDataClient(turn_status=status)
                context = app_module._build_followup_quality_context("session-1")
                self.assertEqual(context, "")

    def test_stream_context_is_not_recorded_in_agent_chat_history(self):
        from core import langchain_agent as langchain_agent_module

        class FakeStreamClient:
            def __init__(self):
                self.messages = []

            def generate_stream(self, messages):
                self.messages = list(messages)
                yield "请补充一下具体指标。"

        original_have_langchain = langchain_agent_module.HAVE_LANGCHAIN
        langchain_agent_module.HAVE_LANGCHAIN = False
        try:
            client = FakeStreamClient()
            agent = langchain_agent_module.LangChainInterviewAgent(
                llm_client=client,
                max_history_turns=5,
            )
            list(agent.run_stream("我做了缓存优化。", context=RAW_SUGGESTION))
        finally:
            langchain_agent_module.HAVE_LANGCHAIN = original_have_langchain

        sent_messages = "\n".join(item["content"] for item in client.messages)
        history_text = "\n".join(item["content"] for item in agent.get_chat_history())
        self.assertIn(RAW_SUGGESTION, sent_messages)
        self.assertNotIn(RAW_SUGGESTION, history_text)
        self.assertIn("我做了缓存优化。", history_text)


if __name__ == "__main__":
    unittest.main()

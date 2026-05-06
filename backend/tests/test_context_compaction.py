import os
import json
import shutil
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module


class MockContextCompactionDataClient:
    def __init__(self, answer_size=900):
        self.events = []
        self.messages = []
        self.list_agent_event_calls = []
        self.turns = []
        for idx in range(1, 8):
            self.turns.append({
                "turn_id": f"turn-{idx}",
                "turn_no": idx,
                "question_text": f"第{idx}轮问题：请讲一个性能优化和系统设计案例。",
                "answer_text": (
                    f"第{idx}轮回答：我负责核心模块设计，使用缓存和异步队列优化接口性能，"
                    f"也参与上线监控和回滚方案。"
                    + "补充细节" * answer_size
                ),
                "status": "evaluated",
            })

    def list_interview_turns(self, session_id):
        return list(self.turns)

    def storage_capabilities(self):
        return {"agent_events": True}

    def list_question_metadata(self, session_id):
        return [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "dimensions": [
                    {
                        "name": "性能优化",
                        "pass_criteria": "说明瓶颈、动作和量化结果",
                    }
                ],
            },
            {
                "turn_id": "turn-2",
                "turn_no": 2,
                "dimensions": [
                    {
                        "name": "系统设计",
                        "pass_criteria": "说明模块边界和关键取舍",
                    }
                ],
            },
        ]

    def list_turn_evaluations(self, session_id):
        return [
            {
                "turn_id": "turn-1",
                "turn_no": 1,
                "dimension": "性能优化",
                "score": 6,
                "pass_level": "weak_pass",
                "evidence": "有缓存动作，但缺少前后指标。",
                "suggestion": "追问优化前后的量化指标。",
            },
            {
                "turn_id": "turn-2",
                "turn_no": 2,
                "dimension": "系统设计",
                "score": 8,
                "pass_level": "pass",
                "evidence": "能说明模块拆分。",
                "suggestion": "可以追问高并发降级方案。",
            },
        ]

    def record_agent_event(self, session_id, event_type, *, turn_id="", agent_role="", payload=None):
        self.events.append({
            "event_id": f"event-{len(self.events) + 1}",
            "session_id": session_id,
            "event_type": event_type,
            "turn_id": turn_id,
            "agent_role": agent_role,
            "payload": payload or {},
            "created_at": f"2026-05-04T00:00:{len(self.events) + 1:02d}",
        })
        return True

    def list_agent_events(self, session_id, event_type=None, limit=100):
        self.list_agent_event_calls.append({
            "session_id": session_id,
            "event_type": event_type,
            "limit": limit,
        })
        rows = [
            event for event in self.events
            if event["session_id"] == session_id and (not event_type or event["event_type"] == event_type)
        ]
        rows = list(reversed(rows))
        if limit is not None:
            rows = rows[:limit]
        return [dict(row) for row in rows]

    def append_message(self, session_id, role, content):
        self.messages.append({
            "session_id": session_id,
            "role": role,
            "content": content,
        })
        return {"id": len(self.messages), "session_id": session_id, "role": role, "content": content}


class MockSummaryLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, messages, timeout=None):
        self.calls.append({
            "messages": messages,
            "timeout": timeout,
        })
        return self.response


class BlockingSummaryLLMClient:
    def __init__(self, delay=0.2):
        self.delay = delay
        self.calls = []

    def generate(self, messages, timeout=None):
        self.calls.append({
            "messages": messages,
            "timeout": timeout,
        })
        time.sleep(self.delay)
        return json.dumps({"candidate_facts": ["第1轮 延迟返回"]}, ensure_ascii=False)


class MockSummaryAgent:
    def __init__(self, llm_client):
        self.llm_client = llm_client


class MockSummaryChatAgent:
    def __init__(self, llm_client, response="能继续讲一下权限模型的边界吗？"):
        self.llm_client = llm_client
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


class ContextCompactionTests(unittest.TestCase):
    def setUp(self):
        self.original_storage_available = app_module.STORAGE_AVAILABLE
        self.original_data_client = app_module.data_client
        self.original_checkpoints = dict(app_module._session_context_checkpoints)
        self.original_trace_contexts = dict(app_module._session_trace_contexts)
        self.original_agents = dict(app_module._agents)
        self.original_checkpoint_dir = os.environ.get("PROVIEW_CONTEXT_CHECKPOINT_DIR")
        self.original_summary_enabled = os.environ.get(app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV)
        self.original_summary_timeout = os.environ.get(app_module.CONTEXT_SUMMARY_AGENT_TIMEOUT_ENV)
        self.checkpoint_dir = os.path.join(os.path.dirname(__file__), ".codex_tmp_context_checkpoints")
        shutil.rmtree(self.checkpoint_dir, ignore_errors=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.environ["PROVIEW_CONTEXT_CHECKPOINT_DIR"] = self.checkpoint_dir
        os.environ.pop(app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV, None)
        os.environ.pop(app_module.CONTEXT_SUMMARY_AGENT_TIMEOUT_ENV, None)
        app_module.STORAGE_AVAILABLE = True
        app_module._session_context_checkpoints.clear()
        app_module._session_trace_contexts.clear()
        app_module._agents.clear()
        app_module._session_trace_contexts["session-1"] = {"context_version": 1}

    def tearDown(self):
        app_module.STORAGE_AVAILABLE = self.original_storage_available
        app_module.data_client = self.original_data_client
        app_module._session_context_checkpoints.clear()
        app_module._session_context_checkpoints.update(self.original_checkpoints)
        app_module._session_trace_contexts.clear()
        app_module._session_trace_contexts.update(self.original_trace_contexts)
        app_module._agents.clear()
        app_module._agents.update(self.original_agents)
        if self.original_checkpoint_dir is None:
            os.environ.pop("PROVIEW_CONTEXT_CHECKPOINT_DIR", None)
        else:
            os.environ["PROVIEW_CONTEXT_CHECKPOINT_DIR"] = self.original_checkpoint_dir
        if self.original_summary_enabled is None:
            os.environ.pop(app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV, None)
        else:
            os.environ[app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV] = self.original_summary_enabled
        if self.original_summary_timeout is None:
            os.environ.pop(app_module.CONTEXT_SUMMARY_AGENT_TIMEOUT_ENV, None)
        else:
            os.environ[app_module.CONTEXT_SUMMARY_AGENT_TIMEOUT_ENV] = self.original_summary_timeout
        shutil.rmtree(self.checkpoint_dir, ignore_errors=True)

    def test_context_compaction_builds_hidden_memory_card_and_event(self):
        client = MockContextCompactionDataClient(answer_size=900)
        app_module.data_client = client

        context = app_module._build_interviewer_hidden_context("session-1")

        self.assertIn("隐藏长期记忆卡", context)
        self.assertIn("已覆盖能力", context)
        self.assertIn("性能优化", context)
        self.assertIn("待追问线索", context)
        self.assertIn("隐藏面试官笔记", context)
        self.assertEqual(client.events[0]["event_type"], "context_compacted")
        self.assertGreater(client.events[0]["payload"]["estimated_tokens"], 0)
        self.assertIn("recent_turns", client.events[0]["payload"])
        self.assertIn("candidate_facts", client.events[0]["payload"])
        self.assertIn("risk_signals", client.events[0]["payload"])
        self.assertIn("open_threads", client.events[0]["payload"])
        self.assertEqual(app_module._session_trace_contexts["session-1"]["context_version"], 2)

    def test_context_compaction_writes_checkpoint_file_mirror(self):
        client = MockContextCompactionDataClient(answer_size=900)
        app_module.data_client = client

        app_module._build_context_compaction_context("session-1")

        checkpoint_dir = os.path.join(self.checkpoint_dir, "session-1", "context_checkpoints")
        latest_path = os.path.join(checkpoint_dir, "latest.json")
        versioned_path = os.path.join(checkpoint_dir, "checkpoint_002_turn_007.json")
        with open(latest_path, encoding="utf-8") as handle:
            latest = json.load(handle)

        self.assertTrue(os.path.exists(versioned_path))
        self.assertEqual(latest["schema_version"], "context_checkpoint_v1")
        self.assertEqual(latest["session_id"], "session-1")
        self.assertEqual(latest["context_version"], 2)
        self.assertEqual(latest["last_turn_no"], 7)
        self.assertIn("隐藏长期记忆卡", latest["hidden_memory_card"])
        self.assertIn("candidate_facts", latest["checkpoint"])

    def test_context_compaction_reuses_checkpoint_without_duplicate_event(self):
        client = MockContextCompactionDataClient(answer_size=900)
        app_module.data_client = client

        first = app_module._build_context_compaction_context("session-1")
        second = app_module._build_context_compaction_context("session-1")

        self.assertEqual(first, second)
        self.assertEqual(len(client.events), 1)

    def test_context_compaction_rehydrates_checkpoint_from_agent_event(self):
        client = MockContextCompactionDataClient(answer_size=900)
        app_module.data_client = client

        first = app_module._build_context_compaction_context("session-1")
        app_module._session_context_checkpoints.clear()
        second = app_module._build_context_compaction_context("session-1")

        self.assertEqual(first, second)
        self.assertEqual(len(client.events), 1)
        self.assertEqual(client.list_agent_event_calls[-1]["event_type"], "context_compacted")
        self.assertEqual(app_module._session_context_checkpoints["session-1"]["last_turn_no"], 7)
        self.assertEqual(app_module._session_trace_contexts["session-1"]["context_version"], 2)

    def test_context_compaction_rehydrate_does_not_rewrite_checkpoint_file(self):
        client = MockContextCompactionDataClient(answer_size=900)
        app_module.data_client = client

        app_module._build_context_compaction_context("session-1")
        checkpoint_dir = os.path.join(self.checkpoint_dir, "session-1", "context_checkpoints")
        before = sorted(os.listdir(checkpoint_dir))
        app_module._session_context_checkpoints.clear()
        app_module._build_context_compaction_context("session-1")
        after = sorted(os.listdir(checkpoint_dir))

        self.assertEqual(before, after)
        self.assertEqual(len(client.events), 1)

    def test_context_compaction_advances_version_after_rehydrated_checkpoint(self):
        client = MockContextCompactionDataClient(answer_size=900)
        app_module.data_client = client

        app_module._build_context_compaction_context("session-1")
        app_module._session_context_checkpoints.clear()
        client.turns.append({
            "turn_id": "turn-8",
            "turn_no": 8,
            "question_text": "第8轮问题：继续讲高并发降级方案。",
            "answer_text": "第8轮回答：我负责降级策略设计，使用限流和熔断保护核心链路。" + "补充细节" * 900,
            "status": "evaluated",
        })

        app_module._build_context_compaction_context("session-1")

        self.assertEqual(len(client.events), 2)
        self.assertEqual(client.events[-1]["payload"]["last_turn_no"], 8)
        self.assertEqual(client.events[-1]["payload"]["context_version"], 3)
        self.assertEqual(app_module._session_trace_contexts["session-1"]["context_version"], 3)

    def test_context_compaction_hidden_card_is_not_saved_as_visible_message(self):
        client = MockContextCompactionDataClient(answer_size=900)
        app_module.data_client = client

        context = app_module._build_interviewer_hidden_context("session-1")

        self.assertIn("隐藏长期记忆卡", context)
        self.assertEqual(client.messages, [])

    def test_context_compaction_stays_empty_below_threshold(self):
        client = MockContextCompactionDataClient(answer_size=1)
        app_module.data_client = client

        context = app_module._build_context_compaction_context("session-1")

        self.assertEqual(context, "")
        self.assertEqual(client.events, [])

    def test_summary_agent_success_uses_normalized_checkpoint_fields(self):
        client = MockContextCompactionDataClient(answer_size=900)
        raw_summary = {
            "recent_turns": [
                {"turn_no": 6, "question": "请讲系统设计", "answer": "我拆了网关和任务队列。"},
                {"turn_no": 7, "text": "候选人补充了监控和回滚。"},
                "没有轮次的补充摘要",
            ],
            "covered_dimensions": ["架构设计", "score", "rubric", "架构设计"],
            "candidate_facts": [
                {"turn_no": 6, "fact": "候选人负责过异步队列改造。"},
                "说明了团队协作和上线监控。",
            ],
            "risk_signals": [
                {"turn_no": 7, "risk": "量化结果仍不够具体，score=6。"},
            ],
            "open_threads": [
                {"turn_no": 7, "thread": "继续确认降级策略触发条件和恢复流程。"},
            ],
            "extra_field": ["should be ignored"],
        }
        llm_client = MockSummaryLLMClient(json.dumps(raw_summary, ensure_ascii=False))
        app_module.data_client = client
        app_module._agents["session-1"] = MockSummaryAgent(llm_client)
        os.environ[app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV] = "1"

        context = app_module._build_interviewer_hidden_context("session-1")

        payload = client.events[0]["payload"]
        self.assertEqual(llm_client.calls[0]["timeout"], app_module.CONTEXT_SUMMARY_AGENT_DEFAULT_TIMEOUT_SECONDS)
        self.assertIn("异步队列改造", context)
        self.assertIn("第6轮", payload["candidate_facts"][0])
        self.assertIn("截至第7轮", payload["candidate_facts"][1])
        self.assertIn("降级策略触发条件", payload["open_threads"][0])
        self.assertNotIn("extra_field", payload)
        self.assertNotIn("score", "\n".join(payload["risk_signals"]))
        self.assertNotIn("rubric", "\n".join(payload["covered_dimensions"]))
        self.assertLessEqual(len(payload["recent_turns"]), 4)
        self.assertEqual(payload["last_turn_no"], 7)
        self.assertEqual(payload["context_version"], 2)

    def test_summary_agent_failure_falls_back_to_deterministic_memory_card(self):
        client = MockContextCompactionDataClient(answer_size=900)
        llm_client = MockSummaryLLMClient("这不是 JSON")
        app_module.data_client = client
        app_module._agents["session-1"] = MockSummaryAgent(llm_client)
        os.environ[app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV] = "1"

        context = app_module._build_context_compaction_context("session-1")

        self.assertIn("核心模块设计", context)
        compacted_events = [event for event in client.events if event["event_type"] == "context_compacted"]
        failure_events = [event for event in client.events if event["event_type"] == "context_summary_failed"]
        self.assertEqual(len(compacted_events), 1)
        self.assertEqual(len(failure_events), 1)
        self.assertIn("核心模块设计", "\n".join(compacted_events[0]["payload"]["candidate_facts"]))

    def test_summary_agent_timeout_falls_back_without_blocking_long(self):
        client = MockContextCompactionDataClient(answer_size=900)
        llm_client = BlockingSummaryLLMClient(delay=0.2)
        app_module.data_client = client
        app_module._agents["session-1"] = MockSummaryAgent(llm_client)
        os.environ[app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV] = "1"
        os.environ[app_module.CONTEXT_SUMMARY_AGENT_TIMEOUT_ENV] = "0.01"

        started = time.perf_counter()
        context = app_module._build_context_compaction_context("session-1")
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 0.35)
        self.assertIn("核心模块设计", context)
        self.assertEqual(len([event for event in client.events if event["event_type"] == "context_compacted"]), 1)
        self.assertEqual(len([event for event in client.events if event["event_type"] == "context_summary_failed"]), 1)

    def test_summary_checkpoint_does_not_leak_to_messages_response_or_chat_history(self):
        client = MockContextCompactionDataClient(answer_size=900)
        raw_summary = {
            "candidate_facts": ["第7轮 候选人负责过权限系统设计。"],
            "open_threads": ["第7轮后续：追问权限模型边界。"],
        }
        llm_client = MockSummaryLLMClient(json.dumps(raw_summary, ensure_ascii=False))
        agent = MockSummaryChatAgent(llm_client)
        app_module.data_client = client
        app_module._agents["session-1"] = agent
        os.environ[app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV] = "1"

        with app_module.app.test_request_context(
            "/api/chat",
            method="POST",
            json={"message": "我主要做了权限模块。"},
        ):
            response = app_module.chat.__wrapped__(session_id="session-1")
        payload = response.get_json()

        visible_messages = "\n".join(message["content"] for message in client.messages)
        chat_history = "\n".join(message["content"] for message in agent.get_chat_history())
        self.assertEqual(payload["response"], agent.response)
        self.assertIn("权限系统设计", agent.calls[0]["context"])
        self.assertIn("追问权限模型边界", agent.calls[0]["context"])
        self.assertNotIn("权限系统设计", payload["response"])
        self.assertNotIn("追问权限模型边界", payload["response"])
        self.assertNotIn("权限系统设计", visible_messages)
        self.assertNotIn("追问权限模型边界", visible_messages)
        self.assertNotIn("权限系统设计", chat_history)
        self.assertNotIn("追问权限模型边界", chat_history)

    def test_summary_checkpoint_rehydrates_without_duplicate_event_or_file(self):
        client = MockContextCompactionDataClient(answer_size=900)
        raw_summary = {
            "candidate_facts": ["第7轮 候选人负责过权限系统设计。"],
            "open_threads": ["第7轮后续：追问权限模型边界。"],
        }
        llm_client = MockSummaryLLMClient(json.dumps(raw_summary, ensure_ascii=False))
        app_module.data_client = client
        app_module._agents["session-1"] = MockSummaryAgent(llm_client)
        os.environ[app_module.CONTEXT_SUMMARY_AGENT_ENABLED_ENV] = "1"

        first = app_module._build_context_compaction_context("session-1")
        checkpoint_dir = os.path.join(self.checkpoint_dir, "session-1", "context_checkpoints")
        before = sorted(os.listdir(checkpoint_dir))
        app_module._session_context_checkpoints.clear()
        second = app_module._build_context_compaction_context("session-1")
        after = sorted(os.listdir(checkpoint_dir))

        self.assertEqual(first, second)
        self.assertIn("权限系统设计", second)
        self.assertEqual(len([event for event in client.events if event["event_type"] == "context_compacted"]), 1)
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()

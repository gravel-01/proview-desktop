import os
import json
import shutil
import sys
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


class ContextCompactionTests(unittest.TestCase):
    def setUp(self):
        self.original_storage_available = app_module.STORAGE_AVAILABLE
        self.original_data_client = app_module.data_client
        self.original_checkpoints = dict(app_module._session_context_checkpoints)
        self.original_trace_contexts = dict(app_module._session_trace_contexts)
        self.original_checkpoint_dir = os.environ.get("PROVIEW_CONTEXT_CHECKPOINT_DIR")
        self.checkpoint_dir = os.path.join(os.path.dirname(__file__), ".codex_tmp_context_checkpoints")
        shutil.rmtree(self.checkpoint_dir, ignore_errors=True)
        os.makedirs(self.checkpoint_dir, exist_ok=True)
        os.environ["PROVIEW_CONTEXT_CHECKPOINT_DIR"] = self.checkpoint_dir
        app_module.STORAGE_AVAILABLE = True
        app_module._session_context_checkpoints.clear()
        app_module._session_trace_contexts.clear()
        app_module._session_trace_contexts["session-1"] = {"context_version": 1}

    def tearDown(self):
        app_module.STORAGE_AVAILABLE = self.original_storage_available
        app_module.data_client = self.original_data_client
        app_module._session_context_checkpoints.clear()
        app_module._session_context_checkpoints.update(self.original_checkpoints)
        app_module._session_trace_contexts.clear()
        app_module._session_trace_contexts.update(self.original_trace_contexts)
        if self.original_checkpoint_dir is None:
            os.environ.pop("PROVIEW_CONTEXT_CHECKPOINT_DIR", None)
        else:
            os.environ["PROVIEW_CONTEXT_CHECKPOINT_DIR"] = self.original_checkpoint_dir
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


if __name__ == "__main__":
    unittest.main()

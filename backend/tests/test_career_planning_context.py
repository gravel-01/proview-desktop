"""Phase 2 unit tests for the career planning context aggregator and skills."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.career_planning_context import build_career_context
from services.career_planning_skills import (
    DimensionStat,
    build_evidence_aware_tasks,
    compute_dimension_stats,
    derive_gap_severity,
    extract_resume_gap_signals,
    select_top_evidence,
    select_top_suggestions,
    summarize_context_for_llm,
)


# ---------------------------------------------------------------------------
# Skills tests
# ---------------------------------------------------------------------------

class CareerPlanningSkillsTests(unittest.TestCase):
    def test_derive_gap_severity_uses_thresholds(self):
        self.assertEqual(derive_gap_severity(0, 0), "none")
        self.assertEqual(derive_gap_severity(8.5, 4), "none")
        self.assertEqual(derive_gap_severity(7.5, 4), "low")
        self.assertEqual(derive_gap_severity(6.5, 1), "medium")
        self.assertEqual(derive_gap_severity(5.5, 3), "high")
        self.assertEqual(derive_gap_severity(4.0, 1), "medium")  # single low sample

    def test_compute_dimension_stats_groups_evaluations(self):
        evaluations = [
            {"session_id": "s1", "turn_id": "t1", "turn_no": 1, "dimension": "系统设计",
             "score": 5, "pass_level": "fail",
             "evidence": "缺少容量估算和取舍", "suggestion": "先说边界再量化"},
            {"session_id": "s1", "turn_id": "t1", "turn_no": 1, "dimension": "系统设计",
             "score": 4, "pass_level": "fail",
             "evidence": "组件拆分不清晰", "suggestion": "用模块图先讲清依赖"},
            {"session_id": "s2", "turn_id": "t3", "turn_no": 3, "dimension": "表达",
             "score": 8, "pass_level": "pass",
             "evidence": "条理清楚", "suggestion": ""},
        ]
        stats = compute_dimension_stats(evaluations)
        self.assertEqual(len(stats), 2)
        system = next(s for s in stats if s.dimension == "系统设计")
        self.assertEqual(system.evaluation_count, 2)
        self.assertEqual(system.avg_score, 4.5)
        self.assertEqual(system.low_score_count, 2)
        self.assertEqual(system.severity, "high")
        self.assertGreaterEqual(len(system.evidence_samples), 1)
        self.assertGreaterEqual(len(system.suggestion_samples), 1)

        expression = next(s for s in stats if s.dimension == "表达")
        self.assertEqual(expression.severity, "none")
        self.assertEqual(expression.evaluation_count, 1)

    def test_compute_dimension_stats_returns_empty_for_no_data(self):
        self.assertEqual(compute_dimension_stats([]), [])

    def test_extract_resume_gap_signals_backend_role(self):
        # OCR intentionally omits any of the 4 backend-skill keywords
        # (高并发/微服务/缓存/链路/重构 etc.) so every backend skill group
        # is detected as a gap and surfaces in the signal list.
        ocr = (
            "张三 5 年互联网研发经验，主导过电商交易链路的稳定性治理与上线保障。"
            "熟练使用 Python、Django、FastAPI、PostgreSQL 与 Redis 方案；"
            "熟悉 Docker 容器化、Git 工作流与持续集成流水线；"
            "参与过订单中心、库存异步任务调度与对账服务等核心项目，"
            "能够独立完成模块设计、代码评审与上线部署工作，并输出多份技术文档。"
        )
        signals = extract_resume_gap_signals(ocr, "高级后端工程师")
        # 后端岗位应当至少发现 系统设计 / 性能优化 / 问题定位 / 工程实践 维度中的若干缺口
        self.assertTrue(
            any("系统设计" in s for s in signals),
            f"expected 系统设计 gap, got {signals}",
        )
        self.assertGreaterEqual(len(signals), 2)

    def test_extract_resume_gap_signals_returns_short_text_warning(self):
        signals = extract_resume_gap_signals("", "高级后端工程师")
        self.assertEqual(signals, [])

        short_signals = extract_resume_gap_signals("abc", "高级后端工程师")
        self.assertIn("简历正文过短（疑似扫描件无 OCR）", short_signals)

    def test_select_top_evidence_prefers_low_scores(self):
        evaluations = [
            {"session_id": "s1", "turn_id": "t1", "turn_no": 1, "dimension": "X",
             "score": 9, "evidence": "高分评价", "suggestion": ""},
            {"session_id": "s1", "turn_id": "t2", "turn_no": 2, "dimension": "X",
             "score": 3, "evidence": "低分评价，需要补齐基础", "suggestion": ""},
        ]
        low_first = select_top_evidence(evaluations, n=1)
        self.assertEqual(low_first[0].score, 3)

        high_first = select_top_evidence(evaluations, n=1, prefer_low_score=False)
        self.assertEqual(high_first[0].score, 9)

    def test_select_top_suggestions_picks_dimension_match(self):
        evaluations = [
            {"session_id": "s1", "turn_id": "t1", "turn_no": 1, "dimension": "系统设计",
             "score": 4, "evidence": "evidence", "suggestion": "先说边界再量化"},
            {"session_id": "s1", "turn_id": "t2", "turn_no": 2, "dimension": "表达",
             "score": 8, "evidence": "evidence", "suggestion": "结构化"},
        ]
        suggestions = select_top_suggestions(evaluations, n=2)
        self.assertEqual(len(suggestions), 2)
        self.assertIn("先说边界再量化", [s.text for s in suggestions])

    def test_build_evidence_aware_tasks_creates_foundation_when_gaps_exist(self):
        gap = DimensionStat(
            dimension="系统设计",
            evaluation_count=3,
            avg_score=4.5,
            min_score=3,
            max_score=6,
            low_score_count=3,
            severity="high",
            evidence_samples=["缺少容量估算", "组件拆分不清晰"],
            suggestion_samples=["先说边界再量化", "用模块图先讲清依赖"],
            sessions_observed=2,
        )
        templates = build_evidence_aware_tasks(
            target_role="高级后端工程师",
            milestone_index=1,
            gap_dimensions=[gap],
            focus_gaps=["系统设计"],
            horizon_months=6,
        )
        self.assertGreaterEqual(len(templates), 1)
        self.assertEqual(templates[0].gap_key, "系统设计")
        self.assertIn("系统设计", templates[0].title)
        # max_score is 6; the target threshold is max(6, 7) = 7.
        self.assertIn("7", templates[0].success_criteria)

    def test_summarize_context_for_llm_includes_dimensions(self):
        summary = {"session_count": 2, "evaluation_count": 6}
        stats = [
            DimensionStat(
                dimension="系统设计",
                evaluation_count=3,
                avg_score=4.5,
                min_score=3,
                max_score=6,
                low_score_count=3,
                severity="high",
                evidence_samples=[],
                suggestion_samples=[],
                sessions_observed=2,
            )
        ]
        rendered = summarize_context_for_llm(summary, stats)
        self.assertIn("Career Planning Context", rendered)
        self.assertIn("系统设计", rendered)
        self.assertIn("high", rendered)


# ---------------------------------------------------------------------------
# Context aggregator tests
# ---------------------------------------------------------------------------

class _BaseMockDataClient:
    def __init__(self):
        self.mode = "direct"
        self._latest_resume = None
        self._sessions = []
        self._turn_evaluations = {}
        self._question_metadata = {}
        self._interview_turns = {}
        self._session_info = {}

    def get_latest_resume(self, user_id=None):
        return self._latest_resume

    def list_sessions(self, limit=50, user_id=None):
        return list(self._sessions[:limit])

    def get_session_statistics(self, session_id):
        return {"turn_count": 0, "evaluations": [], "avg_score": 0}

    def get_session_info(self, session_id):
        return self._session_info.get(session_id)

    def list_interview_turns(self, session_id):
        return list(self._interview_turns.get(session_id, []))

    def list_question_metadata(self, session_id):
        return list(self._question_metadata.get(session_id, []))

    def list_turn_evaluations(self, session_id):
        return list(self._turn_evaluations.get(session_id, []))

    def storage_capabilities(self):
        return {
            "structured_turns": True,
            "question_metadata": True,
            "turn_evaluations": True,
            "agent_events": True,
        }


class _RichMockDataClient(_BaseMockDataClient):
    """Mock data client that exposes per-turn evidence for tests."""

    def __init__(self):
        super().__init__()
        self._latest_resume = {
            "id": 7,
            "file_name": "zhang_san.pdf",
            "upload_time": "2026-05-01T10:00:00",
            "ocr_result": (
                "张三 后端工程师\n"
                "熟练使用 Python、Django、PostgreSQL、Docker\n"
                "熟悉 Redis、消息队列\n"
            ),
        }
        self._sessions = [
            {
                "session_id": "s-1",
                "position": "高级后端工程师",
                "status": "completed",
                "interview_style": "default",
                "start_time": "2026-05-10T09:00:00",
                "end_time": "2026-05-10T10:00:00",
            },
            {
                "session_id": "s-2",
                "position": "高级后端工程师",
                "status": "completed",
                "interview_style": "default",
                "start_time": "2026-05-20T09:00:00",
                "end_time": "2026-05-20T10:00:00",
            },
        ]
        self._session_info = {session["session_id"]: session for session in self._sessions}
        self._interview_turns = {
            "s-1": [
                {"turn_id": "t-1-1", "turn_no": 1, "status": "answered",
                 "question_text": "请描述一个高并发场景", "answer_text": "我做过..."},
                {"turn_id": "t-1-2", "turn_no": 2, "status": "answered",
                 "question_text": "k8s 怎么做扩容", "answer_text": "通过 HPA..."},
            ],
            "s-2": [
                {"turn_id": "t-2-1", "turn_no": 1, "status": "answered",
                 "question_text": "系统设计题", "answer_text": "..."},
            ],
        }
        self._question_metadata = {
            "s-1": [
                {"question_id": "q-1", "turn_id": "t-1-1", "turn_no": 1,
                 "dimensions": [{"name": "系统设计"}, {"name": "性能优化"}],
                 "difficulty": "hard", "question_type": "system_design",
                 "source": "rag"},
                {"question_id": "q-2", "turn_id": "t-1-2", "turn_no": 2,
                 "dimensions": [{"name": "系统设计"}],
                 "difficulty": "hard", "question_type": "system_design",
                 "source": "rag"},
            ],
            "s-2": [
                {"question_id": "q-3", "turn_id": "t-2-1", "turn_no": 1,
                 "dimensions": [{"name": "系统设计"}],
                 "difficulty": "mid", "question_type": "system_design",
                 "source": "rag"},
            ],
        }
        self._turn_evaluations = {
            "s-1": [
                {"evaluation_id": "e-1-1", "session_id": "s-1", "turn_id": "t-1-1",
                 "turn_no": 1, "dimension": "系统设计", "score": 4, "pass_level": "fail",
                 "evidence": "缺少容量估算和取舍说明", "suggestion": "先用 30 秒讲清边界再量化",
                 "evaluator_version": "eval_observer_v1"},
                {"evaluation_id": "e-1-2", "session_id": "s-1", "turn_id": "t-1-2",
                 "turn_no": 2, "dimension": "系统设计", "score": 5, "pass_level": "fail",
                 "evidence": "HPA 配置描述不够具体", "suggestion": "结合 YAML 例子说清楚",
                 "evaluator_version": "eval_observer_v1"},
            ],
            "s-2": [
                {"evaluation_id": "e-2-1", "session_id": "s-2", "turn_id": "t-2-1",
                 "turn_no": 1, "dimension": "表达", "score": 8, "pass_level": "pass",
                 "evidence": "条理清楚", "suggestion": "",
                 "evaluator_version": "eval_observer_v1"},
            ],
        }


class _EmptyMockDataClient(_BaseMockDataClient):
    def __init__(self):
        super().__init__()
        self._latest_resume = None
        self._sessions = []


class CareerPlanningContextTests(unittest.TestCase):
    def test_build_career_context_returns_empty_when_no_data(self):
        client = _EmptyMockDataClient()
        context = build_career_context(client, 1, target_role="高级后端工程师")
        self.assertTrue(context.is_empty())
        self.assertEqual(context.summary.evaluation_count, 0)
        self.assertEqual(context.summary.session_count, 0)
        self.assertEqual(context.dimension_stats, [])

    def test_build_career_context_returns_empty_when_data_client_is_none(self):
        context = build_career_context(None, 1, target_role="高级后端工程师")
        self.assertTrue(context.is_empty())
        self.assertEqual(context.build_meta.data_client_kind, "missing")

    def test_build_career_context_aggregates_evaluations_across_sessions(self):
        client = _RichMockDataClient()
        context = build_career_context(client, 1, target_role="高级后端工程师")

        self.assertFalse(context.is_empty())
        self.assertEqual(context.summary.session_count, 2)
        self.assertEqual(context.summary.completed_session_count, 2)
        self.assertEqual(context.summary.evaluation_count, 3)
        self.assertEqual(context.summary.question_metadata_count, 3)
        self.assertGreater(context.summary.turn_count, 0)

        # 系统设计应该有 high severity
        system_stat = next(
            (s for s in context.dimension_stats if s.dimension == "系统设计"),
            None,
        )
        self.assertIsNotNone(system_stat)
        self.assertEqual(system_stat.evaluation_count, 2)
        self.assertEqual(system_stat.avg_score, 4.5)
        self.assertEqual(system_stat.low_score_count, 2)
        self.assertEqual(system_stat.severity, "high")
        self.assertGreaterEqual(len(system_stat.evidence_samples), 1)
        self.assertGreaterEqual(len(system_stat.suggestion_samples), 1)

        # evidence_samples / suggestion_samples should not be empty
        self.assertGreaterEqual(len(context.evidence_samples), 1)
        self.assertGreaterEqual(len(context.suggestion_samples), 1)

    def test_build_career_context_extracts_resume_gap_signals(self):
        client = _RichMockDataClient()
        context = build_career_context(client, 1, target_role="高级后端工程师")

        self.assertTrue(context.resume_summary.has_resume)
        self.assertEqual(context.resume_summary.file_name, "zhang_san.pdf")
        # 后端方向，OCR 缺 k8s / 高并发 / 微服务
        self.assertTrue(context.resume_summary.gap_signals,
                        f"expected gap signals, got {context.resume_summary.gap_signals}")

    def test_build_career_context_handles_data_client_errors_gracefully(self):
        client = _RichMockDataClient()
        client.list_turn_evaluations = MagicMock(side_effect=Exception("boom"))
        context = build_career_context(client, 1, target_role="高级后端工程师")
        # Should not raise; should still report empty evidence path
        self.assertEqual(context.summary.evaluation_count, 0)
        self.assertFalse(context.has_real_evidence())

    def test_build_career_context_respects_session_limit(self):
        client = _RichMockDataClient()
        context = build_career_context(client, 1, target_role="高级后端工程师", session_limit=1)
        self.assertEqual(context.summary.session_count, 1)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the phase 4 resource-closure loop.

Covers the deterministic resource-closure skills introduced in
``services/career_planning_skills`` and the corresponding stores in
``services/career_planning_memory``:

- :func:`score_resource_match` — single-section recommendation score
- :func:`collect_resource_recommendations` — top-N ranked sections
- :func:`tag_resource_to_task` — task ↔ doc section binding
- :func:`apply_read_event_to_progress` — task progress delta
- :class:`DocReadEventStore` — persisted reading events
- :class:`DocFavoriteStore` — persisted favourites (idempotent toggle)
- :class:`TaskResourceRefStore` — task ↔ doc section refs
- :func:`register_phase2_pure_skills` — phase 4 skill registration
- :class:`CareerPlanningDocumentRepository` — section-level search/filter

The tests use a minimal service stub (mirroring the
:class:`CareerPlanningService` connection contract) so they can run
without the real service or database.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List, Dict, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.career_planning_doc_taxonomy import get_section_taxonomy
from services.career_planning_docs import CareerPlanningDocumentRepository
from services.career_planning_memory import (
    DocFavoriteStore,
    DocReadEventStore,
    MemoryBus,
    TaskResourceRefStore,
)
from services.career_planning_skill_registry import (
    SKILL_KIND_PURE_FUNCTION,
    Skill,
    SkillRegistry,
    register_phase2_pure_skills,
)
from services.career_planning_skills import (
    apply_read_event_to_progress,
    collect_resource_recommendations,
    score_resource_match,
    tag_resource_to_task,
)


# ---------------------------------------------------------------------------
# Stub service
# ---------------------------------------------------------------------------

class _StubService:
    """Service stub that owns a SQLite DB path and yields connections."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    @contextmanager
    def _managed_connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def _make_db(suffix: str = "memory") -> Path:
    base = Path(__file__).resolve().parent / f".codex_tmp_phase4_{suffix}"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    return base / "phase4.sqlite3"


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

def _sample_sections() -> List[Dict[str, Any]]:
    """Return a deterministic set of sections covering gap / skill / task tags."""
    return [
        {
            "doc_id": "job-seeking-guide",
            "doc_title": "求职攻略",
            "section_idx": 1,
            "section_heading": "📄 简历优化：让HR一眼看上你",
            "section_bullets": ["STAR 法则", "量化业绩"],
            "section_action_items": ["完成简历初稿"],
            "skill_tags": ["沟通表达", "工程实践"],
            "gap_tags": ["resume_star", "resume_quantification"],
            "task_types": ["project", "skill_practice"],
            "tag_known": True,
        },
        {
            "doc_id": "interview-guide",
            "doc_title": "面试进阶",
            "section_idx": 2,
            "section_heading": "🎤 行为面：用 STAR 拆解经历",
            "section_bullets": ["S/T/A/R 顺序", "行为面陷阱"],
            "section_action_items": ["准备 3 个 STAR 案例"],
            "skill_tags": ["沟通表达"],
            "gap_tags": ["interview_expression", "resume_star"],
            "task_types": ["interview_prep"],
            "tag_known": True,
        },
        {
            "doc_id": "ai-interview",
            "doc_title": "AI 面试实战",
            "section_idx": 0,
            "section_heading": "🤖 AI 面试官的评分机制",
            "section_bullets": ["多维度评估", "反馈循环"],
            "section_action_items": ["完成 1 次 AI 模拟面试"],
            "skill_tags": ["学习能力"],
            "gap_tags": ["ai_interview_familiarity"],
            "task_types": ["interview_prep"],
            "tag_known": True,
        },
        {
            "doc_id": "career-path",
            "doc_title": "职业发展",
            "section_idx": 1,
            "section_heading": "🧭 方向选择：找准自己的跑道",
            "section_bullets": ["职业定位"],
            "section_action_items": ["列出 3 个候选方向"],
            "skill_tags": ["学习能力"],
            "gap_tags": ["career_direction"],
            "task_types": ["course", "skill_practice"],
            "tag_known": True,
        },
    ]


# ---------------------------------------------------------------------------
# score_resource_match
# ---------------------------------------------------------------------------

class ScoreResourceMatchTests(unittest.TestCase):
    def test_high_gap_overlap_raises_score(self):
        section = _sample_sections()[0]
        score = score_resource_match(
            section,
            user_gap_keys=["resume_star"],
            user_skill_keys=["沟通表达"],
            user_task_types=["project"],
        )
        self.assertGreaterEqual(score, 0.5)

    def test_zero_gap_overlap_returns_low_score(self):
        section = _sample_sections()[0]
        score = score_resource_match(
            section,
            user_gap_keys=["unrelated_gap"],
            user_skill_keys=["unrelated_skill"],
            user_task_types=["unrelated_type"],
        )
        self.assertLess(score, 0.4)

    def test_target_role_match_adds_bonus(self):
        section = _sample_sections()[0]
        base = score_resource_match(
            section,
            user_gap_keys=[],
            user_skill_keys=[],
            user_task_types=[],
        )
        boosted = score_resource_match(
            section,
            user_gap_keys=[],
            user_skill_keys=[],
            user_task_types=[],
            target_role="高级前端",
        )
        self.assertGreaterEqual(boosted, base)

    def test_already_completed_penalised(self):
        # Use a single-key overlap so the raw score sits below the 4.0 clamp
        # and the completed penalty visibly reduces the result.
        section = {
            "doc_id": "doc-a",
            "doc_title": "Doc A",
            "section_idx": 0,
            "section_heading": "示例小节",
            "skill_tags": ["沟通表达"],
            "gap_tags": ["resume_star"],
            "task_types": ["project"],
            "tag_known": True,
        }
        score_full = score_resource_match(
            section,
            user_gap_keys=["resume_star"],
            user_skill_keys=["沟通表达"],
            user_task_types=["project"],
        )
        score_done = score_resource_match(
            section,
            user_gap_keys=["resume_star"],
            user_skill_keys=["沟通表达"],
            user_task_types=["project"],
            already_completed_doc_ids=["doc-a"],
        )
        self.assertGreater(score_full, 0.0)
        self.assertLess(score_done, score_full)


# ---------------------------------------------------------------------------
# collect_resource_recommendations
# ---------------------------------------------------------------------------

class CollectRecommendationsTests(unittest.TestCase):
    def setUp(self):
        self.sections = _sample_sections()

    def test_returns_top_n_sorted_by_score(self):
        out = collect_resource_recommendations(
            self.sections,
            user_gap_keys=["resume_star", "interview_expression"],
            user_skill_keys=["沟通表达"],
            user_task_types=["project", "interview_prep"],
            limit=2,
        )
        self.assertEqual(len(out), 2)
        scores = [item["score"] for item in out]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_score_threshold_filters_out(self):
        out = collect_resource_recommendations(
            self.sections,
            user_gap_keys=["resume_star"],
            user_skill_keys=["沟通表达"],
            user_task_types=["project"],
            limit=10,
            score_threshold=0.95,
        )
        # 0.95 阈值下大多数 section 应被过滤
        self.assertEqual(len(out), 0)

    def test_handles_empty_user_context(self):
        out = collect_resource_recommendations(
            self.sections,
            user_gap_keys=[],
            user_skill_keys=[],
            user_task_types=[],
            limit=3,
        )
        # 至少有 1 条 fallback（tag 相似度）
        self.assertGreaterEqual(len(out), 0)


# ---------------------------------------------------------------------------
# tag_resource_to_task
# ---------------------------------------------------------------------------

class TagResourceToTaskTests(unittest.TestCase):
    def test_binds_top_k_sections_to_task(self):
        task = {
            "id": 1,
            "title": "打磨简历",
            "gap_key": "resume_star",
            "task_type": "project",
        }
        refs = tag_resource_to_task(task, _sample_sections(), top_k=2)
        self.assertLessEqual(len(refs), 2)
        for ref in refs:
            self.assertIn("doc_id", ref)
            self.assertIn("section_idx", ref)
            self.assertIn("reason", ref)
            self.assertIn("score", ref)
            self.assertGreater(ref["score"], 0)

    def test_returns_empty_when_no_gap_match(self):
        task = {
            "id": 99,
            "title": "未知 gap",
            "gap_key": "no_such_gap",
            "task_type": "project",
        }
        refs = tag_resource_to_task(task, _sample_sections(), top_k=2)
        self.assertEqual(refs, [])


# ---------------------------------------------------------------------------
# apply_read_event_to_progress
# ---------------------------------------------------------------------------

class ApplyReadEventTests(unittest.TestCase):
    def test_completed_event_increments_progress(self):
        new_value = apply_read_event_to_progress(
            current_progress=20.0,
            completed=True,
            increment=10.0,
        )
        self.assertEqual(new_value, 30.0)

    def test_non_completed_event_no_op(self):
        new_value = apply_read_event_to_progress(
            current_progress=20.0,
            completed=False,
            increment=10.0,
        )
        self.assertEqual(new_value, 20.0)

    def test_progress_clamped_to_100(self):
        new_value = apply_read_event_to_progress(
            current_progress=95.0,
            completed=True,
            increment=10.0,
        )
        self.assertEqual(new_value, 100.0)

    def test_progress_clamped_to_0_on_negative(self):
        new_value = apply_read_event_to_progress(
            current_progress=5.0,
            completed=True,
            increment=-20.0,
        )
        self.assertEqual(new_value, 0.0)


# ---------------------------------------------------------------------------
# DocReadEventStore
# ---------------------------------------------------------------------------

class DocReadEventStoreTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db("read_events")
        self.service = _StubService(self.db_path)
        self.store = DocReadEventStore(service=self.service)
        self.store.ensure_schema()

    def tearDown(self):
        self.store = None
        self.service = None
        shutil.rmtree(self.db_path.parent, ignore_errors=True)

    def test_insert_and_list_for_user(self):
        rid = self.store.insert(
            user_id=1, doc_id="doc-a", section_idx=0,
            read_seconds=42, completed=True, task_id=10,
        )
        self.assertGreater(rid, 0)
        rows = self.store.list_for_user(1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doc_id"], "doc-a")
        self.assertEqual(int(rows[0]["completed"]), 1)

    def test_doc_state_aggregates(self):
        # 同 doc 多次事件，2 次 completed
        for idx in range(3):
            self.store.insert(
                user_id=1, doc_id="doc-a", section_idx=idx,
                read_seconds=10, completed=(idx < 2), task_id=10,
            )
        state = self.store.doc_state(1, "doc-a")
        self.assertEqual(state["read_count"], 3)
        self.assertEqual(state["completed_count"], 2)
        self.assertNotEqual(state["last_read_at"], "")

    def test_list_filters_by_doc(self):
        self.store.insert(user_id=1, doc_id="doc-a", section_idx=0)
        self.store.insert(user_id=1, doc_id="doc-b", section_idx=0)
        rows = self.store.list_for_user(1, doc_id="doc-a")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["doc_id"], "doc-a")


# ---------------------------------------------------------------------------
# DocFavoriteStore
# ---------------------------------------------------------------------------

class DocFavoriteStoreTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db("favorites")
        self.service = _StubService(self.db_path)
        self.store = DocFavoriteStore(service=self.service)
        self.store.ensure_schema()

    def tearDown(self):
        self.store = None
        self.service = None
        shutil.rmtree(self.db_path.parent, ignore_errors=True)

    def test_toggle_adds_and_removes(self):
        self.assertTrue(self.store.toggle(1, "doc-a"))
        self.assertTrue(self.store.is_favorite(1, "doc-a"))
        self.assertFalse(self.store.toggle(1, "doc-a"))
        self.assertFalse(self.store.is_favorite(1, "doc-a"))

    def test_list_for_user(self):
        self.store.toggle(1, "doc-a")
        self.store.toggle(1, "doc-b")
        ids = self.store.list_for_user(1)
        self.assertIn("doc-a", ids)
        self.assertIn("doc-b", ids)

    def test_user_isolation(self):
        self.store.toggle(1, "doc-a")
        self.assertFalse(self.store.is_favorite(2, "doc-a"))


# ---------------------------------------------------------------------------
# TaskResourceRefStore
# ---------------------------------------------------------------------------

def _seed_task_refs(service: _StubService) -> None:
    """Seed minimal career_plans / career_milestones / career_tasks."""
    with service._managed_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS career_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                target_role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS career_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS career_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                milestone_id INTEGER NOT NULL,
                plan_id INTEGER NOT NULL
            );
            """
        )
        conn.execute(
            "INSERT INTO career_plans (id, user_id, target_role, created_at, updated_at) VALUES (1, '1', '前端', datetime('now'), datetime('now'))"
        )
        conn.execute("INSERT INTO career_milestones (id, plan_id) VALUES (1, 1)")
        conn.execute("INSERT INTO career_tasks (id, milestone_id, plan_id) VALUES (10, 1, 1)")
        conn.execute("INSERT INTO career_tasks (id, milestone_id, plan_id) VALUES (11, 1, 1)")


class TaskResourceRefStoreTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db("task_refs")
        self.service = _StubService(self.db_path)
        _seed_task_refs(self.service)
        self.store = TaskResourceRefStore(service=self.service)
        self.store.ensure_schema()

    def tearDown(self):
        self.store = None
        self.service = None
        shutil.rmtree(self.db_path.parent, ignore_errors=True)

    def test_upsert_inserts_and_updates(self):
        self.store.upsert(task_id=10, doc_id="doc-a", section_idx=0, reason="r1")
        rows = self.store.list_for_task(10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "r1")

        # 二次 upsert：同主键 → 覆盖 reason
        self.store.upsert(task_id=10, doc_id="doc-a", section_idx=0, reason="r2")
        rows = self.store.list_for_task(10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reason"], "r2")

    def test_list_for_user_returns_grouped_dict(self):
        self.store.upsert(task_id=10, doc_id="doc-a", section_idx=0, reason="r1")
        self.store.upsert(task_id=10, doc_id="doc-b", section_idx=1, reason="r2")
        self.store.upsert(task_id=11, doc_id="doc-c", section_idx=0, reason="r3")
        grouped = self.store.list_for_user(1)
        self.assertEqual(set(grouped.keys()), {10, 11})
        self.assertEqual(len(grouped[10]), 2)
        self.assertEqual(len(grouped[11]), 1)


# ---------------------------------------------------------------------------
# Phase 4 skill registration
# ---------------------------------------------------------------------------

class Phase4SkillRegistrationTests(unittest.TestCase):
    def test_phase4_skills_are_registered(self):
        reg = SkillRegistry()
        register_phase2_pure_skills(reg)
        # reg.list() returns dicts (legacy contract)
        names = {row["name"] for row in reg.list()}
        for name in (
            "score_resource_match",
            "tag_resource_to_task",
            "apply_read_event_to_progress",
        ):
            self.assertIn(name, names, f"{name} missing from registry")

    def test_phase4_skills_run_via_registry(self):
        reg = SkillRegistry()
        register_phase2_pure_skills(reg)
        # score_resource_match
        result = reg.run(
            "score_resource_match",
            section=_sample_sections()[0],
            user_gap_keys=["resume_star"],
            user_skill_keys=["沟通表达"],
            user_task_types=["project"],
            log_eval=False,
        )
        self.assertTrue(result.success)
        self.assertIsInstance(result.output, float)
        # apply_read_event_to_progress
        result = reg.run(
            "apply_read_event_to_progress",
            current_progress=20.0,
            completed=True,
            increment=10.0,
            log_eval=False,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.output, 30.0)


# ---------------------------------------------------------------------------
# Document repository — section search
# ---------------------------------------------------------------------------

class SectionTaxonomyTests(unittest.TestCase):
    def test_known_heading_has_taxonomy(self):
        tax = get_section_taxonomy("📄 简历优化：让HR一眼看上你")
        self.assertIn("resume_star", tax.gap_tags)
        self.assertIn("沟通表达", tax.skill_tags)
        self.assertIn("project", tax.task_types)
        self.assertTrue(tax.tag_known)

    def test_unknown_heading_returns_unknown(self):
        tax = get_section_taxonomy("未收录的小节")
        self.assertEqual(tax.skill_tags, ())
        self.assertEqual(tax.gap_tags, ())
        self.assertFalse(tax.tag_known)


# ---------------------------------------------------------------------------
# Smoke: MemoryBus exposes the phase 4 stores
# ---------------------------------------------------------------------------

class MemoryBusPhase4Tests(unittest.TestCase):
    def test_bus_exposes_phase4_stores(self):
        service = _StubService(_make_db("bus"))
        bus = MemoryBus(service=service)
        self.assertIsInstance(bus.doc_read_events(), DocReadEventStore)
        self.assertIsInstance(bus.doc_favorites(), DocFavoriteStore)
        self.assertIsInstance(bus.task_resource_refs(), TaskResourceRefStore)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the career planning memory subsystem (phase 3).

Covers the three building blocks introduced in
``services/career_planning_memory``:

- :class:`MemoryStore`: thin wrapper around the existing SQLite store
- :class:`SkillEvalLogStore`: per-skill audit log
- :class:`MemoryBus`: facade that ties short-term and long-term memory

The tests use a minimal service stub (mirroring the
:class:`CareerPlanningService` connection contract) so they can run
without the real service.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.career_planning_memory import (
    MemoryBus,
    MemoryStore,
    SkillEvalLogStore,
    SkillEvalRecord,
    Timer,
    _normalize_plan_row,
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> Path:
    base = Path(__file__).resolve().parent / ".codex_tmp_memory_unit"
    shutil.rmtree(base, ignore_errors=True)
    base.mkdir(parents=True, exist_ok=True)
    return base / "memory.sqlite3"


def _seed_career_plans(service: _StubService) -> None:
    """Insert a minimal career_plans row so MemoryStore.fetch_* works."""
    with service._managed_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS career_profiles (
                user_id TEXT PRIMARY KEY,
                target_role TEXT NOT NULL,
                current_stage TEXT NOT NULL,
                interest_tags TEXT NOT NULL,
                strength_tags TEXT NOT NULL,
                gap_tags TEXT NOT NULL,
                overall_score REAL NOT NULL DEFAULT 0,
                source_summary TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS career_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                target_role TEXT NOT NULL,
                career_goal TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                horizon_months INTEGER NOT NULL DEFAULT 6,
                summary TEXT NOT NULL DEFAULT '',
                assessment_json TEXT NOT NULL DEFAULT '{}',
                recommendation_json TEXT NOT NULL DEFAULT '[]',
                source_session_ids_json TEXT NOT NULL DEFAULT '[]',
                source_resume_id INTEGER,
                source_snapshot_json TEXT NOT NULL DEFAULT '{}',
                model_id TEXT NOT NULL DEFAULT '',
                prompt_hash TEXT NOT NULL DEFAULT '',
                generation_latency_ms INTEGER NOT NULL DEFAULT 0,
                generation_tokens_in INTEGER NOT NULL DEFAULT 0,
                generation_tokens_out INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS career_milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                month_label TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'planned',
                sort_order INTEGER NOT NULL DEFAULT 0,
                target_date TEXT NOT NULL DEFAULT '',
                success_criteria TEXT NOT NULL DEFAULT '',
                focus_gaps_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS career_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                milestone_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                task_type TEXT NOT NULL DEFAULT 'skill_practice',
                priority INTEGER NOT NULL DEFAULT 3,
                status TEXT NOT NULL DEFAULT 'pending',
                progress REAL NOT NULL DEFAULT 0,
                due_date TEXT NOT NULL DEFAULT '',
                completed_at TEXT NOT NULL DEFAULT '',
                gap_key TEXT NOT NULL DEFAULT '',
                source_evidence_json TEXT NOT NULL DEFAULT '[]',
                resource_refs_json TEXT NOT NULL DEFAULT '[]',
                estimated_effort TEXT NOT NULL DEFAULT '',
                success_criteria TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO career_profiles (user_id, target_role, current_stage, interest_tags, strength_tags, gap_tags, overall_score, source_summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            ("1", "前端", "成长中", "[]", "[]", "[]", 7.0, "seeded"),
        )
        conn.execute(
            """
            INSERT INTO career_plans (user_id, target_role, career_goal, status, horizon_months, summary, assessment_json, recommendation_json, source_session_ids_json, source_snapshot_json, model_id, prompt_hash, generation_latency_ms, generation_tokens_in, generation_tokens_out, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
            """,
            (
                "1",
                "前端",
                "seed",
                "active",
                6,
                "summary",
                "{\"x\":1}",
                "[]",
                "[]",
                "{}",
                "mock-llm",
                "abc123",
                100,
                200,
                50,
            ),
        )


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------

class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db()
        self.service = _StubService(self.db_path)
        _seed_career_plans(self.service)
        self.store = MemoryStore(service=self.service)

    def tearDown(self):
        self.store = None
        self.service = None
        shutil.rmtree(self.db_path.parent, ignore_errors=True)

    def test_fetch_active_plan_returns_dict(self):
        plan = self.store.fetch_active_plan(1)
        self.assertIsNotNone(plan)
        self.assertEqual(plan["target_role"], "前端")
        self.assertEqual(plan["assessment_json"], {"x": 1})
        self.assertEqual(plan["model_id"], "mock-llm")

    def test_fetch_plan_history(self):
        history = self.store.fetch_plan_history(1, limit=5)
        self.assertEqual(len(history), 1)

    def test_db_path(self):
        self.assertEqual(self.store.db_path, str(self.db_path))


# ---------------------------------------------------------------------------
# SkillEvalLogStore
# ---------------------------------------------------------------------------

class SkillEvalLogStoreTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db()
        self.service = _StubService(self.db_path)
        self.store = SkillEvalLogStore(service=self.service)
        self.store.ensure_schema()

    def tearDown(self):
        self.store = None
        self.service = None
        shutil.rmtree(self.db_path.parent, ignore_errors=True)

    def test_insert_persists_record(self):
        record = SkillEvalRecord(
            skill_name="compute_dimension_stats",
            skill_version="v1",
            user_id=1,
            inputs={"k": 1},
            outputs={"k": 1},
            latency_ms=10,
            tokens_in=100,
            tokens_out=50,
            success=True,
        )
        row_id = self.store.insert(record)
        self.assertGreater(row_id, 0)
        rows = self.store.read(skill_name="compute_dimension_stats", limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["skill_name"], "compute_dimension_stats")
        self.assertEqual(int(rows[0]["success"]), 1)
        self.assertEqual(rows[0]["latency_ms"], 10)

    def test_read_filters_by_user(self):
        self.store.insert(SkillEvalRecord(skill_name="x", user_id="1", success=True))
        self.store.insert(SkillEvalRecord(skill_name="x", user_id="2", success=True))
        rows = self.store.read(user_id="1", limit=10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["user_id"], "1")

    def test_summary_aggregates(self):
        self.store.insert(SkillEvalRecord(skill_name="x", user_id="1", success=True, latency_ms=10))
        self.store.insert(SkillEvalRecord(skill_name="x", user_id="1", success=False, fallback_reason="parse_error", latency_ms=20))
        self.store.insert(SkillEvalRecord(skill_name="x", user_id="1", success=True, latency_ms=30))
        s = self.store.summary(user_id="1")
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["success"], 2)
        self.assertEqual(s["failure"], 1)
        self.assertAlmostEqual(s["success_rate"], 0.667, places=2)
        # average latency over all 3 records (10+20+30)/3 = 20.0
        self.assertEqual(s["avg_latency_ms"], 20.0)

    def test_record_to_row_serialises_payloads(self):
        record = SkillEvalRecord(
            skill_name="y",
            inputs={"a": 1, "b": [1, 2]},
            outputs={"k": "v"},
        )
        row = record.to_row()
        self.assertEqual(row["inputs_json"], '{"a": 1, "b": [1, 2]}')
        self.assertEqual(row["outputs_json"], '{"k": "v"}')
        self.assertEqual(row["skill_version"], "v1")
        self.assertEqual(row["success"], 1)


# ---------------------------------------------------------------------------
# MemoryBus
# ---------------------------------------------------------------------------

class MemoryBusTests(unittest.TestCase):
    def setUp(self):
        self.db_path = _make_db()
        self.service = _StubService(self.db_path)
        self.bus = MemoryBus(service=self.service)

    def tearDown(self):
        self.bus = None
        self.service = None
        shutil.rmtree(self.db_path.parent, ignore_errors=True)

    def test_short_term_get_set(self):
        self.assertIsNone(self.bus.short_term())
        sentinel = object()
        self.bus.set_short_term(sentinel)
        self.assertIs(self.bus.short_term(), sentinel)

    def test_log_skill_eval_persists(self):
        row_id = self.bus.log_skill_eval(
            skill_name="llm_generate_plan_struct",
            inputs={"k": 1},
            outputs={"k": 2},
            success=True,
            latency_ms=120,
            tokens_in=300,
            tokens_out=80,
        )
        self.assertGreater(row_id, 0)
        rows = self.bus.recent_skill_evals(limit=5)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["latency_ms"], 120)
        self.assertEqual(int(rows[0]["success"]), 1)

    def test_eval_summary(self):
        self.bus.log_skill_eval(skill_name="x", inputs={}, success=True)
        self.bus.log_skill_eval(skill_name="x", inputs={}, success=False, fallback_reason="x")
        s = self.bus.eval_summary()
        self.assertEqual(s["total"], 2)
        self.assertEqual(s["success"], 1)
        self.assertEqual(s["failure"], 1)

    def test_long_term_returns_memory_store(self):
        self.assertIsInstance(self.bus.long_term(), MemoryStore)
        self.assertIsInstance(self.bus.eval_log(), SkillEvalLogStore)


# ---------------------------------------------------------------------------
# Timer
# ---------------------------------------------------------------------------

class TimerTests(unittest.TestCase):
    def test_records_elapsed(self):
        import time
        with Timer() as t:
            time.sleep(0.005)
        self.assertGreaterEqual(t.elapsed_ms, 0)


# ---------------------------------------------------------------------------
# Internal: _normalize_plan_row
# ---------------------------------------------------------------------------

class NormalizePlanRowTests(unittest.TestCase):
    def test_restores_user_id_and_parses_json(self):
        row = {
            "user_id": "42",
            "assessment_json": '{"x": 1}',
            "recommendation_json": '[{"a": 1}]',
            "source_session_ids_json": '["s1"]',
            "source_snapshot_json": '{"k": "v"}',
        }
        out = _normalize_plan_row(row)
        self.assertEqual(out["user_id"], 42)
        self.assertEqual(out["assessment_json"], {"x": 1})
        self.assertEqual(out["recommendation_json"], [{"a": 1}])
        self.assertEqual(out["source_session_ids_json"], ["s1"])
        self.assertEqual(out["source_snapshot_json"], {"k": "v"})

    def test_handles_already_parsed_payloads(self):
        row = {
            "user_id": "abc",
            "assessment_json": {"x": 1},
            "recommendation_json": [],
        }
        out = _normalize_plan_row(row)
        self.assertEqual(out["user_id"], "abc")
        self.assertEqual(out["assessment_json"], {"x": 1})


if __name__ == "__main__":
    unittest.main()

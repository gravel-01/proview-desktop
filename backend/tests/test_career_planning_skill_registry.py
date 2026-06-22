"""Unit tests for the career planning skill registry (phase 3).

Exercises:
- :class:`Skill` construction and validation
- :class:`SkillRegistry` registration, lookup, upgrade, unregister
- :meth:`SkillRegistry.run` happy + error paths
- :class:`SkillEvaluator` matcher contract
- :func:`default_registry` pre-registered phase 2 skills
- :func:`register_phase2_pure_skills` integration with the LLM skill group
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

from services.career_planning_skill_registry import (
    SKILL_KIND_LLM,
    SKILL_KIND_PURE_FUNCTION,
    Skill,
    SkillEvalCase,
    SkillEvaluator,
    SkillEvalSummary,
    SkillRegistry,
    SkillRunResult,
    default_registry,
    register_phase2_pure_skills,
    _hash_payload,
    _matches,
)


# ---------------------------------------------------------------------------
# Skill dataclass
# ---------------------------------------------------------------------------

class SkillConstructionTests(unittest.TestCase):
    def test_rejects_invalid_kind(self):
        with self.assertRaises(ValueError):
            Skill(
                name="x",
                version="v1",
                kind="unknown",
                description="x",
                handler=lambda: None,
            )

    def test_rejects_non_callable_handler(self):
        with self.assertRaises(TypeError):
            Skill(
                name="x",
                version="v1",
                kind=SKILL_KIND_PURE_FUNCTION,
                description="x",
                handler="not callable",
            )

    def test_accepts_valid_skill(self):
        skill = Skill(
            name="x",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="x",
            handler=lambda: 1,
        )
        self.assertEqual(skill.name, "x")
        self.assertEqual(skill.kind, SKILL_KIND_PURE_FUNCTION)


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class _StubBus:
    """Tiny bus stub: records every log_skill_eval call."""

    def __init__(self):
        self.records = []

    def log_skill_eval(self, **kwargs):
        self.records.append(kwargs)
        return len(self.records)


class SkillRegistryTests(unittest.TestCase):
    def setUp(self):
        self.bus = _StubBus()
        self.registry = SkillRegistry(memory_bus=self.bus)

    def test_register_and_get(self):
        skill = Skill(
            name="echo", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="echo", handler=lambda x: x,
        )
        self.registry.register(skill)
        self.assertIs(self.registry.get("echo").handler, skill.handler)
        self.assertIn("echo", [s["name"] for s in self.registry.list()])

    def test_register_duplicate_raises(self):
        skill = Skill(
            name="dup", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda: 1,
        )
        self.registry.register(skill)
        with self.assertRaises(ValueError):
            self.registry.register(skill)

    def test_upgrade_switches_active_version(self):
        self.registry.register(Skill(
            name="v", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda: 1,
        ))
        self.registry.register(Skill(
            name="v", version="v2", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda: 2,
        ), activate=False)
        self.assertEqual(self.registry.get("v").version, "v1")
        self.registry.upgrade("v", "v2")
        self.assertEqual(self.registry.get("v").version, "v2")

    def test_upgrade_unknown_raises(self):
        with self.assertRaises(KeyError):
            self.registry.upgrade("missing", "v9")

    def test_unregister_removes_skill(self):
        self.registry.register(Skill(
            name="u", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda: 1,
        ))
        self.registry.unregister("u")
        with self.assertRaises(KeyError):
            self.registry.get("u")

    def test_run_happy_path(self):
        self.registry.register(Skill(
            name="add", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda a, b: a + b,
        ))
        result = self.registry.run("add", a=2, b=3, log_eval=False)
        self.assertTrue(result.success)
        self.assertEqual(result.output, 5)
        self.assertGreaterEqual(result.latency_ms, 0)
        self.assertEqual(len(self.bus.records), 0)  # log_eval=False

    def test_run_records_eval_log(self):
        self.registry.register(Skill(
            name="x", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda: 42,
        ))
        self.registry.run("x", log_eval=True)
        self.assertEqual(len(self.bus.records), 1)
        self.assertEqual(self.bus.records[0]["skill_name"], "x")
        self.assertTrue(self.bus.records[0]["success"])

    def test_run_exception_is_caught(self):
        def boom():
            raise RuntimeError("nope")

        self.registry.register(Skill(
            name="boom", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=boom,
        ))
        result = self.registry.run("boom", log_eval=True)
        self.assertFalse(result.success)
        self.assertIn("nope", result.error)
        # error is reported as fallback_reason
        self.assertEqual(self.bus.records[0]["fallback_reason"], "nope")

    def test_get_unknown_raises(self):
        with self.assertRaises(KeyError):
            self.registry.get("nope")

    def test_list_returns_active_flag(self):
        self.registry.register(Skill(
            name="a", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda: 1,
        ))
        self.registry.register(Skill(
            name="a", version="v2", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda: 2,
        ), activate=False)
        rows = self.registry.list()
        by_version = {(r["name"], r["version"]): r for r in rows}
        # v1 was registered first with activate=True (default) so it remains active.
        self.assertEqual(by_version[("a", "v1")]["active"], "1")
        # v2 was registered with activate=False so it is inactive.
        self.assertEqual(by_version[("a", "v2")]["active"], "0")


# ---------------------------------------------------------------------------
# SkillEvaluator
# ---------------------------------------------------------------------------

class SkillEvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.bus = _StubBus()
        self.registry = SkillRegistry(memory_bus=self.bus)
        self.registry.register(Skill(
            name="add", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda a, b: a + b,
        ))
        self.evaluator = SkillEvaluator(self.registry)

    def test_evaluator_with_subset_matcher(self):
        cases = [
            {"inputs": {"a": 1, "b": 2}, "expected": {"result": 3}, "matcher": "subset"},
        ]
        # The "subset" matcher checks expected dict subset of output dict.
        # Our handler returns a plain int, so this should fail.
        summaries = self.evaluator.evaluate({"add": cases})
        self.assertEqual(summaries[0].total, 1)
        self.assertEqual(summaries[0].passed, 0)

    def test_evaluator_callable_matcher(self):
        cases = [
            {
                "inputs": {"a": 2, "b": 3},
                "expected": lambda output: output == 5,
                "matcher": "callable",
            }
        ]
        summaries = self.evaluator.evaluate({"add": cases})
        self.assertEqual(summaries[0].passed, 1)
        self.assertEqual(summaries[0].failed, 0)
        self.assertEqual(summaries[0].pass_rate, 1.0)

    def test_evaluator_contains_keys_matcher(self):
        self.registry.register(Skill(
            name="kv", version="v1", kind=SKILL_KIND_PURE_FUNCTION,
            description="x", handler=lambda **kw: kw,
        ))
        cases = [
            {"inputs": {"a": 1, "b": 2}, "expected": {"a": 1}, "matcher": "contains_keys"},
        ]
        summaries = self.evaluator.evaluate({"kv": cases})
        self.assertEqual(summaries[0].passed, 1)

    def test_eval_summary_dataclass(self):
        s = SkillEvalSummary(
            name="x", version="v1", total=2, passed=1, failed=1, avg_latency_ms=12.5
        )
        self.assertEqual(s.pass_rate, 0.5)


# ---------------------------------------------------------------------------
# Default registry + phase 2 skills
# ---------------------------------------------------------------------------

class DefaultRegistryTests(unittest.TestCase):
    def test_default_registry_has_phase2_skills(self):
        reg = default_registry()
        names = [item["name"] for item in reg.list()]
        for expected in (
            "compute_dimension_stats",
            "derive_gap_severity",
            "extract_resume_gap_signals",
            "build_evidence_aware_tasks",
            "select_top_evidence",
            "select_top_suggestions",
            "summarize_context_for_llm",
        ):
            self.assertIn(expected, names)

    def test_phase2_skills_can_be_invoked(self):
        reg = default_registry()
        # derive_gap_severity is a tiny pure function
        from services.career_planning_skills import derive_gap_severity
        result = reg.run("derive_gap_severity", avg_score=4.0, evaluation_count=5, log_eval=False)
        self.assertTrue(result.success)
        self.assertEqual(result.output, "high")

    def test_register_phase2_skills_idempotent(self):
        """Re-registering the phase 2/4 skill set is a no-op (safe boot path)."""
        reg = SkillRegistry()
        register_phase2_pure_skills(reg)
        # Calling twice should not raise; the registry stays consistent.
        register_phase2_pure_skills(reg)
        register_phase2_pure_skills(reg)
        # 7 phase-2 deterministic skills + 3 phase-4 resource-closure
        # skills are registered, each only once.
        self.assertEqual(len(reg.list()), 10)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class HashPayloadTests(unittest.TestCase):
    def test_hash_is_stable(self):
        h1 = _hash_payload({"a": 1, "b": [1, 2]})
        h2 = _hash_payload({"a": 1, "b": [1, 2]})
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)

    def test_hash_ignores_key_order(self):
        h1 = _hash_payload({"a": 1, "b": 2})
        h2 = _hash_payload({"b": 2, "a": 1})
        self.assertEqual(h1, h2)


class MatcherTests(unittest.TestCase):
    def test_subset_matcher(self):
        self.assertTrue(_matches({"a": 1}, {"a": 1, "b": 2}, "subset"))
        self.assertFalse(_matches({"a": 2}, {"a": 1, "b": 2}, "subset"))

    def test_exact_matcher(self):
        self.assertTrue(_matches({"a": 1}, {"a": 1}, "exact"))
        self.assertFalse(_matches({"a": 1}, {"a": 1, "b": 2}, "exact"))

    def test_callable_matcher(self):
        self.assertTrue(_matches(lambda x: x > 5, 10, "callable"))
        self.assertFalse(_matches(lambda x: x > 5, 1, "callable"))


if __name__ == "__main__":
    unittest.main()

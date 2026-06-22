"""Unit tests for the LLM-driven career plan generator (phase 3).

These tests cover the deterministic contract of the
:class:`CareerPlanLLMGenerator` without ever hitting a real LLM. They
exercise:

- prompt rendering (anti-hallucination guardrails present)
- prompt hashing is stable for identical inputs
- JSON extraction (direct, fenced, partial)
- schema validation (positive and negative)
- reference validation (unknown dimension / session id rejected)
- MockLLMClient contract (exception, raw dict, callable)
- fallback on every failure mode
- success path populates metadata + logs an eval record
- Skill registration via attach_llm_skills
- Integration: the structured plan is consumable by CareerPlanningService
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.career_planning_context import (
    BuildMeta,
    CareerContext,
    ContextSummary,
    DataFreshness,
    ResumeSummary,
    SessionContext,
    TurnEvaluationLite,
)
from services.career_planning_llm import (
    CareerPlanLLMGenerator,
    GenerationStats,
    MockLLMClient,
    attach_llm_skills,
)
from services.career_planning_memory import (
    MemoryBus,
    MemoryStore,
    SkillEvalLogStore,
)
from services.career_planning_schema import (
    GenerationOutcome,
    compute_prompt_hash,
    data_to_career_plan_structured,
    extract_json_object,
    parse_career_plan_structured,
    validate_references,
    validate_with_schema,
    CAREER_PLAN_STRUCTURED_SCHEMA,
    VALID_SEVERITY,
    VALID_TASK_TYPE,
)
from services.career_planning_skill_registry import (
    SKILL_KIND_LLM,
    SkillRegistry,
    default_registry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_session_context() -> SessionContext:
    return SessionContext(
        session_id="sess-1",
        position="高级前端开发工程师",
        status="completed",
        interview_style="技术面",
        start_time="2026-01-01T10:00:00Z",
        end_time="2026-01-01T11:00:00Z",
        turn_count=4,
        answered_turn_count=4,
        evaluation_count=4,
        question_metadata_count=2,
        avg_score=7.0,
        eval_strengths="沟通表达 ok",
        eval_weaknesses="系统设计 弱",
        eval_summary="整体中等",
        top_dimensions=["沟通表达", "系统设计"],
        evaluations=[
            TurnEvaluationLite(
                evaluation_id="e1",
                session_id="sess-1",
                turn_id="t1",
                turn_no=1,
                dimension="系统设计",
                score=5,
                pass_level="fail",
                evidence="对缓存一致性方案理解不够",
                suggestion="补齐缓存模式",
            ),
            TurnEvaluationLite(
                evaluation_id="e2",
                session_id="sess-1",
                turn_id="t2",
                turn_no=2,
                dimension="沟通表达",
                score=8,
                pass_level="pass",
                evidence="表达清晰",
                suggestion="继续保持",
            ),
        ],
        question_metadata=[],
        capabilities={
            "structured_turns": True,
            "turn_evaluations": True,
            "question_metadata": True,
        },
    )


def _make_context() -> CareerContext:
    session = _make_session_context()
    summary = ContextSummary(
        session_count=1,
        completed_session_count=1,
        turn_count=4,
        answered_turn_count=4,
        evaluation_count=4,
        low_score_evaluation_count=1,
        question_metadata_count=2,
        avg_score=7.0,
        has_resume=True,
        has_any_evidence=True,
        has_question_metadata=True,
        resume_gap_signal_count=1,
    )
    build_meta = BuildMeta(
        built_at="2026-01-01T10:00:00Z",
        session_limit=6,
        evaluation_limit_per_session=8,
        question_meta_limit_per_session=12,
        truncated_sessions=0,
        data_client_kind="sqlite",
        has_turn_evaluation_capability=True,
        has_question_metadata_capability=True,
        has_turn_capability=True,
    )
    return CareerContext(
        target_role="高级前端开发工程师",
        horizon_months=6,
        resume_summary=ResumeSummary(
            has_resume=True,
            file_name="resume.pdf",
            resume_id=1,
            upload_time="2026-01-01T00:00:00Z",
            ocr_length=1200,
            ocr_preview="前端开发经验...",
            gap_signals=["工程化基础薄弱"],
        ),
        sessions=[session],
        summary=summary,
        dimension_stats=[
            # Lightweight stand-in; full stats are exercised in career_planning_skills tests.
        ],
        evidence_samples=[
            {
                "dimension": "系统设计",
                "score": 5,
                "session_id": "sess-1",
                "turn_no": 1,
                "evidence": "对缓存一致性方案理解不够",
            }
        ],
        suggestion_samples=[
            {
                "dimension": "系统设计",
                "session_id": "sess-1",
                "text": "补齐缓存模式与高可用设计",
            }
        ],
        data_freshness=DataFreshness(
            latest_session_id="sess-1",
            latest_session_at="2026-01-01T11:00:00Z",
            earliest_session_at="2026-01-01T10:00:00Z",
        ),
        build_meta=build_meta,
    )


def _good_structured_payload() -> Dict[str, Any]:
    return {
        "profile": {
            "current_stage": "打基础",
            "overall_score": 6.5,
            "gap_tags": ["系统设计", "工程化基础薄弱"],
            "strength_tags": ["沟通表达"],
            "summary": "围绕高级前端开发工程师目标，需补齐系统设计短板。",
            "generation_mode": "llm",
        },
        "gaps": [
            {
                "key": "system_design",
                "label": "系统设计",
                "severity": "high",
                "dimension": "系统设计",
                "evidence_session_ids": ["sess-1"],
                "evidence_quotes": ["对缓存一致性方案理解不够"],
                "recommended_action": "补齐缓存模式与高可用设计。",
            }
        ],
        "milestones": [
            {
                "sort_order": 1,
                "title": "夯实基础",
                "month": 1,
                "description": "梳理目标岗位能力地图，补齐系统设计。",
                "success_criteria": "完成 1 次完整的系统设计模拟。",
                "focus_gaps": ["system_design"],
            },
            {
                "sort_order": 2,
                "title": "形成作品",
                "month": 3,
                "description": "完成 1 个高质量项目。",
                "success_criteria": "形成可讲述的项目复盘。",
                "focus_gaps": ["system_design"],
            },
            {
                "sort_order": 3,
                "title": "冲刺岗位",
                "month": 6,
                "description": "完成模拟面试。",
                "success_criteria": "通过至少 1 次模拟面试。",
                "focus_gaps": [],
            },
        ],
        "tasks": [
            {
                "title": "补齐系统设计",
                "description": "完成 5 道系统设计题。",
                "task_type": "skill_practice",
                "priority": 5,
                "gap_key": "system_design",
                "estimated_effort": "4 周",
                "success_criteria": "完成 5 道题并复盘。",
                "source_evidence": [
                    {
                        "session_id": "sess-1",
                        "turn_no": 1,
                        "score": 5,
                        "quote": "对缓存一致性方案理解不够",
                    }
                ],
                "resource_refs": [],
            }
        ],
        "recommendations": [
            {
                "type": "course",
                "title": "系统设计课程",
                "reason": "针对系统设计 gap。",
                "url": "",
            }
        ],
    }


# ---------------------------------------------------------------------------
# JSON extraction & schema validation
# ---------------------------------------------------------------------------

class JsonExtractionTests(unittest.TestCase):
    def test_extract_direct_json(self):
        text = json.dumps({"a": 1, "b": [1, 2, 3]}, ensure_ascii=False)
        out = extract_json_object(text)
        self.assertEqual(out, {"a": 1, "b": [1, 2, 3]})

    def test_extract_fenced_json(self):
        text = "```json\n{\"a\": 2}\n```"
        out = extract_json_object(text)
        self.assertEqual(out, {"a": 2})

    def test_extract_first_last_brace(self):
        # The implementation picks the first '{' to last '}'. Use a
        # snippet that is parseable end-to-end.
        text = 'noise prefix {"k": 1, "list": [1, 2]} trailing'
        out = extract_json_object(text)
        self.assertEqual(out, {"k": 1, "list": [1, 2]})

    def test_extract_returns_none_on_unparseable_brace_pair(self):
        # Multi-brace content that cannot be parsed as a single object
        # should return None rather than crash.
        text = "{ not json } middle { broken }"
        out = extract_json_object(text)
        self.assertIsNone(out)

    def test_extract_returns_none_on_garbage(self):
        self.assertIsNone(extract_json_object(""))

    def test_extract_returns_none_on_unparseable(self):
        self.assertIsNone(extract_json_object("just a string"))


class SchemaValidationTests(unittest.TestCase):
    def setUp(self):
        self.payload = _good_structured_payload()

    def test_accepts_well_formed_payload(self):
        ok, reason = validate_with_schema(self.payload)
        self.assertTrue(ok, reason)
        self.assertEqual(reason, "")

    def test_rejects_missing_profile(self):
        broken = dict(self.payload)
        broken["profile"] = {"current_stage": "打基础"}
        ok, reason = validate_with_schema(broken)
        self.assertFalse(ok)
        # jsonschema uses "required property" wording; manual fallback uses "missing_"
        self.assertTrue("required property" in reason or "missing" in reason, reason)

    def test_rejects_invalid_severity(self):
        broken = json.loads(json.dumps(self.payload))
        broken["gaps"][0]["severity"] = "very_high"
        ok, reason = validate_with_schema(broken)
        self.assertFalse(ok)
        # jsonschema enumerates the bad value; manual fallback uses "severity"
        self.assertTrue("severity" in reason or "very_high" in reason, reason)

    def test_rejects_task_without_evidence(self):
        broken = json.loads(json.dumps(self.payload))
        broken["tasks"][0]["source_evidence"] = []
        ok, reason = validate_with_schema(broken)
        self.assertFalse(ok)
        # jsonschema says "too short"; manual fallback says "task_no_evidence"
        self.assertTrue("task_no_evidence" in reason or "too short" in reason, reason)

    def test_rejects_invalid_task_type(self):
        broken = json.loads(json.dumps(self.payload))
        broken["tasks"][0]["task_type"] = "magic"
        ok, reason = validate_with_schema(broken)
        self.assertFalse(ok)

    def test_rejects_score_out_of_range(self):
        broken = json.loads(json.dumps(self.payload))
        broken["profile"]["overall_score"] = 11
        ok, reason = validate_with_schema(broken)
        self.assertFalse(ok)

    def test_severity_and_task_type_enums(self):
        # Direct check on schema enums to ensure contract.
        self.assertIn("high", VALID_SEVERITY)
        self.assertIn("skill_practice", VALID_TASK_TYPE)


class ReferenceValidationTests(unittest.TestCase):
    def setUp(self):
        self.context = _make_context()
        self.payload = _good_structured_payload()

    def test_accepts_references_against_context(self):
        plan = data_to_career_plan_structured(self.payload)
        ok, reason = validate_references(plan, self.context)
        self.assertTrue(ok, reason)

    def test_rejects_unknown_session_id(self):
        plan = data_to_career_plan_structured(self.payload)
        # Tamper: change the source_evidence session id to something the
        # context has not seen.
        plan = type(plan)(
            **{**plan.__dict__, "tasks": [
                type(plan.tasks[0])(
                    **{**plan.tasks[0].__dict__, "source_evidence": [
                        {"session_id": "ghost", "turn_no": 1, "score": 5, "quote": "x"}
                    ]}
                )
            ]}
        )
        ok, reason = validate_references(plan, self.context)
        self.assertFalse(ok)
        self.assertIn("session", reason)

    def test_rejects_unknown_dimension(self):
        plan = data_to_career_plan_structured(self.payload)
        # Forge a gap with a dimension not in DIMENSION_LIBRARY
        bad_gap = type(plan.gaps[0])(
            **{**plan.gaps[0].__dict__, "dimension": "魔法维度"}
        )
        plan = type(plan)(**{**plan.__dict__, "gaps": [bad_gap]})
        ok, reason = validate_references(plan, self.context)
        self.assertFalse(ok)


# ---------------------------------------------------------------------------
# parse_career_plan_structured (end-to-end)
# ---------------------------------------------------------------------------

class ParseStructuredTests(unittest.TestCase):
    def test_parses_valid_payload(self):
        raw = json.dumps(_good_structured_payload(), ensure_ascii=False)
        plan = parse_career_plan_structured(raw)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.profile.current_stage, "打基础")
        self.assertEqual(plan.profile.overall_score, 6.5)
        self.assertEqual(len(plan.gaps), 1)
        self.assertEqual(len(plan.milestones), 3)
        self.assertEqual(len(plan.tasks), 1)
        self.assertEqual(len(plan.recommendations), 1)
        self.assertEqual(plan.gaps[0].dimension, "系统设计")

    def test_returns_none_on_invalid_json(self):
        self.assertIsNone(parse_career_plan_structured("not json"))

    def test_returns_none_on_schema_violation(self):
        payload = _good_structured_payload()
        payload["tasks"][0]["task_type"] = "magic"
        raw = json.dumps(payload, ensure_ascii=False)
        self.assertIsNone(parse_career_plan_structured(raw))


# ---------------------------------------------------------------------------
# Prompt hashing
# ---------------------------------------------------------------------------

class PromptHashTests(unittest.TestCase):
    def test_hash_is_stable(self):
        h1 = compute_prompt_hash("system", "user")
        h2 = compute_prompt_hash("system", "user")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 16)

    def test_hash_changes_with_input(self):
        h1 = compute_prompt_hash("a", "b")
        h2 = compute_prompt_hash("a", "c")
        self.assertNotEqual(h1, h2)


# ---------------------------------------------------------------------------
# CareerPlanLLMGenerator happy path with MockLLMClient
# ---------------------------------------------------------------------------

class _StubService:
    """Minimal service stub that satisfies :class:`MemoryBus` contract."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        # A persistent connection helper compatible with CareerPlanningService.
        from contextlib import contextmanager
        import sqlite3
        self._sqlite3 = sqlite3

        @contextmanager
        def _managed_connection():
            conn = sqlite3.connect(str(db_path), timeout=30)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self._managed_connection = _managed_connection


class CareerPlanLLMGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(__file__).resolve().parent / ".codex_tmp_llm_unit"
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.context = _make_context()
        self.service = _StubService(self.temp_dir / "memory.sqlite3")
        self.memory_bus = MemoryBus(service=self.service)
        self.mock_client = MockLLMClient(response=_good_structured_payload())
        self.generator = CareerPlanLLMGenerator(
            llm_client=self.mock_client,
            memory_bus=self.memory_bus,
        )

    def tearDown(self):
        self.generator = None
        self.mock_client = None
        self.memory_bus = None
        self.service = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_returns_successful_outcome(self):
        outcome = self.generator.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
            blueprint_milestones=[
                {"month": 1, "title": "夯实基础"},
                {"month": 3, "title": "形成作品"},
                {"month": 6, "title": "冲刺岗位"},
            ],
        )
        self.assertTrue(outcome.success)
        self.assertIsNotNone(outcome.plan)
        # Mock client is sub-millisecond; latency must be non-negative.
        self.assertGreaterEqual(outcome.latency_ms, 0)
        self.assertEqual(outcome.model_id, "mock-llm")
        self.assertEqual(len(outcome.prompt_hash), 16)
        # structured plan is consumable
        self.assertEqual(outcome.plan.profile.current_stage, "打基础")
        # prompt is recorded
        self.assertEqual(len(self.mock_client.calls), 1)
        msgs = self.mock_client.calls[0]
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[1]["role"], "user")
        # skill eval is logged
        rows = self.memory_bus.eval_log().read(limit=10)
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(rows[0]["skill_name"], "llm_generate_plan_struct")
        self.assertEqual(int(rows[0]["success"]), 1)

    def test_generate_handles_fenced_json(self):
        payload = _good_structured_payload()
        client = MockLLMClient(
            response="```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
        )
        gen = CareerPlanLLMGenerator(llm_client=client, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
            blueprint_milestones=[{"month": 1, "title": "x"}] * 3,
        )
        self.assertTrue(outcome.success)

    def test_generate_fails_on_bad_json(self):
        client = MockLLMClient(response="not a json")
        gen = CareerPlanLLMGenerator(llm_client=client, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
        )
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.fallback_reason, "parse_or_schema_error")
        rows = self.memory_bus.eval_log().read(limit=10)
        self.assertEqual(int(rows[0]["success"]), 0)

    def test_generate_fails_on_schema_violation(self):
        bad = _good_structured_payload()
        bad["tasks"][0]["task_type"] = "magic"
        client = MockLLMClient(response=bad)
        gen = CareerPlanLLMGenerator(llm_client=client, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
        )
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.fallback_reason, "parse_or_schema_error")

    def test_generate_fails_on_unknown_reference(self):
        bad = _good_structured_payload()
        bad["tasks"][0]["source_evidence"][0]["session_id"] = "ghost-session"
        client = MockLLMClient(response=bad)
        gen = CareerPlanLLMGenerator(llm_client=client, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
        )
        self.assertFalse(outcome.success)
        self.assertIn("reference_invalid", outcome.fallback_reason)

    def test_generate_fails_when_client_raises(self):
        client = MockLLMClient(raise_exc=RuntimeError("network"))
        gen = CareerPlanLLMGenerator(llm_client=client, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
        )
        self.assertFalse(outcome.success)
        self.assertIn("llm_exception", outcome.fallback_reason)

    def test_generate_fails_when_no_client(self):
        gen = CareerPlanLLMGenerator(llm_client=None, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
        )
        self.assertFalse(outcome.success)
        self.assertEqual(outcome.fallback_reason, "llm_unavailable")

    def test_generate_normalises_milestone_count(self):
        # LLM only returns 2 milestones; the service expects 3. The 3rd
        # should be backfilled from the blueprint.
        short = json.loads(json.dumps(_good_structured_payload()))
        short["milestones"] = short["milestones"][:2]
        client = MockLLMClient(response=short)
        gen = CareerPlanLLMGenerator(llm_client=client, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
            blueprint_milestones=[
                {"month": 1, "title": "夯实基础", "description": "step 1"},
                {"month": 3, "title": "形成作品", "description": "step 2"},
                {"month": 6, "title": "冲刺岗位", "description": "step 3"},
            ],
        )
        self.assertTrue(outcome.success)
        self.assertEqual(len(outcome.plan.milestones), 3)
        # Third milestone is the backfilled one from the blueprint
        self.assertEqual(outcome.plan.milestones[2].sort_order, 3)

    def test_generate_rejects_when_too_few_tasks(self):
        # Strip the task entirely; schema requires >=1 but per-milestone
        # coverage would also fail; the test should expose the failure.
        bad = json.loads(json.dumps(_good_structured_payload()))
        bad["tasks"] = []
        client = MockLLMClient(response=bad)
        gen = CareerPlanLLMGenerator(llm_client=client, memory_bus=self.memory_bus)
        outcome = gen.generate(
            context=self.context,
            target_role="高级前端开发工程师",
            horizon_months=6,
        )
        # Schema enforces minItems:1 on tasks => parse failure.
        self.assertFalse(outcome.success)


# ---------------------------------------------------------------------------
# Skill registration
# ---------------------------------------------------------------------------

class SkillRegistrationTests(unittest.TestCase):
    def test_attach_llm_skills_registers_one_skill(self):
        reg = SkillRegistry()
        gen = CareerPlanLLMGenerator(llm_client=MockLLMClient(response={}))
        attach_llm_skills(reg, gen)
        listed = reg.list()
        names = [item["name"] for item in listed]
        self.assertIn("llm_generate_plan_struct", names)
        kinds = [item["kind"] for item in listed]
        self.assertIn(SKILL_KIND_LLM, kinds)

    def test_registered_skill_invocation_calls_generate(self):
        reg = SkillRegistry()
        gen = CareerPlanLLMGenerator(llm_client=MockLLMClient(response=_good_structured_payload()))
        attach_llm_skills(reg, gen)
        result = reg.run("llm_generate_plan_struct", context=_make_context(), target_role="高级前端开发工程师", horizon_months=6, log_eval=False)
        self.assertTrue(result.success)
        self.assertTrue(isinstance(result.output, GenerationOutcome))


# ---------------------------------------------------------------------------
# Service integration (LLM happy path + fallback)
# ---------------------------------------------------------------------------

class CareerPlanningServiceLLMIntegrationTests(unittest.TestCase):
    """End-to-end: wire the generator into the service and assert that the
    LLM path populates structured rows + audit columns, and the fallback
    path leaves the deterministic templates intact."""

    def setUp(self):
        from services.career_planning_service import CareerPlanningService

        self.temp_dir = Path(__file__).resolve().parent / ".codex_tmp_llm_int"
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.data_client = _MockDataClient()
        self.memory_bus = MemoryBus(service=_StubService(self.temp_dir / "memory.sqlite3"))
        self.mock_client = MockLLMClient(response=_good_structured_payload())
        self.generator = CareerPlanLLMGenerator(
            llm_client=self.mock_client,
            memory_bus=self.memory_bus,
        )
        self.service = CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career.sqlite3"),
            llm_generator=self.generator,
        )

    def tearDown(self):
        self.service = None
        self.generator = None
        self.mock_client = None
        self.memory_bus = None
        self.data_client = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_llm_path_persists_structured_plan(self):
        result = self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )

        self.assertTrue(result["llm"]["attempted"])
        self.assertTrue(result["llm"]["succeeded"])
        self.assertEqual(result["llm"]["model_id"], "mock-llm")
        # LLM-generated milestone title should override the blueprint
        titles = [m["title"] for m in result["milestones"]]
        self.assertIn("夯实基础", titles)
        # Profile metadata is augmented
        self.assertEqual(result["profile"]["llm_model_id"], "mock-llm")
        self.assertEqual(len(result["profile"]["llm_prompt_hash"]), 16)
        # Skill eval log is written
        rows = self.memory_bus.eval_log().read(limit=10)
        self.assertGreaterEqual(len(rows), 1)

    def test_fallback_path_keeps_deterministic_output(self):
        # Wire a generator that always fails (raises).
        failing = CareerPlanLLMGenerator(
            llm_client=MockLLMClient(raise_exc=RuntimeError("network")),
            memory_bus=self.memory_bus,
        )
        svc = self._build_service_with_generator(failing)
        result = svc.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        self.assertTrue(result["llm"]["attempted"])
        self.assertFalse(result["llm"]["succeeded"])
        self.assertIn("llm_exception", result["llm"]["fallback_reason"])
        # profile should not carry the LLM metadata
        self.assertEqual(result["profile"].get("llm_model_id", ""), "")
        # plan was still created (phase 2 fallback)
        self.assertGreaterEqual(len(result["milestones"]), 1)
        self.assertGreaterEqual(len(result["tasks"]), 1)

    def test_no_generator_runs_legacy_path(self):
        # Fresh service with no LLM generator
        from services.career_planning_service import CareerPlanningService
        svc = CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career-legacy.sqlite3"),
        )
        result = svc.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            refresh=True,
        )
        self.assertFalse(result["llm"]["attempted"])
        self.assertFalse(result["llm"]["succeeded"])
        self.assertGreaterEqual(len(result["milestones"]), 1)

    # ------------------------------------------------------------------

    def _build_service_with_generator(self, generator):
        from services.career_planning_service import CareerPlanningService
        return CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career-fb.sqlite3"),
            llm_generator=generator,
        )


class _MockDataClient:
    """Minimal data client stub compatible with the service / context aggregator."""

    def __init__(self):
        self.get_user = MagicMock(return_value={"id": 1})
        self.get_or_create_local_user = MagicMock(
            return_value={"id": 1, "username": "本地用户", "display_name": "本地用户"}
        )
        self.get_latest_resume = MagicMock(
            return_value={"file_name": "resume.pdf", "title": "后端工程师简历"}
        )
        self.list_sessions = MagicMock(return_value=[
            {
                "session_id": "sess-1",
                "status": "completed",
                "position": "高级前端开发工程师",
            }
        ])
        self.get_session_statistics = MagicMock(return_value={
            "turn_count": 4,
            "evaluations": [
                {"dimension": "系统设计", "score": 5, "comment": "gap"},
                {"dimension": "沟通表达", "score": 8, "comment": "ok"},
            ],
            "avg_score": 6.5,
        })
        # Optional APIs the aggregator may probe for.
        self.get_turn_evaluations = MagicMock(return_value=[])
        self.get_question_metadata = MagicMock(return_value=[])


# ---------------------------------------------------------------------------
# Schema enum smoke checks
# ---------------------------------------------------------------------------

class SchemaContractTests(unittest.TestCase):
    def test_schema_required_keys(self):
        required = set(CAREER_PLAN_STRUCTURED_SCHEMA.get("required") or [])
        self.assertEqual(
            required,
            {"profile", "gaps", "milestones", "tasks", "recommendations"},
        )

    def test_schema_profile_subshape(self):
        profile = CAREER_PLAN_STRUCTURED_SCHEMA["properties"]["profile"]
        self.assertIn("current_stage", profile["required"])
        self.assertIn("overall_score", profile["required"])


if __name__ == "__main__":
    unittest.main()

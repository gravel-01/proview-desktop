import os
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import app as app_module
from services.career_planning_docs import CareerPlanningDocumentRepository
from services.career_planning_llm import (
    CareerPlanLLMGenerator,
    MockLLMClient,
    attach_llm_skills,
)
from services.career_planning_service import CareerPlanningService


def make_workspace_tempdir(name: str) -> Path:
    path = Path(__file__).resolve().parent / name
    shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


class MockDataClient:
    def __init__(self):
        self.get_user = MagicMock(return_value={"id": 1})
        self.get_or_create_local_user = MagicMock(return_value={"id": 1, "username": "本地用户", "display_name": "本地用户"})
        self.get_latest_resume = MagicMock(return_value={"file_name": "resume.pdf", "title": "后端工程师简历"})
        self.list_sessions = MagicMock(return_value=[
            {
                "session_id": "session-1",
                "status": "completed",
                "position": "高级前端开发工程师",
            }
        ])
        self.get_session_statistics = MagicMock(return_value={
            "turn_count": 4,
            "evaluations": [
                {"dimension": "表达", "score": 8, "comment": "good"},
                {"dimension": "系统设计", "score": 6, "comment": "gap"},
            ],
            "avg_score": 7.0,
        })


class EmptyContextDataClient(MockDataClient):
    def __init__(self):
        super().__init__()
        self.get_latest_resume = MagicMock(return_value=None)
        self.list_sessions = MagicMock(return_value=[])
        self.get_session_statistics = MagicMock(return_value={
            "turn_count": 0,
            "evaluations": [],
            "avg_score": 0,
        })


class CareerPlanningServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = make_workspace_tempdir(".codex_tmp_career_planning_service")
        self.data_client = MockDataClient()
        self.service = CareerPlanningService(self.data_client, db_path=str(self.temp_dir / "career.sqlite3"))

    def tearDown(self):
        self.service = None
        self.data_client = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_generate_plan_creates_persistent_dashboard(self):
        result = self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )

        self.assertEqual(result["profile"]["user_id"], 1)
        self.assertGreaterEqual(len(result["plans"]), 1)
        self.assertGreaterEqual(len(result["milestones"]), 1)
        self.assertGreaterEqual(len(result["tasks"]), 1)

        dashboard = self.service.build_dashboard(1)
        self.assertEqual(dashboard["stats"]["plan_count"], len(dashboard["plans"]))
        self.assertGreaterEqual(dashboard["stats"]["progress_rate"], 0)

    def test_update_task_rejects_unknown_task(self):
        self.assertIsNone(self.service.update_task(1, 999999, status="completed"))

    def test_horizon_months_are_clamped(self):
        result = self.service.generate_plan(user_id=1, horizon_months=99)
        self.assertLessEqual(result["current_plan"]["horizon_months"], 12)

    def test_generate_plan_reuses_active_plan_without_refresh(self):
        first = self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )

        second = self.service.generate_plan(user_id=1)

        self.assertEqual(len(second["plans"]), 1)
        self.assertEqual(first["current_plan"]["id"], second["current_plan"]["id"])

    def test_build_dashboard_returns_empty_state_when_target_role_missing(self):
        empty_service = CareerPlanningService(
            EmptyContextDataClient(),
            db_path=str(self.temp_dir / "career-empty.sqlite3"),
        )

        dashboard = empty_service.build_dashboard(1)

        self.assertEqual(dashboard["plans"], [])
        self.assertEqual(dashboard["tasks"], [])
        self.assertEqual(dashboard["stats"]["progress_rate"], 0)

    def test_profile_uses_empty_mode_when_no_resume_and_no_session(self):
        """第一阶段：无简历且无面试时，profile 不应伪造个性化结论，generation_mode='empty'。"""
        empty_service = CareerPlanningService(
            EmptyContextDataClient(),
            db_path=str(self.temp_dir / "career-no-context.sqlite3"),
        )
        # 显式提供 target_role 以绕过 ValueError
        result = empty_service.generate_plan(
            user_id=1, target_role="高级前端开发工程师", refresh=True,
        )
        profile = result["profile"]
        self.assertEqual(profile["generation_mode"], "empty")
        self.assertEqual(profile["has_resume"], False)
        self.assertEqual(profile["has_evaluations"], False)
        self.assertEqual(profile["session_count"], 0)
        import json as _json
        self.assertEqual(_json.loads(profile["gap_tags"]), [])
        self.assertEqual(_json.loads(profile["strength_tags"]), [])

    def test_profile_uses_fallback_mode_when_no_evaluations(self):
        """第一阶段：有面试无结构化评价时，profile 使用 fallback 模式且 gaps 为空。"""
        class NoEvalDataClient(MockDataClient):
            def get_session_statistics(self, session_id):
                return {"turn_count": 4, "evaluations": [], "avg_score": 0}

        no_eval = NoEvalDataClient()
        no_eval.get_session_statistics = lambda session_id: {"turn_count": 4, "evaluations": [], "avg_score": 0}
        svc = CareerPlanningService(
            no_eval,
            db_path=str(self.temp_dir / "career-no-eval.sqlite3"),
        )
        result = svc.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        profile = result["profile"]
        self.assertEqual(profile["generation_mode"], "fallback")
        self.assertEqual(profile["has_evaluations"], False)
        self.assertEqual(profile["evaluation_count"], 0)
        # gap_tags 应当为空（不强补模板）
        import json as _json
        self.assertEqual(_json.loads(profile["gap_tags"]), [])

    def test_milestone_status_syncs_after_task_completion(self):
        """第一阶段：完成任务后，对应 milestone 应自动变为 completed/in_progress。"""
        result = self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        first_task = result["tasks"][0]
        first_milestone_id = first_task["milestone_id"]
        before_status = next(m for m in result["milestones"] if m["id"] == first_milestone_id)["status"]
        self.assertEqual(before_status, "planned")

        # 完成该 milestone 下所有 task
        milestone_tasks = [t for t in result["tasks"] if t["milestone_id"] == first_milestone_id]
        for task in milestone_tasks:
            self.service.update_task(user_id=1, task_id=task["id"], status="completed", progress=100, note="done")

        # 重新拉 dashboard，milestone 状态应为 completed
        dashboard = self.service.build_dashboard(1)
        updated_milestone = next(m for m in dashboard["milestones"] if m["id"] == first_milestone_id)
        self.assertEqual(updated_milestone["status"], "completed")

    def test_milestone_status_in_progress_when_partial(self):
        """第一阶段：部分任务推进时，milestone 状态应为 in_progress。"""
        result = self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        first_task = result["tasks"][0]
        first_milestone_id = first_task["milestone_id"]
        # 只 +25%，不全完成
        self.service.update_task(user_id=1, task_id=first_task["id"], status="in_progress", progress=25, note="partial")
        dashboard = self.service.build_dashboard(1)
        updated_milestone = next(m for m in dashboard["milestones"] if m["id"] == first_milestone_id)
        self.assertEqual(updated_milestone["status"], "in_progress")


class CareerPlanningDocsRepositoryTests(unittest.TestCase):
    def test_loads_structured_documents(self):
        repository = CareerPlanningDocumentRepository()
        catalog = repository.get_catalog()

        self.assertIn("documents", catalog)
        self.assertEqual(len(catalog["documents"]), 3)
        self.assertIsNotNone(repository.get_document("job-seeking-guide"))
        self.assertIsNone(repository.get_document("missing"))


class CareerPlanningApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = make_workspace_tempdir(".codex_tmp_career_planning_api")
        self.data_client = MockDataClient()
        self.service = CareerPlanningService(self.data_client, db_path=str(self.temp_dir / "career.sqlite3"))

        app_module.STORAGE_AVAILABLE = True
        app_module.data_client = self.data_client
        app_module.career_planning_service = self.service
        self.client = app_module.app.test_client()

    def tearDown(self):
        self.client = None
        self.service = None
        self.data_client = None
        app_module.career_planning_service = None
        app_module.data_client = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _auth_headers(self):
        return {"Authorization": "Bearer session-token"}

    def test_docs_endpoint_uses_local_user_by_default(self):
        response = self.client.get('/api/career/docs')
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")

    def test_docs_endpoint_returns_catalog(self):
        response = self.client.get('/api/career/docs', headers=self._auth_headers())
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(len(payload["data"]["documents"]), 3)

    def test_doc_detail_endpoint_returns_specific_document(self):
        response = self.client.get('/api/career/docs/job-seeking-guide', headers=self._auth_headers())
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["id"], "job-seeking-guide")
        self.assertTrue(payload["data"]["sections"])

    def test_dashboard_endpoint_returns_generated_data(self):
        response = self.client.get('/api/career/dashboard', headers=self._auth_headers())
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertIn("profile", payload["data"])
        self.assertIn("plans", payload["data"])

    def test_dashboard_endpoint_returns_empty_state_without_target_role(self):
        empty_data_client = EmptyContextDataClient()
        empty_service = CareerPlanningService(
            empty_data_client,
            db_path=str(self.temp_dir / "career-empty-api.sqlite3"),
        )
        app_module.data_client = empty_data_client
        app_module.career_planning_service = empty_service

        response = self.client.get('/api/career/dashboard', headers=self._auth_headers())
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["data"]["plans"], [])
        self.assertEqual(payload["data"]["tasks"], [])

    def test_generate_plan_endpoint_creates_plan(self):
        response = self.client.post(
            '/api/career/plans/generate',
            headers=self._auth_headers(),
            json={"target_role": "高级前端开发工程师", "career_goal": "6 个月内拿到 offer", "horizon_months": 6, "refresh": True},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        self.assertGreaterEqual(len(payload["data"]["plans"]), 1)

    def test_generate_plan_endpoint_rejects_invalid_horizon_months(self):
        response = self.client.post(
            '/api/career/plans/generate',
            headers=self._auth_headers(),
            json={"target_role": "高级前端开发工程师", "career_goal": "6 个月内拿到 offer", "horizon_months": "invalid"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["status"], "error")

    def test_task_update_roundtrip_reflects_dashboard_state(self):
        generated = self.client.post(
            '/api/career/plans/generate',
            headers=self._auth_headers(),
            json={"target_role": "高级前端开发工程师", "career_goal": "6 个月内拿到 offer", "horizon_months": 6, "refresh": True},
        ).get_json()
        task_id = generated["data"]["tasks"][0]["id"]

        update_response = self.client.patch(
            f'/api/career/tasks/{task_id}',
            headers=self._auth_headers(),
            json={"status": "completed", "progress": 100, "note": "done"},
        )
        update_payload = update_response.get_json()

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(update_payload["status"], "success")
        self.assertEqual(update_payload["data"]["tasks"][0]["status"], "completed")
        self.assertGreaterEqual(update_payload["data"]["stats"]["completed_task_count"], 1)

    def test_task_update_requires_existing_task(self):
        response = self.client.patch(
            '/api/career/tasks/999999',
            headers=self._auth_headers(),
            json={"status": "completed", "progress": 100, "note": "done"},
        )
        payload = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["status"], "error")

    def test_task_update_uses_local_user_by_default(self):
        response = self.client.patch('/api/career/tasks/1', json={"status": "completed"})
        payload = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["status"], "error")


# ---------------------------------------------------------------------------
# Phase 3: LLM integration tests
# ---------------------------------------------------------------------------

def _good_llm_payload() -> dict:
    """Return a valid :class:`CareerPlanStructured` payload for the mock LLM."""
    return {
        "profile": {
            "current_stage": "打基础",
            "overall_score": 6.5,
            "gap_tags": ["系统设计"],
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
                "evidence_session_ids": ["session-1"],
                "evidence_quotes": [
                    "对缓存一致性方案理解不够",
                ],
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
                "focus_gaps": ["系统设计"],
            },
            {
                "sort_order": 2,
                "title": "形成作品",
                "month": 3,
                "description": "完成 1 个高质量项目。",
                "success_criteria": "形成可讲述的项目复盘。",
                "focus_gaps": ["系统设计"],
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
                "gap_key": "系统设计",
                "estimated_effort": "4 周",
                "success_criteria": "完成 5 道题并复盘。",
                "source_evidence": [
                    {
                        "session_id": "session-1",
                        "turn_no": 1,
                        "score": 6,
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


class CareerPlanningLLMIntegrationTests(unittest.TestCase):
    """End-to-end tests for the phase 3 LLM structured generation pipeline.

    These tests use a :class:`MockLLMClient` to drive the LLM pathway
    through the public ``generate_plan`` / ``build_dashboard`` API. They
    assert that:

    - LLM success surfaces ``generation_mode='llm'`` and LLM metadata
      on the profile / plan response.
    - LLM failure (exception, parse error, reference error) falls back
      to the phase 2 evidence-aware templates and ``generation_mode``
      stays ``'fallback'`` (or ``'evidence_aware'`` when evidence is
      present).
    - Every call records a row in ``career_skill_eval_logs``.
    - The API endpoints reflect the same behaviour.
    """

    def setUp(self):
        self.temp_dir = make_workspace_tempdir(".codex_tmp_career_planning_llm_api")
        self.data_client = MockDataClient()
        self.mock_client = MockLLMClient(response=_good_llm_payload())
        self.generator = CareerPlanLLMGenerator(llm_client=self.mock_client)
        self.service = CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career.sqlite3"),
            llm_generator=self.generator,
        )

    def tearDown(self):
        self.service = None
        self.generator = None
        self.mock_client = None
        self.data_client = None
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    # --- direct service tests ---

    def test_generate_plan_uses_llm_path_and_surfaces_metadata(self):
        """LLM success path: profile.generation_mode == 'llm' and LLM metadata is set."""
        result = self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        profile = result["profile"]
        # LLM metadata fields exposed on the response profile
        self.assertEqual(profile.get("generation_mode"), "llm")
        self.assertEqual(profile.get("llm_generation_mode"), "llm")
        self.assertEqual(profile.get("llm_model_id"), "mock-llm")
        self.assertGreaterEqual(int(profile.get("llm_latency_ms") or 0), 0)
        self.assertEqual(len(profile.get("llm_prompt_hash") or ""), 16)
        # llm block in the response
        llm_block = result.get("llm") or {}
        self.assertTrue(llm_block.get("attempted"))
        self.assertTrue(llm_block.get("succeeded"))
        self.assertEqual(llm_block.get("model_id"), "mock-llm")
        self.assertEqual(llm_block.get("fallback_reason"), "")

    def test_generate_plan_persists_llm_metadata_on_plan_row(self):
        """The career_plans row receives model_id / prompt_hash / latency."""
        result = self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        current_plan = result["current_plan"]
        self.assertEqual(current_plan.get("model_id"), "mock-llm")
        self.assertEqual(len(current_plan.get("prompt_hash") or ""), 16)
        self.assertGreaterEqual(int(current_plan.get("generation_latency_ms") or 0), 0)

    def test_generate_plan_falls_back_when_llm_raises(self):
        """LLM exception -> service continues with the phase 2 template path."""
        # Re-construct a generator that always raises
        raising_client = MockLLMClient(raise_exc=RuntimeError("simulated network failure"))
        failing_generator = CareerPlanLLMGenerator(llm_client=raising_client)
        service = CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career-raising.sqlite3"),
            llm_generator=failing_generator,
        )
        result = service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        profile = result["profile"]
        # generation_mode reflects the fallback (not 'llm')
        self.assertNotEqual(profile.get("generation_mode"), "llm")
        # LLM metadata still exposes the failure (may include the
        # exception detail as a suffix; the prefix is the contract).
        self.assertTrue(
            str(profile.get("llm_fallback_reason") or "").startswith("llm_exception"),
            profile.get("llm_fallback_reason"),
        )
        llm_block = result.get("llm") or {}
        self.assertTrue(llm_block.get("attempted"))
        self.assertFalse(llm_block.get("succeeded"))
        # A plan was still created
        self.assertGreaterEqual(len(result["plans"]), 1)
        self.assertGreaterEqual(len(result["tasks"]), 1)

    def test_generate_plan_falls_back_on_invalid_payload(self):
        """LLM returns unparseable JSON -> service falls back without raising."""
        bad_client = MockLLMClient(response="not json at all")
        bad_generator = CareerPlanLLMGenerator(llm_client=bad_client)
        service = CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career-bad-payload.sqlite3"),
            llm_generator=bad_generator,
        )
        result = service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        profile = result["profile"]
        self.assertNotEqual(profile.get("generation_mode"), "llm")
        self.assertIn(
            profile.get("llm_fallback_reason"),
            ("parse_or_schema_error", "schema_invalid", "parse_error"),
        )
        self.assertGreaterEqual(len(result["tasks"]), 1)

    def test_skill_eval_logs_record_both_success_and_failure(self):
        """Each LLM call writes a row to career_skill_eval_logs."""
        # Success run
        self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        # Failure run with a separate service (different db so we isolate logs)
        bad_client = MockLLMClient(response="not json")
        bad_generator = CareerPlanLLMGenerator(llm_client=bad_client)
        bad_service = CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career-eval-log.sqlite3"),
            llm_generator=bad_generator,
        )
        bad_service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )

        bus = bad_service.memory_bus()
        rows = bus.eval_log().read(limit=20)
        names = [row.get("skill_name") for row in rows]
        # The success call must be present (on the original service db)
        bus_success = self.service.memory_bus()
        success_rows = bus_success.eval_log().read(limit=20)
        success_names = [row.get("skill_name") for row in success_rows]
        self.assertIn("llm_generate_plan_struct", success_names)
        self.assertIn("llm_generate_plan_struct", names)
        # On the failure db there should be at least one failed row
        failures = [r for r in rows if int(r.get("success") or 0) == 0]
        self.assertGreaterEqual(len(failures), 1)
        self.assertTrue(failures[0].get("fallback_reason"))

    def test_no_llm_generator_runs_evidence_aware_path(self):
        """When the service has no generator, generation_mode stays 'fallback' or 'evidence'."""
        plain_service = CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / "career-no-llm.sqlite3"),
            llm_generator=None,
        )
        result = plain_service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        profile = result["profile"]
        # Without an LLM, generation_mode must NOT be 'llm'
        self.assertNotEqual(profile.get("generation_mode"), "llm")
        # LLM block still present but reports not attempted
        llm_block = result.get("llm") or {}
        self.assertFalse(llm_block.get("attempted"))

    def test_dashboard_preserves_llm_metadata(self):
        """build_dashboard reuses the persisted plan row and keeps the LLM fields."""
        self.service.generate_plan(
            user_id=1,
            target_role="高级前端开发工程师",
            career_goal="6 个月内拿到 offer",
            horizon_months=6,
            refresh=True,
        )
        dashboard = self.service.build_dashboard(1)
        profile = dashboard["profile"]
        # The dashboard profile is the augmented runtime view; LLM metadata
        # is rebuilt on every read so it stays self-describing.
        self.assertIn("llm_model_id", profile)

    # --- API endpoint tests ---

    def _api_service(self, db_name: str, generator: CareerPlanLLMGenerator):
        return CareerPlanningService(
            self.data_client,
            db_path=str(self.temp_dir / db_name),
            llm_generator=generator,
        )

    def test_api_endpoint_surfaces_llm_metadata(self):
        """POST /api/career/plans/generate returns llm block on success."""
        client_obj = MockLLMClient(response=_good_llm_payload())
        generator = CareerPlanLLMGenerator(llm_client=client_obj)
        service = self._api_service("career-api-llm.sqlite3", generator)
        app_module.STORAGE_AVAILABLE = True
        app_module.data_client = self.data_client
        app_module.career_planning_service = service
        flask_client = app_module.app.test_client()

        response = flask_client.post(
            "/api/career/plans/generate",
            headers={"Authorization": "Bearer session-token"},
            json={
                "target_role": "高级前端开发工程师",
                "career_goal": "6 个月内拿到 offer",
                "horizon_months": 6,
                "refresh": True,
            },
        )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        llm = (payload["data"] or {}).get("llm") or {}
        self.assertTrue(llm.get("attempted"))
        self.assertTrue(llm.get("succeeded"))
        self.assertEqual(llm.get("model_id"), "mock-llm")
        profile = (payload["data"] or {}).get("profile") or {}
        self.assertEqual(profile.get("generation_mode"), "llm")

    def test_api_endpoint_falls_back_on_llm_failure(self):
        """POST /api/career/plans/generate returns 200 with fallback metadata on LLM failure."""
        raising = MockLLMClient(raise_exc=RuntimeError("boom"))
        generator = CareerPlanLLMGenerator(llm_client=raising)
        service = self._api_service("career-api-fallback.sqlite3", generator)
        app_module.STORAGE_AVAILABLE = True
        app_module.data_client = self.data_client
        app_module.career_planning_service = service
        flask_client = app_module.app.test_client()

        response = flask_client.post(
            "/api/career/plans/generate",
            headers={"Authorization": "Bearer session-token"},
            json={
                "target_role": "高级前端开发工程师",
                "career_goal": "6 个月内拿到 offer",
                "horizon_months": 6,
                "refresh": True,
            },
        )
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "success")
        llm = (payload["data"] or {}).get("llm") or {}
        self.assertTrue(llm.get("attempted"))
        self.assertFalse(llm.get("succeeded"))
        self.assertIn("llm_exception", llm.get("fallback_reason", ""))
        # A plan was still created by the fallback path
        self.assertGreaterEqual(len(payload["data"]["plans"]), 1)


if __name__ == "__main__":
    unittest.main()

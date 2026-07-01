"""Career planning domain service.

This service generates a lightweight career plan from existing user data
and persists the result in SQLite. By default it shares the main local
SQLite file with the interview runtime, but it can still be pointed at a
dedicated database for tests or isolated environments.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from runtime_paths import get_env_file_path
from services.career_planning_context import (
    BuildMeta,
    CareerContext,
    ContextSummary,
    ResumeSummary,
    build_career_context,
)
from services.career_planning_llm import CareerPlanLLMGenerator
from services.career_planning_memory import MemoryBus, MemoryStore
from services.career_planning_schema import (
    CareerPlanStructured,
    GenerationOutcome,
)
from services.career_planning_skill_registry import (
    Skill,
    SkillRegistry,
    SKILL_KIND_LLM,
    default_registry,
)
from services.career_planning_skills import (
    DimensionStat,
    TaskTemplate,
    build_evidence_aware_tasks,
)
from sqlite_paths import get_career_sqlite_path, resolve_sqlite_path

load_dotenv(get_env_file_path())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, value))


def _safe_json_loads(raw: str, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _serialize_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _normalize_user_id(user_id: Any) -> str:
    if user_id is None:
        return ""
    return str(user_id).strip()


def _restore_user_id(user_id: Any) -> Any:
    if isinstance(user_id, str):
        raw = user_id.strip()
        if raw.isdigit():
            return int(raw)
        return raw
    return user_id


def _normalize_plan_record(plan: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(plan)
    if "user_id" in normalized:
        normalized["user_id"] = _restore_user_id(normalized["user_id"])
    normalized["assessment_json"] = _safe_json_loads(normalized.get("assessment_json", ""), {})
    normalized["recommendation_json"] = _safe_json_loads(normalized.get("recommendation_json", ""), [])
    return normalized


@dataclass
class CareerBlueprint:
    stage_label: str
    strengths: List[str]
    gaps: List[str]
    priorities: List[str]
    recommendations: List[Dict[str, str]]
    milestones: List[Dict[str, Any]]


# Task type mapping: code -> (icon, label)
TASK_TYPE_MAPS: Dict[str, Dict[str, str]] = {
    "skill_practice": {"icon": "book-open", "label": "技术学习"},
    "interview_prep": {"icon": "target", "label": "面试准备"},
    "project": {"icon": "code", "label": "项目实践"},
    "course": {"icon": "graduation-cap", "label": "课程学习"},
}


def _enrich_task_type(task: Dict[str, Any]) -> Dict[str, Any]:
    """Add task_type_icon and task_type_label to a task dict."""
    task_type = task.get("task_type", "")
    mapping = TASK_TYPE_MAPS.get(task_type, {"icon": "list", "label": "其他"})
    return {
        **task,
        "task_type_icon": mapping["icon"],
        "task_type_label": mapping["label"],
    }


def _enrich_tasks(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Enrich a list of tasks with task_type_icon and task_type_label."""
    return [_enrich_task_type(task) for task in tasks]


# ---------------------------------------------------------------------------
# Phase 2 helpers (module-level to keep service methods compact)
# ---------------------------------------------------------------------------

def _resume_to_payload(resume: ResumeSummary) -> Dict[str, Any]:
    return {
        "file_name": resume.file_name,
        "resume_id": resume.resume_id,
        "upload_time": resume.upload_time,
        "ocr_length": resume.ocr_length,
        "ocr_preview": resume.ocr_preview,
        "gap_signals": list(resume.gap_signals or []),
    }


def _dim_stat_to_dict(stat: DimensionStat) -> Dict[str, Any]:
    return {
        "dimension": stat.dimension,
        "evaluation_count": stat.evaluation_count,
        "avg_score": stat.avg_score,
        "min_score": stat.min_score,
        "max_score": stat.max_score,
        "low_score_count": stat.low_score_count,
        "severity": stat.severity,
        "evidence_samples": list(stat.evidence_samples or []),
        "suggestion_samples": list(stat.suggestion_samples or []),
        "sessions_observed": stat.sessions_observed,
    }


def _build_meta_to_dict(meta: BuildMeta) -> Dict[str, Any]:
    return {
        "built_at": meta.built_at,
        "session_limit": meta.session_limit,
        "evaluation_limit_per_session": meta.evaluation_limit_per_session,
        "question_meta_limit_per_session": meta.question_meta_limit_per_session,
        "truncated_sessions": meta.truncated_sessions,
        "data_client_kind": meta.data_client_kind,
        "has_turn_evaluation_capability": meta.has_turn_evaluation_capability,
        "has_question_metadata_capability": meta.has_question_metadata_capability,
        "has_turn_capability": meta.has_turn_capability,
    }


def _resolve_generation_mode(context: CareerContext) -> str:
    summary = context.summary
    if not summary.has_resume and summary.completed_session_count == 0:
        return "empty"
    if not summary.has_any_evidence:
        return "fallback"
    return "evidence"


def _build_source_summary(
    context: CareerContext,
    has_resume: bool,
    evaluation_count: int,
    avg_score: float,
) -> str:
    parts: List[str] = []
    resume = context.resume_summary
    if has_resume and resume.file_name:
        parts.append(f"简历:{resume.file_name}({resume.ocr_length}字)")
    else:
        parts.append("简历:未上传")

    parts.append(f"面试次数:{context.summary.session_count}(完成 {context.summary.completed_session_count})")
    parts.append(f"完成会话:{context.summary.completed_session_count}")
    parts.append(f"轮次:{context.summary.turn_count}/已答:{context.summary.answered_turn_count}")

    if context.build_meta.has_turn_evaluation_capability:
        if evaluation_count > 0:
            parts.append(f"逐轮评价:{evaluation_count}条")
            parts.append(f"低分(<7):{context.summary.low_score_evaluation_count}条")
            parts.append(f"平均分:{avg_score:.1f}")
        else:
            parts.append("逐轮评价:无")
    else:
        parts.append("逐轮评价:能力缺失")

    if context.build_meta.has_question_metadata_capability:
        parts.append(f"问题元数据:{context.summary.question_metadata_count}条")
    else:
        parts.append("问题元数据:能力缺失")

    if context.resume_summary.gap_signals:
        parts.append(f"简历缺口信号:{len(context.resume_summary.gap_signals)}个")
    return "；".join(parts)


def _build_source_snapshot(context: CareerContext) -> Dict[str, Any]:
    summary = context.summary
    return {
        "session_count": summary.session_count,
        "completed_session_count": summary.completed_session_count,
        "turn_count": summary.turn_count,
        "answered_turn_count": summary.answered_turn_count,
        "evaluation_count": summary.evaluation_count,
        "low_score_evaluation_count": summary.low_score_evaluation_count,
        "question_metadata_count": summary.question_metadata_count,
        "avg_score": summary.avg_score,
        "has_resume": summary.has_resume,
        "has_any_evidence": summary.has_any_evidence,
        "has_question_metadata": summary.has_question_metadata,
        "resume_gap_signal_count": summary.resume_gap_signal_count,
        "latest_session_id": context.data_freshness.latest_session_id,
        "latest_session_at": context.data_freshness.latest_session_at,
        "earliest_session_at": context.data_freshness.earliest_session_at,
        "data_client_kind": context.build_meta.data_client_kind,
        "build_meta": _build_meta_to_dict(context.build_meta),
    }


def _split_focus_gaps(profile: Dict[str, Any], blueprint: CareerBlueprint) -> List[List[str]]:
    """Distribute gap keys across milestones.

    High-severity gaps go to the first milestone, medium-severity to
    the second, others to the third. Falls back to blueprint gaps when
    no real evidence exists.
    """
    gap_dimensions: List[Dict[str, Any]] = profile.get("gap_dimensions") or []
    gap_keys: List[str] = profile.get("resume_gap_signals") or []

    if gap_dimensions:
        high = [d["dimension"] for d in gap_dimensions if d.get("severity") == "high"]
        medium = [d["dimension"] for d in gap_dimensions if d.get("severity") == "medium"]
        plan = [
            high[:2] + gap_keys[:1],
            medium[:2],
            (gap_keys[1:] or [])[:2],
        ]
        # Fill empty slots with blueprint gaps so every milestone has work
        blueprint_gaps = list(blueprint.gaps or [])
        cursor = 0
        for index, slot in enumerate(plan):
            while len(slot) < 1 and cursor < len(blueprint_gaps):
                slot.append(blueprint_gaps[cursor])
                cursor += 1
        return [sorted({item for item in slot if item}) for slot in plan]

    return [list(blueprint.gaps or []) for _ in blueprint.milestones]


def _build_milestone_success(
    target_role: str,
    milestone: Dict[str, Any],
    focus_gaps: List[str],
) -> str:
    if focus_gaps:
        joined = "、".join(focus_gaps[:3])
        return f"完成 {milestone.get('title', '本阶段')} 目标，针对 {joined} 至少产出 1 个可验证成果"
    return f"完成 {milestone.get('title', '本阶段')} 目标，围绕目标岗位「{target_role}」沉淀阶段性产出"


def _struct_tasks_to_specs(tasks: Sequence[Any]) -> List[Dict[str, Any]]:
    """Convert :class:`TaskDraft` instances to the dict shape ``_create_plan_rows`` expects."""
    specs: List[Dict[str, Any]] = []
    for task in tasks:
        specs.append(
            {
                "title": getattr(task, "title", "未命名任务") or "未命名任务",
                "description": getattr(task, "description", "") or "",
                "task_type": getattr(task, "task_type", "skill_practice") or "skill_practice",
                "priority": int(getattr(task, "priority", 3) or 3),
                "gap_key": getattr(task, "gap_key", "") or "",
                "source_evidence": list(getattr(task, "source_evidence", []) or []),
                "resource_refs": list(getattr(task, "resource_refs", []) or []),
                "estimated_effort": getattr(task, "estimated_effort", "") or "",
                "success_criteria": getattr(task, "success_criteria", "") or "",
            }
        )
    return specs


def _struct_recommendations(structured: Optional[CareerPlanStructured]) -> List[Dict[str, str]]:
    if structured is None:
        return []
    out: List[Dict[str, str]] = []
    for rec in structured.recommendations:
        out.append(
            {
                "type": rec.type or "evidence_practice",
                "title": rec.title,
                "reason": rec.reason,
                "url": rec.url or "",
            }
        )
    return out


def _build_recommendations_from_context(
    context: Optional[CareerContext],
    blueprint: CareerBlueprint,
) -> List[Dict[str, str]]:
    base = list(blueprint.recommendations or [])
    if not context or not context.has_real_evidence():
        return base
    extras: List[Dict[str, str]] = []
    for stat in context.dimension_stats:
        if stat.severity != "high" or not stat.evidence_samples:
            continue
        first_evidence = stat.evidence_samples[0]
        extras.append(
            {
                "type": "evidence_practice",
                "title": f"针对性补齐 {stat.dimension}",
                "reason": (
                    f"近 {stat.evaluation_count} 次面试中，{stat.dimension} 平均分 {stat.avg_score}，"
                    f"最低 {stat.min_score}。建议结合：{first_evidence[:80]}"
                ),
                "url": "",
            }
        )
        if len(extras) >= 2:
            break
    return base + extras


def _gap_evidence_for_task(
    context: CareerContext,
    gap_key: str,
    focus_gaps: List[str],
) -> List[Dict[str, Any]]:
    """Pick evidence samples relevant to a task gap_key."""
    if not context or not context.evidence_samples:
        return []
    target_dimensions = {gap_key} | set(focus_gaps or [])
    matched = [
        item for item in context.evidence_samples
        if str(item.get("dimension") or "") in target_dimensions
    ]
    if matched:
        return matched[:3]
    return list(context.evidence_samples[:3])


def _first_suggestion_for_focus(
    context: Optional[CareerContext],
    focus_gaps: List[str],
) -> str:
    if not context or not context.suggestion_samples:
        return ""
    target_dimensions = set(focus_gaps or [])
    for sample in context.suggestion_samples:
        if str(sample.get("dimension") or "") in target_dimensions:
            text = str(sample.get("text") or "").strip()
            if text:
                return text
    # Fallback: first suggestion
    for sample in context.suggestion_samples:
        text = str(sample.get("text") or "").strip()
        if text:
            return text
    return ""


class CareerPlanningService:
    def __init__(
        self,
        data_client: Any,
        db_path: Optional[str] = None,
        *,
        llm_generator: Optional[CareerPlanLLMGenerator] = None,
    ):
        self.data_client = data_client
        base_path = resolve_sqlite_path(db_path) if db_path else get_career_sqlite_path()
        self.db_path = base_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.llm_generator = llm_generator
        self._memory_bus: Optional[MemoryBus] = None
        self._skill_registry: Optional[SkillRegistry] = None
        self._ensure_schema()
        # Phase 3: wire the LLM generator to the service-level memory bus
        # so every call records a row in ``career_skill_eval_logs`` without
        # requiring the caller (e.g. ``app.py``) to do the wiring manually.
        if self.llm_generator is not None and getattr(self.llm_generator, "_memory_bus", None) is None:
            try:
                self.llm_generator._memory_bus = self.memory_bus()
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[career_planning] wire memory bus to LLM failed: {exc}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def _managed_connection(self) -> sqlite3.Connection:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._managed_connection() as conn:
            self._migrate_schema_if_needed(conn)
            self._create_schema(conn)
            self._migrate_schema_if_needed_v2(conn)
            self._migrate_schema_if_needed_v3(conn)
            self._migrate_schema_if_needed_v4(conn)

    def _create_schema(self, conn: sqlite3.Connection) -> None:
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES career_profiles(user_id) ON DELETE CASCADE
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
                updated_at TEXT NOT NULL,
                FOREIGN KEY(plan_id) REFERENCES career_plans(id) ON DELETE CASCADE
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
                updated_at TEXT NOT NULL,
                FOREIGN KEY(milestone_id) REFERENCES career_milestones(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS career_progress_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                progress_delta REAL NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES career_tasks(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_career_plans_user_status ON career_plans(user_id, status, updated_at DESC);
            CREATE INDEX IF NOT EXISTS idx_career_milestones_plan_sort ON career_milestones(plan_id, sort_order ASC);
            CREATE INDEX IF NOT EXISTS idx_career_tasks_milestone_status ON career_tasks(milestone_id, status, priority DESC);
            CREATE INDEX IF NOT EXISTS idx_career_progress_logs_task ON career_progress_logs(task_id, created_at DESC);
            """
        )

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()
        return bool(row)

    def _column_type(self, conn: sqlite3.Connection, table_name: str, column_name: str) -> str:
        if not self._table_exists(conn, table_name):
            return ""
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        for row in rows:
            if row[1] == column_name:
                return str(row[2] or "").upper()
        return ""

    def _migrate_schema_if_needed(self, conn: sqlite3.Connection) -> None:
        if not self._table_exists(conn, "career_profiles"):
            return

        profile_type = self._column_type(conn, "career_profiles", "user_id")
        plan_type = self._column_type(conn, "career_plans", "user_id")
        if profile_type == "TEXT" and plan_type == "TEXT":
            return

        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            existing_tables = [
                "career_progress_logs",
                "career_tasks",
                "career_milestones",
                "career_plans",
                "career_profiles",
            ]
            for table_name in existing_tables:
                if self._table_exists(conn, table_name):
                    conn.execute(f"ALTER TABLE {table_name} RENAME TO {table_name}_legacy")

            self._create_schema(conn)

            if self._table_exists(conn, "career_profiles_legacy"):
                conn.execute(
                    """
                    INSERT INTO career_profiles (
                        user_id, target_role, current_stage, interest_tags, strength_tags, gap_tags,
                        overall_score, source_summary, created_at, updated_at
                    )
                    SELECT
                        CAST(user_id AS TEXT), target_role, current_stage, interest_tags, strength_tags, gap_tags,
                        overall_score, source_summary, created_at, updated_at
                    FROM career_profiles_legacy
                    """
                )

            if self._table_exists(conn, "career_plans_legacy"):
                conn.execute(
                    """
                    INSERT INTO career_plans (
                        id, user_id, target_role, career_goal, status, horizon_months, summary,
                        assessment_json, recommendation_json, created_at, updated_at
                    )
                    SELECT
                        id, CAST(user_id AS TEXT), target_role, career_goal, status, horizon_months, summary,
                        assessment_json, recommendation_json, created_at, updated_at
                    FROM career_plans_legacy
                    """
                )

            if self._table_exists(conn, "career_milestones_legacy"):
                conn.execute(
                    """
                    INSERT INTO career_milestones (
                        id, plan_id, title, description, month_label, status, sort_order, target_date, created_at, updated_at
                    )
                    SELECT
                        id, plan_id, title, description, month_label, status, sort_order, target_date, created_at, updated_at
                    FROM career_milestones_legacy
                    """
                )

            if self._table_exists(conn, "career_tasks_legacy"):
                conn.execute(
                    """
                    INSERT INTO career_tasks (
                        id, milestone_id, title, description, task_type, priority, status, progress, due_date,
                        completed_at, created_at, updated_at
                    )
                    SELECT
                        id, milestone_id, title, description, task_type, priority, status, progress, due_date,
                        completed_at, created_at, updated_at
                    FROM career_tasks_legacy
                    """
                )

            if self._table_exists(conn, "career_progress_logs_legacy"):
                conn.execute(
                    """
                    INSERT INTO career_progress_logs (
                        id, task_id, note, progress_delta, created_at
                    )
                    SELECT
                        id, task_id, note, progress_delta, created_at
                    FROM career_progress_logs_legacy
                    """
                )

            for table_name in [
                "career_progress_logs_legacy",
                "career_tasks_legacy",
                "career_milestones_legacy",
                "career_plans_legacy",
                "career_profiles_legacy",
            ]:
                if self._table_exists(conn, table_name):
                    conn.execute(f"DROP TABLE {table_name}")
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    # ------------------------------------------------------------------
    # Phase 2 migration: add evidence / source columns to existing tables
    # ------------------------------------------------------------------
    def _column_exists(self, conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        if not self._table_exists(conn, table_name):
            return False
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return any(row[1] == column_name for row in rows)

    def _add_column_if_missing(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        column_name: str,
        column_def: str,
    ) -> None:
        if self._column_exists(conn, table_name, column_name):
            return
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")

    def _migrate_schema_if_needed_v2(self, conn: sqlite3.Connection) -> None:
        """Idempotently add phase-2 evidence columns to existing tables."""
        # career_plans
        self._add_column_if_missing(
            conn, "career_plans", "source_session_ids_json", "TEXT NOT NULL DEFAULT '[]'"
        )
        self._add_column_if_missing(
            conn, "career_plans", "source_resume_id", "INTEGER"
        )
        self._add_column_if_missing(
            conn, "career_plans", "source_snapshot_json", "TEXT NOT NULL DEFAULT '{}'"
        )

        # career_milestones
        self._add_column_if_missing(
            conn, "career_milestones", "success_criteria", "TEXT NOT NULL DEFAULT ''"
        )
        self._add_column_if_missing(
            conn, "career_milestones", "focus_gaps_json", "TEXT NOT NULL DEFAULT '[]'"
        )

        # career_tasks
        self._add_column_if_missing(conn, "career_tasks", "gap_key", "TEXT NOT NULL DEFAULT ''")
        self._add_column_if_missing(
            conn, "career_tasks", "source_evidence_json", "TEXT NOT NULL DEFAULT '[]'"
        )
        self._add_column_if_missing(
            conn, "career_tasks", "resource_refs_json", "TEXT NOT NULL DEFAULT '[]'"
        )
        self._add_column_if_missing(
            conn, "career_tasks", "estimated_effort", "TEXT NOT NULL DEFAULT ''"
        )
        self._add_column_if_missing(
            conn, "career_tasks", "success_criteria", "TEXT NOT NULL DEFAULT ''"
        )

    # ------------------------------------------------------------------
    # Phase 3 migration: add LLM / skill eval columns + new table
    # ------------------------------------------------------------------
    def _migrate_schema_if_needed_v3(self, conn: sqlite3.Connection) -> None:
        """Idempotently add phase-3 LLM columns and the eval log table."""
        # career_plans
        self._add_column_if_missing(
            conn, "career_plans", "model_id", "TEXT NOT NULL DEFAULT ''"
        )
        self._add_column_if_missing(
            conn, "career_plans", "prompt_hash", "TEXT NOT NULL DEFAULT ''"
        )
        self._add_column_if_missing(
            conn, "career_plans", "generation_latency_ms", "INTEGER NOT NULL DEFAULT 0"
        )
        self._add_column_if_missing(
            conn, "career_plans", "generation_tokens_in", "INTEGER NOT NULL DEFAULT 0"
        )
        self._add_column_if_missing(
            conn, "career_plans", "generation_tokens_out", "INTEGER NOT NULL DEFAULT 0"
        )
        self._add_column_if_missing(
            conn, "career_plans", "generation_mode", "TEXT NOT NULL DEFAULT 'evidence_aware'"
        )

        # career_profiles
        self._add_column_if_missing(
            conn, "career_profiles", "model_id", "TEXT NOT NULL DEFAULT ''"
        )
        self._add_column_if_missing(
            conn, "career_profiles", "prompt_hash", "TEXT NOT NULL DEFAULT ''"
        )
        self._add_column_if_missing(
            conn, "career_profiles", "generation_latency_ms", "INTEGER NOT NULL DEFAULT 0"
        )

        # career_skill_eval_logs (new table)
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS career_skill_eval_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                skill_name TEXT NOT NULL,
                skill_version TEXT NOT NULL DEFAULT 'v1',
                user_id TEXT,
                plan_id INTEGER,
                model_id TEXT NOT NULL DEFAULT '',
                prompt_hash TEXT NOT NULL DEFAULT '',
                inputs_json TEXT NOT NULL DEFAULT '{}',
                outputs_json TEXT NOT NULL DEFAULT '{}',
                latency_ms INTEGER NOT NULL DEFAULT 0,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0,
                success INTEGER NOT NULL DEFAULT 0,
                fallback_reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_career_skill_eval_logs_skill_created
                ON career_skill_eval_logs(skill_name, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_career_skill_eval_logs_user
                ON career_skill_eval_logs(user_id, created_at DESC);
            """
        )

    # ------------------------------------------------------------------
    # Phase 4 migration: resource-closure tables (idempotent)
    # ------------------------------------------------------------------
    def _migrate_schema_if_needed_v4(self, conn: sqlite3.Connection) -> None:
        """Create the v4 resource-closure tables (read events / favorites / task refs).

        The tables are created with ``IF NOT EXISTS`` so re-running
        :meth:`_ensure_schema` is a no-op. The column types intentionally
        mirror the store APIs in :mod:`services.career_planning_memory`
        so any future schema bump only needs to be applied in one place.
        """
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS career_doc_read_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                section_idx INTEGER NOT NULL DEFAULT 0,
                read_seconds INTEGER NOT NULL DEFAULT 0,
                completed INTEGER NOT NULL DEFAULT 0,
                task_id INTEGER,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_career_doc_read_events_user
                ON career_doc_read_events(user_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_career_doc_read_events_doc
                ON career_doc_read_events(user_id, doc_id);

            CREATE TABLE IF NOT EXISTS career_doc_favorites (
                user_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, doc_id)
            );

            CREATE TABLE IF NOT EXISTS career_task_resource_refs (
                task_id INTEGER NOT NULL,
                doc_id TEXT NOT NULL,
                section_idx INTEGER NOT NULL DEFAULT 0,
                reason TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                PRIMARY KEY (task_id, doc_id, section_idx)
            );
            CREATE INDEX IF NOT EXISTS idx_career_task_resource_refs_task
                ON career_task_resource_refs(task_id);
            """
        )

    def health(self) -> Dict[str, Any]:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return {"ok": True, "db_path": str(self.db_path)}
        except Exception as exc:
            return {"ok": False, "db_path": str(self.db_path), "error": str(exc)}

    # ------------------------------------------------------------------
    # Phase 3 memory / skill registry accessors
    # ------------------------------------------------------------------
    def memory_bus(self) -> MemoryBus:
        """Lazily build a :class:`MemoryBus` for the service.

        The bus wires the long-term store (this service) and the
        procedural eval log together. The short-term context is set by
        the caller (typically ``generate_plan``).
        """
        if self._memory_bus is None:
            self._memory_bus = MemoryBus(service=self)
        return self._memory_bus

    def skill_registry(self) -> SkillRegistry:
        """Return the lazily-initialised :class:`SkillRegistry`."""
        if self._skill_registry is None:
            self._skill_registry = default_registry(memory_bus=self.memory_bus())
            if self.llm_generator is not None:
                try:
                    from services.career_planning_llm import attach_llm_skills

                    attach_llm_skills(self._skill_registry, self.llm_generator)
                except Exception as exc:  # pragma: no cover - defensive
                    print(f"[career_planning] attach_llm_skills failed: {exc}")
        return self._skill_registry

    def set_llm_generator(self, generator: Optional[CareerPlanLLMGenerator]) -> None:
        """Inject / replace the LLM generator at runtime.

        Re-registers the LLM-backed skills so subsequent calls pick up
        the new provider. Also re-wires the service-level memory bus so
        the new generator records eval logs without the caller having to
        do it manually.
        """
        self.llm_generator = generator
        if generator is not None:
            try:
                generator._memory_bus = self.memory_bus()
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[career_planning] set_llm_generator wire bus failed: {exc}")
        if self._skill_registry is not None and generator is not None:
            try:
                from services.career_planning_llm import attach_llm_skills

                attach_llm_skills(self._skill_registry, generator)
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[career_planning] set_llm_generator re-register failed: {exc}")

    def _row_to_dict(self, row: sqlite3.Row | None) -> Dict[str, Any]:
        if not row:
            return {}
        data = dict(row)
        if "user_id" in data:
            data["user_id"] = _restore_user_id(data["user_id"])
        return data

    def _role_blueprint(self, target_role: str) -> CareerBlueprint:
        role = (target_role or "").strip()
        role_lower = role.lower()

        if any(keyword in role for keyword in ["前端", "web", "vue", "react"]):
            return CareerBlueprint(
                stage_label="技术成长型",
                strengths=["产品协作", "界面实现", "快速迭代"],
                gaps=["系统设计", "性能优化", "工程化", "跨团队协作"],
                priorities=["补齐工程基础", "沉淀代表项目", "强化表达与方案能力"],
                recommendations=[
                    {"type": "course", "title": "前端工程化与架构", "reason": "补齐工程能力短板，支持中高级岗位竞争。", "url": ""},
                    {"type": "practice", "title": "系统设计模拟题", "reason": "提升面试中的方案表达与架构思维。", "url": ""},
                    {"type": "project", "title": "高质量业务项目复盘", "reason": "把项目经验转化为可讲述的亮点。", "url": ""},
                ],
                milestones=[
                    {"month": 1, "title": "夯实基础", "description": "梳理技术栈、补齐薄弱环节并完成目标岗位画像。"},
                    {"month": 3, "title": "形成作品", "description": "完成一个可展示的高质量项目与复盘材料。"},
                    {"month": 6, "title": "冲刺岗位", "description": "完成系统设计准备和针对性模拟面试。"},
                ],
            )

        if any(keyword in role for keyword in ["后端", "服务端", "java", "golang", "python"]):
            return CareerBlueprint(
                stage_label="技术深化型",
                strengths=["接口实现", "业务理解", "问题拆解"],
                gaps=["数据库设计", "高并发", "架构设计", "稳定性治理"],
                priorities=["强化服务抽象", "补齐中间件知识", "沉淀稳定性案例"],
                recommendations=[
                    {"type": "course", "title": "后端架构与系统设计", "reason": "提高方案深度和稳定性治理能力。", "url": ""},
                    {"type": "practice", "title": "数据库与缓存专项练习", "reason": "补齐核心中间件与性能优化能力。", "url": ""},
                    {"type": "project", "title": "高并发项目复盘", "reason": "将工程经验沉淀为面试可讲述案例。", "url": ""},
                ],
                milestones=[
                    {"month": 1, "title": "补齐基础", "description": "梳理数据库、缓存和接口设计知识。"},
                    {"month": 3, "title": "强化工程", "description": "完成一个服务稳定性或性能优化项目。"},
                    {"month": 6, "title": "架构冲刺", "description": "完成系统设计与故障治理准备。"},
                ],
            )

        if any(keyword in role for keyword in ["产品", "运营", "pm", "manager"]):
            return CareerBlueprint(
                stage_label="业务驱动型",
                strengths=["需求理解", "跨部门协作", "目标拆解"],
                gaps=["业务建模", "数据分析", "方案表达", "资源整合"],
                priorities=["建立业务框架", "积累案例库", "增强数据说服力"],
                recommendations=[
                    {"type": "course", "title": "产品方法论与数据分析", "reason": "提升业务判断和数据驱动能力。", "url": ""},
                    {"type": "practice", "title": "需求评审与PRD演练", "reason": "增强方案表达与协作效率。", "url": ""},
                    {"type": "project", "title": "关键项目复盘", "reason": "用成果证明业务闭环能力。", "url": ""},
                ],
                milestones=[
                    {"month": 1, "title": "梳理业务框架", "description": "明确目标行业、岗位和核心指标。"},
                    {"month": 3, "title": "形成案例", "description": "准备 2-3 个有量化结果的项目故事。"},
                    {"month": 6, "title": "岗位冲刺", "description": "完善面试话术和业务分析能力。"},
                ],
            )

        return CareerBlueprint(
            stage_label="通用成长型",
            strengths=["学习能力", "执行能力", "沟通意愿"],
            gaps=["目标岗位认知", "差异化亮点", "项目表达"],
            priorities=["明确方向", "沉淀案例", "补齐短板"],
            recommendations=[
                {"type": "course", "title": "目标岗位能力地图", "reason": "建立清晰的目标与差距认知。", "url": ""},
                {"type": "practice", "title": "面试表达与复盘", "reason": "把经验转化为可讲述内容。", "url": ""},
                {"type": "project", "title": "代表性项目沉淀", "reason": "用可验证成果提升竞争力。", "url": ""},
            ],
            milestones=[
                {"month": 1, "title": "方向确认", "description": "确认目标岗位和关键能力差距。"},
                {"month": 3, "title": "能力补齐", "description": "补齐 2-3 个最关键能力短板。"},
                {"month": 6, "title": "成果输出", "description": "形成项目、简历和面试表达闭环。"},
            ],
        )

    def _collect_user_context(self, user_id: int) -> Dict[str, Any]:
        """Backward-compatible thin context used by legacy paths and tests.

        Phase 2 introduces :func:`build_career_context` which returns a
        fully typed :class:`CareerContext`. This legacy helper is kept
        for callers that still expect a plain ``dict`` (e.g. quick smoke
        tests, ad-hoc scripts).
        """
        latest_resume = None
        sessions: List[Dict[str, Any]] = []
        latest_completed_session: Dict[str, Any] = {}
        latest_stats: Dict[str, Any] = {"turn_count": 0, "evaluations": [], "avg_score": 0}

        if self.data_client:
            latest_resume = self.data_client.get_latest_resume(user_id=user_id)
            sessions = self.data_client.list_sessions(limit=8, user_id=user_id) or []
            for session in sessions:
                if session.get("status") == "completed":
                    latest_completed_session = session
                    latest_stats = self.data_client.get_session_statistics(session.get("session_id")) or latest_stats
                    break
            if not latest_completed_session and sessions:
                latest_completed_session = sessions[0]
                latest_stats = self.data_client.get_session_statistics(latest_completed_session.get("session_id")) or latest_stats

        return {
            "resume": latest_resume,
            "sessions": sessions,
            "latest_session": latest_completed_session,
            "stats": latest_stats,
        }

    def _build_full_career_context(
        self,
        user_id: int,
        target_role: str,
        horizon_months: int = 6,
    ) -> CareerContext:
        """Build a typed :class:`CareerContext` via the phase-2 aggregator."""
        return build_career_context(
            self.data_client,
            user_id,
            target_role=target_role,
            horizon_months=horizon_months,
        )

    def _derive_profile(
        self,
        user_id: int,
        target_role: str,
        context: CareerContext,
        blueprint: CareerBlueprint,
    ) -> Dict[str, Any]:
        """Derive a :class:`CareerProfile` payload from real user context.

        The function is the only source of truth for ``gap_tags`` and
        ``strength_tags``. When the context has no real evaluations, the
        arrays are intentionally empty (no fake-personalisation).
        """
        summary = context.summary
        dimension_stats: List[DimensionStat] = context.dimension_stats

        # gap / strength derived from real per-turn evaluations
        gap_dimensions = [d for d in dimension_stats if d.severity in ("high", "medium")]
        strength_dimensions = [
            d for d in dimension_stats
            if d.severity in ("low", "none") and d.evaluation_count > 0
        ]

        gap_tags = sorted({d.dimension for d in gap_dimensions})
        strength_tags = sorted({d.dimension for d in strength_dimensions})

        # When there is no real evaluation, keep both gap_tags and
        # strength_tags empty (no fake-personalisation, phase 1 policy).
        if not context.has_real_evidence():
            gap_tags = []
            strength_tags = []
        else:
            # If we have real evidence but no strengths surfaced (everything
            # below threshold), fall back to blueprint hints. Gaps stay
            # empty if no real gap dimension is observed.
            if not strength_tags and blueprint.strengths:
                strength_tags = blueprint.strengths[:3]

        # Inject resume-side gap signals (deduped)
        resume_gap_signals = list(context.resume_summary.gap_signals or [])
        for signal in resume_gap_signals:
            if signal and signal not in gap_tags:
                gap_tags.append(signal)

        # current_stage & generation_mode
        has_resume = summary.has_resume
        evaluation_count = summary.evaluation_count
        avg_score = summary.avg_score
        completed_count = summary.completed_session_count

        if not has_resume and completed_count == 0:
            current_stage = "数据不足"
            generation_mode = "empty"
        elif has_resume and completed_count == 0:
            current_stage = "仅有简历数据"
            generation_mode = "fallback"
        elif evaluation_count == 0:
            current_stage = "仅有面试记录"
            generation_mode = "fallback"
        elif summary.low_score_evaluation_count == 0 and avg_score >= 8.0:
            current_stage = "冲刺中"
            generation_mode = "evidence"
        elif avg_score >= 6.5:
            current_stage = "成长中"
            generation_mode = "evidence"
        else:
            current_stage = "打基础"
            generation_mode = "evidence"

        source_summary = _build_source_summary(context, has_resume, evaluation_count, avg_score)
        source_snapshot = _build_source_snapshot(context)

        return {
            "user_id": user_id,
            "target_role": target_role,
            "current_stage": current_stage,
            "generation_mode": generation_mode,
            "has_resume": has_resume,
            "has_evaluations": evaluation_count > 0,
            "evaluation_count": evaluation_count,
            "session_count": summary.session_count,
            "interest_tags": json.dumps([blueprint.stage_label, target_role], ensure_ascii=False),
            "strength_tags": json.dumps(strength_tags, ensure_ascii=False),
            "gap_tags": json.dumps(gap_tags, ensure_ascii=False),
            "overall_score": avg_score,
            "source_summary": source_summary,
            "sessions": summary.session_count,
            "latest_session_id": context.data_freshness.latest_session_id,
            "resume": _resume_to_payload(context.resume_summary),
            # phase-2 runtime fields (not persisted; see _save_profile)
            "gap_dimensions": [_dim_stat_to_dict(d) for d in gap_dimensions],
            "strength_dimensions": [_dim_stat_to_dict(d) for d in strength_dimensions],
            "resume_gap_signals": resume_gap_signals,
            "source_snapshot": source_snapshot,
            "context_meta": _build_meta_to_dict(context.build_meta),
        }

    def _save_profile(self, profile: Dict[str, Any]) -> None:
        storage_user_id = _normalize_user_id(profile["user_id"])
        # source_summary 等扩展字段当前不落库，仅内存返回，避免不兼容旧 schema。
        # generation_mode 同样作为生成结果直接透传给前端。
        with self._managed_connection() as conn:
            existing = conn.execute("SELECT user_id FROM career_profiles WHERE user_id = ?", (storage_user_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE career_profiles
                    SET target_role = ?, current_stage = ?, interest_tags = ?, strength_tags = ?, gap_tags = ?,
                        overall_score = ?, source_summary = ?, updated_at = ?
                    WHERE user_id = ?
                    """,
                    (
                        profile["target_role"],
                        profile["current_stage"],
                        profile["interest_tags"],
                        profile["strength_tags"],
                        profile["gap_tags"],
                        profile["overall_score"],
                        profile["source_summary"],
                        _utc_now(),
                        storage_user_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO career_profiles (
                        user_id, target_role, current_stage, interest_tags, strength_tags, gap_tags,
                        overall_score, source_summary, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        storage_user_id,
                        profile["target_role"],
                        profile["current_stage"],
                        profile["interest_tags"],
                        profile["strength_tags"],
                        profile["gap_tags"],
                        profile["overall_score"],
                        profile["source_summary"],
                        _utc_now(),
                        _utc_now(),
                    ),
                )

    def _deactivate_current_plans(self, user_id: int) -> None:
        storage_user_id = _normalize_user_id(user_id)
        with self._managed_connection() as conn:
            conn.execute(
                "UPDATE career_plans SET status = 'archived', updated_at = ? WHERE user_id = ? AND status = 'active'",
                (_utc_now(), storage_user_id),
            )

    def _create_plan_rows(
        self,
        user_id: int,
        target_role: str,
        goal: str,
        horizon_months: int,
        profile: Dict[str, Any],
        blueprint: CareerBlueprint,
        context: Optional[CareerContext] = None,
        structured: Optional[CareerPlanStructured] = None,
        generation_outcome: Optional[GenerationOutcome] = None,
    ) -> Dict[str, Any]:
        """Persist the plan, milestones, and tasks to SQLite.

        Routing
        -------
        - ``structured`` is a non-None :class:`CareerPlanStructured`:
          the LLM path is used; milestone / task / recommendation rows
          come from the LLM output (already validated). ``profile`` is
          augmented with the LLM metadata so the response can surface
          it. This corresponds to ``generation_mode == "llm"``.
        - ``structured`` is ``None`` and ``context`` contains real
          evidence: phase 2 evidence-aware templates run (no LLM). The
          generation mode is "evidence_aware".
        - Otherwise the legacy blueprint templates run. Generation
          mode is "fallback" or "empty" depending on data presence.
        """
        assessment = {
            "current_stage": profile["current_stage"],
            "strengths": _safe_json_loads(profile["strength_tags"], []),
            "gaps": _safe_json_loads(profile["gap_tags"], []),
            "overall_score": profile["overall_score"],
            "source_summary": profile["source_summary"],
            "gap_dimensions": profile.get("gap_dimensions") or [],
            "strength_dimensions": profile.get("strength_dimensions") or [],
            "resume_gap_signals": profile.get("resume_gap_signals") or [],
            "source_snapshot": profile.get("source_snapshot") or {},
        }

        recommendations = _build_recommendations_from_context(context, blueprint)
        summary = (
            f"围绕目标岗位「{target_role}」生成 {horizon_months} 个月职业规划，"
            f"当前阶段为 {profile['current_stage']}，建议优先完成差距补齐和代表性成果沉淀。"
        )
        storage_user_id = _normalize_user_id(user_id)

        source_session_ids = [s.session_id for s in context.sessions] if context else []
        source_resume_id = context.resume_summary.resume_id if context and context.resume_summary.has_resume else None
        source_snapshot = profile.get("source_snapshot") or {}

        focus_gaps_per_milestone = _split_focus_gaps(profile, blueprint)

        # LLM metadata (only set when structured is provided)
        model_id = generation_outcome.model_id if generation_outcome else ""
        prompt_hash = generation_outcome.prompt_hash if generation_outcome else ""
        latency_ms = int(generation_outcome.latency_ms) if generation_outcome else 0
        tokens_in = int(generation_outcome.tokens_in) if generation_outcome else 0
        tokens_out = int(generation_outcome.tokens_out) if generation_outcome else 0
        # Phase 3: persist the generation mode so the dashboard can rebuild
        # LLM metadata on every read without consulting the live context.
        if structured is not None:
            persisted_generation_mode = "llm"
        elif generation_outcome is not None and generation_outcome.fallback_reason:
            persisted_generation_mode = "llm_fallback"
        elif context and context.has_real_evidence():
            persisted_generation_mode = "evidence_aware"
        else:
            persisted_generation_mode = profile.get("generation_mode") or "fallback"

        with self._managed_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO career_plans (
                    user_id, target_role, career_goal, status, horizon_months, summary,
                    assessment_json, recommendation_json,
                    source_session_ids_json, source_resume_id, source_snapshot_json,
                    model_id, prompt_hash, generation_latency_ms,
                    generation_tokens_in, generation_tokens_out,
                    generation_mode,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    storage_user_id,
                    target_role,
                    goal,
                    horizon_months,
                    summary,
                    _serialize_json(assessment),
                    _serialize_json(recommendations),
                    _serialize_json(source_session_ids),
                    source_resume_id,
                    _serialize_json(source_snapshot),
                    model_id,
                    prompt_hash,
                    latency_ms,
                    tokens_in,
                    tokens_out,
                    persisted_generation_mode,
                    _utc_now(),
                    _utc_now(),
                ),
            )
            plan_id = int(cursor.lastrowid)

            milestone_rows: List[Dict[str, Any]] = []
            task_rows: List[Dict[str, Any]] = []
            now = datetime.now(timezone.utc)
            month_step = max(1, horizon_months // max(len(blueprint.milestones), 1))

            # LLM-derived plans use the structured milestones/tasks directly.
            structured_milestones = list(structured.milestones) if structured else []
            structured_tasks_by_milestone: Dict[int, List[Any]] = {}
            if structured:
                # Group tasks by milestone_index via focus_gaps overlap
                for ms in structured_milestones:
                    structured_tasks_by_milestone[ms.sort_order] = []
                for task in structured.tasks:
                    # Try to attribute the task to a milestone via focus_gaps match
                    target_index = 1
                    for ms in structured_milestones:
                        if task.gap_key and task.gap_key in (ms.focus_gaps or []):
                            target_index = ms.sort_order
                            break
                    structured_tasks_by_milestone.setdefault(target_index, []).append(task)

            for index, milestone in enumerate(blueprint.milestones, start=1):
                target_date = (now + timedelta(days=30 * _clamp(milestone.get("month", index), 1, horizon_months))).date().isoformat()
                month_label = f"第 {milestone.get('month', index)} 个月"
                focus_gaps = focus_gaps_per_milestone[index - 1] if index - 1 < len(focus_gaps_per_milestone) else []
                milestone_success = _build_milestone_success(target_role, milestone, focus_gaps)
                milestone_title = milestone.get("title", f"阶段 {index}")
                milestone_description = milestone.get("description", "")
                if structured and index - 1 < len(structured_milestones):
                    s_ms = structured_milestones[index - 1]
                    milestone_title = s_ms.title or milestone_title
                    milestone_description = s_ms.description or milestone_description
                    milestone_success = s_ms.success_criteria or milestone_success

                m_cursor = conn.execute(
                    """
                    INSERT INTO career_milestones (
                        plan_id, title, description, month_label, status, sort_order, target_date,
                        success_criteria, focus_gaps_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'planned', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        plan_id,
                        milestone_title,
                        milestone_description,
                        month_label,
                        index,
                        target_date,
                        milestone_success,
                        _serialize_json(focus_gaps),
                        _utc_now(),
                        _utc_now(),
                    ),
                )
                milestone_id = int(m_cursor.lastrowid)
                milestone_rows.append({
                    "id": milestone_id,
                    "plan_id": plan_id,
                    "success_criteria": milestone_success,
                    "focus_gaps_json": _serialize_json(focus_gaps),
                    **milestone,
                })

                # Pick task source: LLM > evidence-aware > blueprint
                if structured:
                    task_specs = _struct_tasks_to_specs(
                        structured_tasks_by_milestone.get(index, [])
                    )
                else:
                    task_specs = self._select_task_specs(
                        target_role=target_role,
                        milestone_title=milestone_title,
                        milestone_index=milestone.get("month", index),
                        focus_gaps=focus_gaps,
                        context=context,
                        blueprint=blueprint,
                    )

                for task_index, task_spec in enumerate(task_specs, start=1):
                    due_date = (now + timedelta(days=30 * _clamp(int(milestone.get('month', index)), 1, horizon_months))).date().isoformat()
                    t_cursor = conn.execute(
                        """
                        INSERT INTO career_tasks (
                            milestone_id, title, description, task_type, priority, status, progress, due_date,
                            completed_at, gap_key, source_evidence_json, resource_refs_json,
                            estimated_effort, success_criteria, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, '', ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            milestone_id,
                            task_spec["title"],
                            task_spec["description"],
                            task_spec["task_type"],
                            task_spec["priority"],
                            due_date,
                            task_spec.get("gap_key", ""),
                            _serialize_json(task_spec.get("source_evidence", [])),
                            _serialize_json(task_spec.get("resource_refs", [])),
                            task_spec.get("estimated_effort", ""),
                            task_spec.get("success_criteria", ""),
                            _utc_now(),
                            _utc_now(),
                        ),
                    )
                    task_rows.append({
                        "id": int(t_cursor.lastrowid),
                        "milestone_id": milestone_id,
                        "gap_key": task_spec.get("gap_key", ""),
                        "source_evidence_json": _serialize_json(task_spec.get("source_evidence", [])),
                        "resource_refs_json": _serialize_json(task_spec.get("resource_refs", [])),
                        "estimated_effort": task_spec.get("estimated_effort", ""),
                        "success_criteria": task_spec.get("success_criteria", ""),
                        **task_spec,
                    })

        return {
            "plan_id": plan_id,
            "summary": summary,
            "assessment": assessment,
            "recommendations": recommendations,
            "milestones": milestone_rows,
            "tasks": _enrich_tasks(task_rows),
        }

    def _select_task_specs(
        self,
        *,
        target_role: str,
        milestone_title: str,
        milestone_index: int,
        focus_gaps: List[str],
        context: Optional[CareerContext],
        blueprint: CareerBlueprint,
    ) -> List[Dict[str, Any]]:
        """Decide which task template to use for a milestone.

        Returns a list of plain dicts that map to the ``career_tasks``
        columns. When real evidence exists, the evidence-aware path is
        preferred and legacy templates are appended as fallback fillers
        to keep the milestone at a useful density.
        """
        evidence_specs: List[Dict[str, Any]] = []
        if context and context.has_real_evidence() and focus_gaps:
            gap_dimensions = [
                d for d in context.dimension_stats
                if d.dimension in focus_gaps
            ]
            templates: List[TaskTemplate] = build_evidence_aware_tasks(
                target_role=target_role,
                milestone_index=milestone_index,
                gap_dimensions=gap_dimensions,
                focus_gaps=focus_gaps,
                horizon_months=context.horizon_months,
            )
            for template in templates:
                evidence_specs.append(
                    {
                        "title": template.title,
                        "description": template.description,
                        "task_type": template.task_type,
                        "priority": template.priority,
                        "gap_key": template.gap_key,
                        "estimated_effort": template.estimated_effort,
                        "success_criteria": template.success_criteria,
                        "source_evidence": _gap_evidence_for_task(
                            context, template.gap_key, focus_gaps
                        ),
                        "resource_refs": [],
                    }
                )

        if not evidence_specs:
            return self._milestone_tasks(target_role, milestone_title, milestone_index)

        # Augment with at least one interview-prep task derived from suggestions
        suggestion = _first_suggestion_for_focus(context, focus_gaps)
        if suggestion and len(evidence_specs) < 4:
            evidence_specs.append(
                {
                    "title": f"按面试官建议精进 {focus_gaps[0] or '目标能力'}",
                    "description": (
                        f"基于最近一次面试的逐轮评价建议：{suggestion}"
                    ),
                    "task_type": "interview_prep",
                    "priority": 3,
                    "gap_key": focus_gaps[0] if focus_gaps else "",
                    "estimated_effort": "2 周",
                    "success_criteria": "至少完成 1 次相关题目练习并复盘",
                    "source_evidence": _gap_evidence_for_task(
                        context, focus_gaps[0] if focus_gaps else "", focus_gaps
                    ),
                    "resource_refs": [],
                }
            )

        return evidence_specs

    def _milestone_tasks(self, target_role: str, milestone_title: str, month_index: int) -> List[Dict[str, Any]]:
        role = (target_role or "").strip()
        if "前端" in role or "vue" in role.lower() or "react" in role.lower():
            if month_index <= 1:
                return [
                    {"title": "梳理技术栈地图", "description": "整理目标岗位需要的核心知识点与差距。", "task_type": "skill_practice", "priority": 5},
                    {"title": "准备面试表达模板", "description": "输出项目亮点、技术挑战和结果的讲述模板。", "task_type": "interview_prep", "priority": 4},
                ]
            if month_index == 3:
                return [
                    {"title": "完成工程化项目复盘", "description": "整理一个可展示的高质量项目。", "task_type": "project", "priority": 5},
                    {"title": "系统设计专项练习", "description": "补齐性能优化和架构设计表达。", "task_type": "skill_practice", "priority": 4},
                ]
            return [
                {"title": "模拟面试冲刺", "description": "验证表达与临场反应能力。", "task_type": "interview_prep", "priority": 5},
                {"title": "简历与作品集定稿", "description": "将项目成果沉淀为可投递材料。", "task_type": "course", "priority": 4},
            ]

        if "后端" in role or "go" in role.lower() or "java" in role.lower() or "python" in role.lower():
            if month_index <= 1:
                return [
                    {"title": "夯实数据结构与接口设计", "description": "补齐目标岗位核心知识。", "task_type": "skill_practice", "priority": 5},
                    {"title": "整理稳定性案例", "description": "沉淀故障排查和性能优化案例。", "task_type": "project", "priority": 4},
                ]
            if month_index == 3:
                return [
                    {"title": "数据库与缓存专项", "description": "梳理常见高频问题和实践方案。", "task_type": "skill_practice", "priority": 5},
                    {"title": "系统设计模拟", "description": "训练架构设计与权衡能力。", "task_type": "interview_prep", "priority": 4},
                ]
            return [
                {"title": "高并发场景复盘", "description": "准备高频业务场景答题材料。", "task_type": "project", "priority": 5},
                {"title": "面试题库冲刺", "description": "覆盖高频八股与工程问题。", "task_type": "interview_prep", "priority": 4},
            ]

        return [
            {"title": f"{milestone_title} - 核心能力补齐", "description": "围绕当前目标岗位补齐核心短板。", "task_type": "skill_practice", "priority": 5},
            {"title": f"{milestone_title} - 面试表达整理", "description": "把学习成果整理成可讲述的材料。", "task_type": "interview_prep", "priority": 4},
        ]

    def _fetch_profile(self, user_id: int) -> Dict[str, Any]:
        storage_user_id = _normalize_user_id(user_id)
        with self._managed_connection() as conn:
            row = conn.execute("SELECT * FROM career_profiles WHERE user_id = ?", (storage_user_id,)).fetchone()
            return self._row_to_dict(row)

    def _profile_with_metadata(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Augment a saved profile with phase-2 runtime metadata.

        Uses :func:`build_career_context` to re-derive mode / counts from
        the actual user data so the UI never sees stale flags. When the
        incoming profile already carries phase 3 LLM metadata, the
        augmentation preserves it so the response stays self-describing.
        """
        if not profile:
            return profile
        target_role = str(profile.get("target_role") or "")
        context = self._build_full_career_context(
            user_id=int(profile.get("user_id") or 0),
            target_role=target_role,
        )
        summary = context.summary

        # Snapshot phase 3 metadata so it survives the augmentation.
        llm_keys = (
            "llm_model_id",
            "llm_prompt_hash",
            "llm_latency_ms",
            "llm_tokens_in",
            "llm_tokens_out",
            "llm_fallback_reason",
            "llm_generation_mode",
            "llm_current_stage",
            "llm_overall_score",
            "llm_gap_tags",
            "llm_strength_tags",
            "llm_summary",
        )
        llm_snapshot = {key: profile.get(key) for key in llm_keys if key in profile}

        profile["generation_mode"] = _resolve_generation_mode(context)
        profile["has_resume"] = summary.has_resume
        profile["has_evaluations"] = summary.has_any_evidence
        profile["evaluation_count"] = summary.evaluation_count
        profile["session_count"] = summary.session_count
        profile["gap_dimensions"] = [
            _dim_stat_to_dict(d)
            for d in context.dimension_stats
            if d.severity in ("high", "medium")
        ]
        profile["strength_dimensions"] = [
            _dim_stat_to_dict(d)
            for d in context.dimension_stats
            if d.severity in ("low", "none") and d.evaluation_count > 0
        ]
        profile["resume_gap_signals"] = list(context.resume_summary.gap_signals or [])
        profile["source_snapshot"] = _build_source_snapshot(context)
        profile["context_meta"] = _build_meta_to_dict(context.build_meta)
        profile["evidence_samples"] = list(context.evidence_samples or [])
        profile["suggestion_samples"] = list(context.suggestion_samples or [])

        # Restore phase 3 metadata.
        profile.update(llm_snapshot)
        return profile

    def _fetch_plans(self, user_id: int) -> List[Dict[str, Any]]:
        storage_user_id = _normalize_user_id(user_id)
        with self._managed_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM career_plans WHERE user_id = ? ORDER BY updated_at DESC, id DESC",
                (storage_user_id,),
            ).fetchall()
            return [_normalize_plan_record(dict(row)) for row in rows]

    def _fetch_plan_detail(self, plan_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        storage_user_id = _normalize_user_id(user_id)
        with self._managed_connection() as conn:
            plan = conn.execute(
                "SELECT * FROM career_plans WHERE id = ? AND user_id = ?",
                (plan_id, storage_user_id),
            ).fetchone()
            if not plan:
                return None

            milestones = conn.execute(
                "SELECT * FROM career_milestones WHERE plan_id = ? ORDER BY sort_order ASC, id ASC",
                (plan_id,),
            ).fetchall()
            tasks = conn.execute(
                """
                SELECT t.*, m.plan_id
                FROM career_tasks t
                JOIN career_milestones m ON m.id = t.milestone_id
                WHERE m.plan_id = ?
                ORDER BY m.sort_order ASC, t.priority DESC, t.id ASC
                """,
                (plan_id,),
            ).fetchall()
            logs = conn.execute(
                """
                SELECT l.*, t.milestone_id
                FROM career_progress_logs l
                JOIN career_tasks t ON t.id = l.task_id
                JOIN career_milestones m ON m.id = t.milestone_id
                WHERE m.plan_id = ?
                ORDER BY l.created_at DESC, l.id DESC
                """,
                (plan_id,),
            ).fetchall()

            return {
                "plan": _normalize_plan_record(dict(plan)),
                "milestones": [dict(row) for row in milestones],
                "tasks": _enrich_tasks([dict(row) for row in tasks]),
                "logs": [dict(row) for row in logs],
            }

    def _resolve_llm_outcome(
        self,
        *,
        context: CareerContext,
        target_role: str,
        horizon_months: int,
        blueprint_milestones: List[Dict[str, Any]],
    ) -> Tuple[Optional[CareerPlanStructured], Optional[GenerationOutcome]]:
        """Try the LLM path; return ``(structured, outcome)`` or ``(None, None)`` on failure.

        The function is the single seam between the deterministic phase 2
        pipeline and the LLM-driven phase 3 pipeline. Any exception is
        swallowed and converted to a ``success=False`` outcome so the
        caller can transparently fall back while still surfacing the
        failure to the API response.
        """
        generator = self.llm_generator
        if generator is None:
            return None, None
        try:
            outcome = generator.generate(
                context=context,
                target_role=target_role,
                horizon_months=horizon_months,
                blueprint_milestones=blueprint_milestones,
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[career_planning] LLM generator raised: {exc}")
            # Build a synthetic failure outcome so the UI can still
            # surface the failure (model_id, prompt_hash, fallback_reason).
            try:
                from services.career_planning_prompts import build_plan_prompt
                from services.career_planning_schema import (
                    GenerationOutcome,
                    compute_prompt_hash,
                )
                prompt = build_plan_prompt(
                    context=context,
                    target_role=target_role,
                    horizon_months=horizon_months,
                    expected_milestone_count=len(blueprint_milestones) or 3,
                )
                prompt_hash = compute_prompt_hash(prompt.system_prompt, prompt.user_prompt)
            except Exception:
                prompt_hash = ""
            return None, GenerationOutcome(
                success=False,
                error=f"llm_exception:{exc}",
                fallback_reason="llm_exception",
                model_id="fallback",
                prompt_hash=prompt_hash,
            )
        if not outcome or not outcome.success or outcome.plan is None:
            return None, outcome
        return outcome.plan, outcome

    def _augment_profile_with_llm(
        self,
        profile: Dict[str, Any],
        structured: Optional[CareerPlanStructured],
        outcome: Optional[GenerationOutcome],
    ) -> Dict[str, Any]:
        """Surface LLM metadata to the API response without breaking the v1 schema.

        On success, every ``llm_*`` field is populated. On failure only
        ``llm_fallback_reason`` is set so the UI can render the failure
        state without leaking empty model IDs.
        """
        if outcome is None:
            return profile
        profile = dict(profile)
        if outcome.success and structured is not None:
            profile["generation_mode"] = "llm"
            profile["llm_generation_mode"] = "llm"
            profile["llm_current_stage"] = structured.profile.current_stage
            profile["llm_overall_score"] = structured.profile.overall_score
            profile["llm_gap_tags"] = list(structured.profile.gap_tags)
            profile["llm_strength_tags"] = list(structured.profile.strength_tags)
            profile["llm_summary"] = structured.profile.summary
            profile["llm_model_id"] = outcome.model_id or ""
            profile["llm_prompt_hash"] = outcome.prompt_hash or ""
            profile["llm_latency_ms"] = int(outcome.latency_ms or 0)
            profile["llm_tokens_in"] = int(outcome.tokens_in or 0)
            profile["llm_tokens_out"] = int(outcome.tokens_out or 0)
        # Always surface the failure reason when the LLM was attempted.
        profile["llm_fallback_reason"] = outcome.fallback_reason or ""
        return profile

    def generate_plan(
        self,
        user_id: int,
        target_role: str = "",
        career_goal: str = "",
        horizon_months: int = 6,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        horizon_months = _clamp(int(horizon_months or 6), 3, 12)
        latest_session = self._latest_session_summary(user_id)
        resolved_target = (target_role or latest_session.get("position") or "").strip()
        if not resolved_target:
            raise ValueError("target_role is required. Please provide target position explicitly.")

        # Phase 2: build the typed CareerContext that powers gap/strength
        # derivation and evidence-aware task generation.
        context = self._build_full_career_context(
            user_id=user_id,
            target_role=resolved_target,
            horizon_months=horizon_months,
        )
        blueprint = self._role_blueprint(resolved_target)
        profile = self._derive_profile(user_id, resolved_target, context, blueprint)
        self._save_profile(profile)

        if not refresh and not target_role and not career_goal:
            existing_active = next((plan for plan in self._fetch_plans(user_id) if plan.get("status") == "active"), None)
            if existing_active:
                detail = self._fetch_plan_detail(int(existing_active["id"]), user_id) or {}
                enriched_profile = self._profile_with_metadata(self._fetch_profile(user_id))
                return {
                    "profile": enriched_profile,
                    "plans": self._fetch_plans(user_id),
                    "current_plan": detail.get("plan") or existing_active,
                    "milestones": detail.get("milestones") or [],
                    "tasks": detail.get("tasks") or [],
                    "logs": detail.get("logs") or [],
                    "recommendations": existing_active.get("recommendation_json", []),
                }

        self._deactivate_current_plans(user_id)

        # Phase 3: attempt the LLM-driven path before falling back to the
        # deterministic phase 2 templates. The LLM outcome is best-effort;
        # on any failure the existing evidence-aware / blueprint path runs
        # unchanged.
        structured, llm_outcome = self._resolve_llm_outcome(
            context=context,
            target_role=resolved_target,
            horizon_months=horizon_months,
            blueprint_milestones=list(blueprint.milestones),
        )
        # Always augment the profile with LLM metadata when the generator
        # was invoked — even on failure, the caller still needs to see
        # ``llm_fallback_reason`` / ``llm_latency_ms`` so the UI can render
        # the failure path. The augment helper is a no-op when ``outcome``
        # is None (no generator wired in).
        if llm_outcome is not None:
            profile = self._augment_profile_with_llm(profile, structured, llm_outcome)

        plan_bundle = self._create_plan_rows(
            user_id=user_id,
            target_role=resolved_target,
            goal=career_goal or f"围绕 {resolved_target} 构建可执行的发展路径",
            horizon_months=horizon_months,
            profile=profile,
            blueprint=blueprint,
            context=context,
            structured=structured,
            generation_outcome=llm_outcome,
        )

        detail = self._fetch_plan_detail(plan_bundle["plan_id"], user_id) or {}
        # Merge the LLM-augmented profile into the enriched response so the
        # caller sees ``llm_*`` fields without polluting the persisted
        # ``career_profiles`` row.
        base_profile = self._profile_with_metadata(self._fetch_profile(user_id))
        for key, value in profile.items():
            if key.startswith("llm_") or key == "generation_mode":
                base_profile[key] = value
        return {
            "profile": base_profile,
            "plans": self._fetch_plans(user_id),
            "current_plan": detail.get("plan") or {},
            "milestones": detail.get("milestones") or [],
            "tasks": detail.get("tasks") or [],
            "logs": detail.get("logs") or [],
            "recommendations": plan_bundle["recommendations"],
            "plan_bundle": plan_bundle,
            "llm": {
                "attempted": self.llm_generator is not None,
                "succeeded": structured is not None,
                "model_id": llm_outcome.model_id if llm_outcome else "",
                "prompt_hash": llm_outcome.prompt_hash if llm_outcome else "",
                "latency_ms": int(llm_outcome.latency_ms) if llm_outcome else 0,
                "tokens_in": int(llm_outcome.tokens_in) if llm_outcome else 0,
                "tokens_out": int(llm_outcome.tokens_out) if llm_outcome else 0,
                "fallback_reason": llm_outcome.fallback_reason if llm_outcome else "",
            },
        }

    def _latest_session_summary(self, user_id: int) -> Dict[str, Any]:
        """Return the most recent session dict (best-effort)."""
        if not self.data_client:
            return {}
        list_sessions = getattr(self.data_client, "list_sessions", None)
        if not callable(list_sessions):
            return {}
        try:
            sessions = list_sessions(limit=1, user_id=user_id) or []
        except Exception:
            return []
        if not sessions:
            return {}
        session = sessions[0]
        if str(session.get("status") or "") == "completed":
            return session
        # Fallback: scan a few recent sessions to find a completed one
        try:
            more = list_sessions(limit=8, user_id=user_id) or []
        except Exception:
            return session
        for candidate in more:
            if str(candidate.get("status") or "") == "completed":
                return candidate
        return session

    def _aggregate_milestone_statuses(self, conn: sqlite3.Connection, plan_id: int) -> None:
        """根据任务进度动态计算并更新 milestone 状态和 progress。

        规则：
        - 所有任务 status='completed'        -> milestone.status='completed'
        - 任一任务 progress>0 或 status≠'pending' -> milestone.status='in_progress'
        - 否则                                -> milestone.status='planned'

        progress 为该 milestone 下任务的平均进度。
        """
        rows = conn.execute(
            """
            SELECT m.id AS milestone_id,
                   COUNT(t.id) AS task_count,
                   SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) AS completed_count,
                   COALESCE(AVG(t.progress), 0) AS avg_progress
            FROM career_milestones m
            LEFT JOIN career_tasks t ON t.milestone_id = m.id
            WHERE m.plan_id = ?
            GROUP BY m.id
            """,
            (plan_id,),
        ).fetchall()
        now = _utc_now()
        for row in rows:
            milestone_id = int(row["milestone_id"])
            task_count = int(row["task_count"] or 0)
            completed_count = int(row["completed_count"] or 0)
            avg_progress = float(row["avg_progress"] or 0)

            if task_count == 0:
                next_status = "planned"
            elif completed_count >= task_count:
                next_status = "completed"
            elif completed_count > 0 or avg_progress > 0:
                next_status = "in_progress"
            else:
                next_status = "planned"

            conn.execute(
                """
                UPDATE career_milestones
                SET status = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_status, now, milestone_id),
            )

    def _fetch_milestones_for_plan(self, conn: sqlite3.Connection, plan_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(
            "SELECT * FROM career_milestones WHERE plan_id = ? ORDER BY sort_order ASC, id ASC",
            (plan_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def _attach_plan_llm_metadata(self, profile: Dict[str, Any], current_plan: Dict[str, Any]) -> Dict[str, Any]:
        """Surface the active plan's LLM metadata on the profile payload.

        Phase 3 stores ``model_id`` / ``prompt_hash`` / ``generation_latency_ms``
        on the ``career_plans`` row (so the LLM is auditable per-generation),
        not on ``career_profiles``. The dashboard re-derives the profile
        from the live context on every read, so we re-attach the LLM
        metadata from the most recent plan here to keep the API contract
        self-describing.
        """
        if not current_plan:
            return profile
        # Don't override LLM metadata already in flight from generate_plan.
        if profile.get("llm_model_id") or profile.get("llm_prompt_hash"):
            return profile
        profile = dict(profile)
        if current_plan.get("model_id"):
            profile["llm_model_id"] = str(current_plan.get("model_id") or "")
        if current_plan.get("prompt_hash"):
            profile["llm_prompt_hash"] = str(current_plan.get("prompt_hash") or "")
        if current_plan.get("generation_latency_ms"):
            profile["llm_latency_ms"] = int(current_plan.get("generation_latency_ms") or 0)
        # Map stored generation_mode on the plan to a ``llm_generation_mode``
        # field that the UI can render without re-deriving.
        plan_generation_mode = current_plan.get("generation_mode") or "evidence_aware"
        if plan_generation_mode not in ("llm", "llm_fallback", "evidence_aware", "fallback", "empty"):
            plan_generation_mode = "evidence_aware"
        profile["llm_generation_mode"] = plan_generation_mode
        return profile

    def build_dashboard(self, user_id: int) -> Dict[str, Any]:
        profile = self._profile_with_metadata(self._fetch_profile(user_id))
        plans = self._fetch_plans(user_id)
        current_plan = next((plan for plan in plans if plan.get("status") == "active"), plans[0] if plans else None)

        if not profile or not current_plan:
            try:
                generated = self.generate_plan(user_id)
            except ValueError:
                return {
                    "profile": profile or {},
                    "plans": plans,
                    "current_plan": current_plan or {},
                    "milestones": [],
                    "tasks": [],
                    "logs": [],
                    "recommendations": [],
                    "stats": {
                        "plan_count": len(plans),
                        "active_task_count": 0,
                        "completed_task_count": 0,
                        "progress_rate": 0,
                    },
                    "doc_recommendations": [],
                    "favorite_doc_ids": [],
                }

            profile = generated["profile"]
            plans = generated["plans"]
            current_plan = generated["current_plan"]
            milestones = generated["milestones"]
            tasks = generated["tasks"]
            logs = generated["logs"]
            recommendations = generated["recommendations"]
        else:
            detail = self._fetch_plan_detail(current_plan["id"], user_id) or {}
            milestones = detail.get("milestones") or []
            tasks = detail.get("tasks") or []
            logs = detail.get("logs") or []
            recommendations = _safe_json_loads(current_plan.get("recommendation_json", ""), [])

            # Re-attach LLM metadata from the persisted plan row so the
            # dashboard reflects the generation mode of the active plan.
            profile = self._attach_plan_llm_metadata(profile, current_plan)

            # 拉取数据时重新聚合 milestone 状态，保证 dashboard、roadmap、tasks 进度口径一致
            with self._managed_connection() as conn:
                self._aggregate_milestone_statuses(conn, int(current_plan["id"]))
                milestones = self._fetch_milestones_for_plan(conn, int(current_plan["id"]))

        dashboard_stats = {
            "plan_count": len(plans),
            "active_task_count": len([task for task in tasks if task.get("status") != "completed"]),
            "completed_task_count": len([task for task in tasks if task.get("status") == "completed"]),
            "progress_rate": self._calc_progress_rate(tasks),
        }

        # Phase 4: attach doc recommendations + favourite ids + read state.
        # The backfill of (task, doc, section) refs is fire-and-forget: we
        # never want the dashboard call to fail because the catalogue
        # JSON could not be loaded. The recommendations list is the
        # primary surface for the new "为你推荐" sidebar; the favourite
        # list is included so the frontend does not have to make a
        # second roundtrip to render the heart icons.
        doc_recommendations: List[Dict[str, Any]] = []
        try:
            doc_recommendations = self._recommend_for_plan(
                user_id=int(user_id),
                plan_id=int(current_plan.get("id")) if current_plan else None,
                limit=4,
            )
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[career_planning] recommend failed: {exc}")

        favorite_doc_ids: List[str] = []
        try:
            favorite_doc_ids = self.list_favorite_docs(int(user_id))
        except Exception:  # pragma: no cover - defensive
            favorite_doc_ids = []

        # Persist the (task, doc, section) links the first time we see a
        # plan so the task panel can render the "推荐资源" button.
        if current_plan:
            try:
                self.persist_task_resource_refs(
                    plan_id=int(current_plan.get("id")),
                    user_id=int(user_id),
                )
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[career_planning] persist_task_resource_refs failed: {exc}")

        # Enrich every task with its persisted resource_refs (read from
        # the new table so the dashboard reflects the back-filled state).
        task_ref_map: Dict[int, List[Dict[str, Any]]] = {}
        try:
            task_ref_map = self.memory_bus().task_resource_refs().list_for_user(int(user_id))
        except Exception:  # pragma: no cover - defensive
            task_ref_map = {}
        for t in tasks:
            tid = int(t.get("id") or 0)
            if not tid:
                continue
            refs = task_ref_map.get(tid) or []
            t["resource_refs"] = [
                {
                    "doc_id": r.get("doc_id"),
                    "section_idx": int(r.get("section_idx") or 0),
                    "reason": r.get("reason") or "",
                }
                for r in refs
            ]

        return {
            "profile": profile,
            "plans": plans,
            "current_plan": current_plan or {},
            "milestones": milestones,
            "tasks": tasks,
            "logs": logs,
            "recommendations": recommendations,
            "stats": dashboard_stats,
            # Phase 4 additions
            "doc_recommendations": doc_recommendations,
            "favorite_doc_ids": favorite_doc_ids,
        }

    def _calc_progress_rate(self, tasks: List[Dict[str, Any]]) -> float:
        if not tasks:
            return 0.0
        total = 0.0
        for task in tasks:
            total += float(task.get("progress") or 0)
        return round(total / len(tasks), 1)

    def update_task(self, user_id: int, task_id: int, status: str = "", progress: Optional[float] = None, note: str = "") -> Optional[Dict[str, Any]]:
        storage_user_id = _normalize_user_id(user_id)
        with self._managed_connection() as conn:
            row = conn.execute(
                """
                SELECT t.*, p.user_id, p.id AS plan_id
                FROM career_tasks t
                JOIN career_milestones m ON m.id = t.milestone_id
                JOIN career_plans p ON p.id = m.plan_id
                WHERE t.id = ? AND p.user_id = ?
                """,
                (task_id, storage_user_id),
            ).fetchone()
            if not row:
                return None

            task = dict(row)
            next_status = status or task.get("status") or "pending"
            next_progress = float(progress if progress is not None else task.get("progress") or 0)
            if next_status == "completed":
                next_progress = max(next_progress, 100.0)
                completed_at = _utc_now()
            else:
                completed_at = task.get("completed_at") or ""

            conn.execute(
                """
                UPDATE career_tasks
                SET status = ?, progress = ?, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (next_status, next_progress, completed_at, _utc_now(), task_id),
            )

            if note:
                conn.execute(
                    "INSERT INTO career_progress_logs (task_id, note, progress_delta, created_at) VALUES (?, ?, ?, ?)",
                    (task_id, note, next_progress - float(task.get("progress") or 0), _utc_now()),
                )

            # 任务进度变化后，联动更新该 milestone 下所有 milestone 状态，保证 dashboard/roadmap/tasks 进度一致
            self._aggregate_milestone_statuses(conn, int(task.get("plan_id")))

        return self._fetch_plan_detail(int(task.get("plan_id")), user_id)

    # ------------------------------------------------------------------
    # Phase 4: resource closure (doc library → task → user behaviour)
    # ------------------------------------------------------------------
    def doc_repository(self) -> "CareerPlanningDocumentRepository":
        """Return the (lazily-constructed) doc repository singleton.

        The repository is shared across requests and is intentionally
        cheap to construct — the underlying JSON file is read on every
        :meth:`list_sections_with_tags` call so the data stays in sync
        with manual edits in development.
        """
        if not hasattr(self, "_doc_repo") or self._doc_repo is None:
            from services.career_planning_docs import (
                CareerPlanningDocumentRepository,
            )

            self._doc_repo = CareerPlanningDocumentRepository()
        return self._doc_repo

    def _collect_user_recommendation_keys(
        self,
        *,
        user_id: int,
        plan_id: Optional[int],
        profile: Dict[str, Any],
        tasks: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Return the user-derived keys the recommender needs.

        Pulls from the current plan's tasks first (most precise), then
        falls back to the profile's gap_tags / strength_tags. When even
        the profile is empty the function returns a small evergreen
        fallback so the doc panel is never blank.
        """
        gap_keys: List[str] = []
        skill_keys: List[str] = []
        task_types: List[str] = []

        for task in tasks or []:
            if not isinstance(task, dict):
                continue
            gap_key = str(task.get("gap_key") or "").strip()
            if gap_key and gap_key not in gap_keys:
                gap_keys.append(gap_key)
            task_type = str(task.get("task_type") or "").strip()
            if task_type and task_type not in task_types:
                task_types.append(task_type)
            focus_gaps = task.get("focus_gaps") or []
            if isinstance(focus_gaps, list):
                for g in focus_gaps:
                    if isinstance(g, dict):
                        g = g.get("key") or g.get("dimension") or ""
                    s = str(g or "").strip()
                    if s and s not in gap_keys:
                        gap_keys.append(s)

        # Fall back to the profile when no task info is available.
        if not gap_keys:
            for tag in profile.get("gap_tags") or []:
                s = str(tag).strip()
                if s and s not in gap_keys:
                    gap_keys.append(s)
            # Also look for derived skill dimensions from `gap_dimensions`
            for dim in profile.get("gap_dimensions") or []:
                if isinstance(dim, dict):
                    name = str(dim.get("dimension") or dim.get("name") or "").strip()
                    if name and name not in skill_keys:
                        skill_keys.append(name)

        if not gap_keys:
            from services.career_planning_skills import DEFAULT_FALLBACK_GAP_TAGS

            gap_keys = list(DEFAULT_FALLBACK_GAP_TAGS)

        return {
            "gap_keys": gap_keys,
            "skill_keys": skill_keys,
            "task_types": task_types,
            "plan_id": plan_id,
            "user_id": int(user_id) if user_id is not None else 0,
        }

    def _recommend_for_plan(
        self,
        *,
        user_id: int,
        plan_id: Optional[int] = None,
        limit: int = 4,
        score_threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """Return the top-N recommended doc sections for ``user_id``.

        The function is the canonical entrypoint for
        ``GET /api/career/docs/recommend`` and the
        ``CareerInsightSidebar`` panel. It is intentionally synchronous
        and side-effect free: callers can refresh as often as they like.
        """
        profile = self._fetch_profile(int(user_id)) if user_id else {}
        tasks: List[Dict[str, Any]] = []
        target_role = str(profile.get("target_role") or "")
        if plan_id is None:
            try:
                active = self.memory_bus().long_term().fetch_active_plan(int(user_id)) if user_id else None
            except Exception:
                active = None
            plan_id = int(active.get("id")) if active else None
        if plan_id is not None:
            detail = self._fetch_plan_detail(int(plan_id), int(user_id))
            if detail:
                tasks = list(detail.get("tasks") or [])
                target_role = target_role or str(detail.get("target_role") or "")

        keys = self._collect_user_recommendation_keys(
            user_id=int(user_id) if user_id else 0,
            plan_id=plan_id,
            profile=profile,
            tasks=tasks,
        )

        sections = self.doc_repository().list_sections_with_tags()
        if not sections:
            return []

        # Read state for context-aware penalties.
        already_recommended_doc_ids: List[str] = []
        already_completed_doc_ids: List[str] = []
        try:
            bus = self.memory_bus()
            completed = bus.doc_read_events().list_for_user(int(user_id), limit=200)
            for ev in completed:
                if int(ev.get("completed") or 0) == 1:
                    doc_id = str(ev.get("doc_id") or "")
                    if doc_id and doc_id not in already_completed_doc_ids:
                        already_completed_doc_ids.append(doc_id)
        except Exception:  # pragma: no cover - defensive
            pass

        from services.career_planning_skills import collect_resource_recommendations

        recs = collect_resource_recommendations(
            sections,
            user_gap_keys=keys["gap_keys"],
            user_skill_keys=keys["skill_keys"],
            user_task_types=keys["task_types"],
            target_role=target_role,
            already_recommended_doc_ids=already_recommended_doc_ids,
            already_completed_doc_ids=already_completed_doc_ids,
            limit=int(limit),
            score_threshold=float(score_threshold),
        )
        # Attach ``read_state`` so the UI can render a "已读 / 未读" pill.
        for rec in recs:
            try:
                state = self.memory_bus().doc_read_events().doc_state(int(user_id), rec["doc_id"])
                rec["read_state"] = (
                    "completed" if state.get("completed_count", 0) > 0 else
                    "in_progress" if state.get("read_count", 0) > 0 else
                    "unread"
                )
                rec["read_count"] = state.get("read_count", 0)
                rec["completed_count"] = state.get("completed_count", 0)
            except Exception:  # pragma: no cover - defensive
                rec["read_state"] = "unread"
                rec["read_count"] = 0
                rec["completed_count"] = 0
        # Annotate related task ids for the dashboard / sidebar.
        if plan_id is not None:
            try:
                ref_map = self.memory_bus().task_resource_refs().list_for_user(int(user_id))
            except Exception:  # pragma: no cover - defensive
                ref_map = {}
            for rec in recs:
                doc_id = rec["doc_id"]
                section_idx = int(rec["section_idx"])
                related = [
                    int(tid)
                    for (tid, refs) in ref_map.items()
                    for r in refs
                    if str(r.get("doc_id") or "") == doc_id
                    and int(r.get("section_idx") or 0) == section_idx
                ]
                rec["related_task_ids"] = related
        return recs

    def persist_task_resource_refs(self, *, plan_id: int, user_id: int) -> int:
        """Walk a plan's tasks and persist the recommender's section links.

        Returns the number of (task, doc, section) triples written. The
        function is idempotent thanks to the ``ON CONFLICT DO UPDATE``
        on :class:`TaskResourceRefStore`. It is called automatically by
        :meth:`generate_plan` and can also be invoked from the API for
        back-filling historical plans.
        """
        detail = self._fetch_plan_detail(int(plan_id), int(user_id))
        if not detail:
            return 0
        target_role = str(detail.get("target_role") or "")
        sections = self.doc_repository().list_sections_with_tags()
        if not sections:
            return 0
        from services.career_planning_skills import tag_resource_to_task

        bus = self.memory_bus()
        store = bus.task_resource_refs()
        total = 0
        for task in detail.get("tasks") or []:
            if not isinstance(task, dict):
                continue
            task_id = int(task.get("id") or 0)
            if not task_id:
                continue
            refs = tag_resource_to_task(task, sections, target_role=target_role)
            for ref in refs:
                store.upsert(
                    task_id=task_id,
                    doc_id=str(ref.get("doc_id") or ""),
                    section_idx=int(ref.get("section_idx") or 0),
                    reason=str(ref.get("reason") or ""),
                )
                total += 1
        return total

    def mark_doc_read(
        self,
        *,
        user_id: int,
        doc_id: str,
        section_idx: int,
        read_seconds: int = 0,
        completed: bool = False,
        task_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Record a doc read event and (optionally) advance the task progress.

        When ``completed`` is true and the event was linked to a task,
        the function:

        1. Calls :func:`apply_read_event_to_progress` via the skill
           registry to compute the new progress (clamped at 100).
        2. Calls :meth:`update_task` so the milestone state is
           re-aggregated and ``career_progress_logs`` records the delta.
        3. Returns the full updated plan detail for the caller.

        The function is the single seam between the read events and the
        existing task / milestone bookkeeping.
        """
        bus = self.memory_bus()
        event_id = bus.doc_read_events().insert(
            user_id=int(user_id),
            doc_id=str(doc_id),
            section_idx=int(section_idx),
            read_seconds=int(read_seconds),
            completed=bool(completed),
            task_id=int(task_id) if task_id else None,
        )

        # If we have an associated task, advance its progress.
        updated_task: Optional[Dict[str, Any]] = None
        if completed and task_id:
            # Read the current progress so we can apply the increment.
            current_progress = 0.0
            current_status = ""
            with self._managed_connection() as conn:
                row = conn.execute(
                    "SELECT progress, status FROM career_tasks WHERE id = ?",
                    (int(task_id),),
                ).fetchone()
                if row:
                    current_progress = float(row["progress"] or 0)
                    current_status = str(row["status"] or "")

            # Run the skill so the eval log gets a row (phase 3 wiring).
            try:
                registry = self.skill_registry()
                registry.run(
                    "apply_read_event_to_progress",
                    current_progress=current_progress,
                    completed=True,
                    increment=10.0,
                )
            except Exception:  # pragma: no cover - defensive
                pass
            new_progress = min(100.0, current_progress + 10.0)
            new_status = (
                "completed" if new_progress >= 100.0 else
                "in_progress" if new_progress > 0 else
                current_status or "in_progress"
            )
            try:
                detail = self.update_task(
                    user_id=int(user_id),
                    task_id=int(task_id),
                    status=new_status,
                    progress=float(new_progress),
                    note=f"完成文档《{doc_id}》第 {int(section_idx) + 1} 章阅读",
                )
                if detail:
                    for t in detail.get("tasks") or []:
                        if int(t.get("id") or 0) == int(task_id):
                            updated_task = t
                            break
            except Exception as exc:  # pragma: no cover - defensive
                print(f"[career_planning] mark_doc_read update_task failed: {exc}")

        return {
            "event_id": int(event_id),
            "doc_id": str(doc_id),
            "section_idx": int(section_idx),
            "completed": bool(completed),
            "task_id": int(task_id) if task_id else None,
            "task": updated_task,
        }

    def get_doc_read_state(self, user_id: int, doc_id: str) -> Dict[str, Any]:
        """Return the persisted read state for ``(user_id, doc_id)``."""
        bus = self.memory_bus()
        return bus.doc_read_events().doc_state(int(user_id), str(doc_id))

    def toggle_doc_favorite(self, user_id: int, doc_id: str) -> bool:
        """Toggle favorite state and return the new state (True = favorited)."""
        bus = self.memory_bus()
        return bool(bus.doc_favorites().toggle(int(user_id), str(doc_id)))

    def list_favorite_docs(self, user_id: int) -> List[str]:
        bus = self.memory_bus()
        return list(bus.doc_favorites().list_for_user(int(user_id)))

    def list_task_resource_refs(self, task_id: int, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        bus = self.memory_bus()
        return list(bus.task_resource_refs().list_for_task(int(task_id), user_id=user_id))

    def link_task_to_doc(
        self,
        *,
        user_id: int,
        task_id: int,
        doc_id: str,
        section_idx: int,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Persist a (task, doc, section) link on demand.

        The function is the API-layer entrypoint for manual links (e.g.
        the user clicking "添加为资源" on a doc). It is a thin wrapper
        around :class:`TaskResourceRefStore.upsert` that returns the
        canonical ``{task_id, doc_id, section_idx, reason}`` dict for
        the response body.
        """
        # Verify the task belongs to the user (defensive).
        detail_plan_id: Optional[int] = None
        with self._managed_connection() as conn:
            row = conn.execute(
                """
                SELECT t.plan_id, p.user_id FROM career_tasks t
                JOIN career_plans p ON p.id = t.plan_id
                WHERE t.id = ?
                """,
                (int(task_id),),
            ).fetchone()
            if row:
                detail_plan_id = int(row["plan_id"])
                if str(row["user_id"]) != str(int(user_id)):
                    raise PermissionError("task does not belong to user")
        if detail_plan_id is None:
            raise ValueError(f"task {task_id} not found")
        bus = self.memory_bus()
        bus.task_resource_refs().upsert(
            task_id=int(task_id),
            doc_id=str(doc_id),
            section_idx=int(section_idx),
            reason=str(reason or ""),
        )
        return {
            "task_id": int(task_id),
            "doc_id": str(doc_id),
            "section_idx": int(section_idx),
            "reason": str(reason or ""),
        }

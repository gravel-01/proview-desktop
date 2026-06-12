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
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from runtime_paths import get_env_file_path
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


class CareerPlanningService:
    def __init__(self, data_client: Any, db_path: Optional[str] = None):
        self.data_client = data_client
        base_path = resolve_sqlite_path(db_path) if db_path else get_career_sqlite_path()
        self.db_path = base_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

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

    def health(self) -> Dict[str, Any]:
        try:
            with self._connect() as conn:
                conn.execute("SELECT 1")
            return {"ok": True, "db_path": str(self.db_path)}
        except Exception as exc:
            return {"ok": False, "db_path": str(self.db_path), "error": str(exc)}

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

    def _derive_profile(self, user_id: int, target_role: str, context: Dict[str, Any], blueprint: CareerBlueprint) -> Dict[str, Any]:
        stats = context.get("stats") or {}
        evaluations = stats.get("evaluations") or []
        strengths = [item.get("dimension", "") for item in evaluations if item.get("score", 0) >= 7]
        gaps = [item.get("dimension", "") for item in evaluations if item.get("score", 0) < 7]
        avg_score = float(stats.get("avg_score") or 0)
        evaluation_count = len(evaluations)

        # 没有真实评价数据时，不伪造个性化差距和优势，交由前端展示空状态
        if not evaluations:
            strengths = []
            gaps = []
        else:
            if not strengths:
                strengths = blueprint.strengths[:3]
            if not gaps:
                gaps = blueprint.gaps[:4]

        session_count = len(context.get("sessions") or [])
        has_resume = bool(context.get("resume"))
        has_evaluations = evaluation_count > 0

        if not has_resume and session_count == 0:
            current_stage = "数据不足"
            generation_mode = "empty"
        elif not has_evaluations:
            current_stage = "仅有面试记录"
            generation_mode = "fallback"
        elif avg_score >= 8.0:
            current_stage = "冲刺中"
            generation_mode = "evidence"
        elif avg_score >= 6.5:
            current_stage = "成长中"
            generation_mode = "evidence"
        else:
            current_stage = "打基础"
            generation_mode = "evidence"

        resume = context.get("resume") or {}
        source_summary_parts = [
            "简历:{}".format(resume.get("file_name") or "未上传") if resume else "简历:未上传",
            "面试次数:{}".format(session_count),
        ]
        if has_evaluations:
            source_summary_parts.append("结构化评价:{}条".format(evaluation_count))
            source_summary_parts.append("最近面试均分:{:.1f}".format(avg_score))
        else:
            source_summary_parts.append("结构化评价:无")
        source_summary = "；".join(source_summary_parts)

        return {
            "user_id": user_id,
            "target_role": target_role,
            "current_stage": current_stage,
            "generation_mode": generation_mode,
            "has_resume": has_resume,
            "has_evaluations": has_evaluations,
            "evaluation_count": evaluation_count,
            "session_count": session_count,
            "interest_tags": json.dumps([blueprint.stage_label, target_role], ensure_ascii=False),
            "strength_tags": json.dumps(strengths, ensure_ascii=False),
            "gap_tags": json.dumps(gaps, ensure_ascii=False),
            "overall_score": avg_score,
            "source_summary": source_summary,
            "sessions": session_count,
            "latest_session_id": (context.get("latest_session") or {}).get("session_id"),
            "resume": resume,
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
    ) -> Dict[str, Any]:
        assessment = {
            "current_stage": profile["current_stage"],
            "strengths": _safe_json_loads(profile["strength_tags"], []),
            "gaps": _safe_json_loads(profile["gap_tags"], []),
            "overall_score": profile["overall_score"],
            "source_summary": profile["source_summary"],
        }

        recommendations = blueprint.recommendations
        summary = (
            f"围绕目标岗位「{target_role}」生成 {horizon_months} 个月职业规划，"
            f"当前阶段为 {profile['current_stage']}，建议优先完成差距补齐和代表性成果沉淀。"
        )
        storage_user_id = _normalize_user_id(user_id)

        with self._managed_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO career_plans (
                    user_id, target_role, career_goal, status, horizon_months, summary,
                    assessment_json, recommendation_json, created_at, updated_at
                ) VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
                """,
                (
                    storage_user_id,
                    target_role,
                    goal,
                    horizon_months,
                    summary,
                    _serialize_json(assessment),
                    _serialize_json(recommendations),
                    _utc_now(),
                    _utc_now(),
                ),
            )
            plan_id = int(cursor.lastrowid)

            milestone_rows: List[Dict[str, Any]] = []
            task_rows: List[Dict[str, Any]] = []
            now = datetime.now(timezone.utc)
            month_step = max(1, horizon_months // max(len(blueprint.milestones), 1))

            for index, milestone in enumerate(blueprint.milestones, start=1):
                target_date = (now + timedelta(days=30 * _clamp(milestone.get("month", index), 1, horizon_months))).date().isoformat()
                m_cursor = conn.execute(
                    """
                    INSERT INTO career_milestones (
                        plan_id, title, description, month_label, status, sort_order, target_date, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'planned', ?, ?, ?, ?)
                    """,
                    (
                        plan_id,
                        milestone.get("title", f"阶段 {index}"),
                        milestone.get("description", ""),
                        f"第 {milestone.get('month', index)} 个月",
                        index,
                        target_date,
                        _utc_now(),
                        _utc_now(),
                    ),
                )
                milestone_id = int(m_cursor.lastrowid)
                milestone_rows.append({"id": milestone_id, "plan_id": plan_id, **milestone})

                task_specs = self._milestone_tasks(target_role, milestone.get("title", ""), milestone.get("month", index))
                for task_index, task_spec in enumerate(task_specs, start=1):
                    due_date = (now + timedelta(days=30 * _clamp(int(milestone.get('month', index)), 1, horizon_months))).date().isoformat()
                    t_cursor = conn.execute(
                        """
                        INSERT INTO career_tasks (
                            milestone_id, title, description, task_type, priority, status, progress, due_date,
                            completed_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, '', ?, ?)
                        """,
                        (
                            milestone_id,
                            task_spec["title"],
                            task_spec["description"],
                            task_spec["task_type"],
                            task_spec["priority"],
                            due_date,
                            _utc_now(),
                            _utc_now(),
                        ),
                    )
                    task_rows.append({"id": int(t_cursor.lastrowid), "milestone_id": milestone_id, **task_spec})

        return {
            "plan_id": plan_id,
            "summary": summary,
            "assessment": assessment,
            "recommendations": recommendations,
            "milestones": milestone_rows,
            "tasks": _enrich_tasks(task_rows),
        }

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
        """为已保存的 profile 补上 generation_mode、has_resume、has_evaluations 等运行时元数据。"""
        if not profile:
            return profile
        context = self._collect_user_context(profile.get("user_id"))
        stats = context.get("stats") or {}
        evaluations = stats.get("evaluations") or []
        evaluation_count = len(evaluations)
        session_count = len(context.get("sessions") or [])
        has_resume = bool(context.get("resume"))
        has_evaluations = evaluation_count > 0

        if not has_resume and session_count == 0:
            generation_mode = "empty"
        elif not has_evaluations:
            generation_mode = "fallback"
        else:
            generation_mode = "evidence"

        profile["generation_mode"] = generation_mode
        profile["has_resume"] = has_resume
        profile["has_evaluations"] = has_evaluations
        profile["evaluation_count"] = evaluation_count
        profile["session_count"] = session_count
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

    def generate_plan(
        self,
        user_id: int,
        target_role: str = "",
        career_goal: str = "",
        horizon_months: int = 6,
        refresh: bool = False,
    ) -> Dict[str, Any]:
        horizon_months = _clamp(int(horizon_months or 6), 3, 12)
        context = self._collect_user_context(user_id)
        latest_session = context.get("latest_session") or {}

        # Resolve target_role: prefer explicit input, then recent interview position
        # Do NOT fallback to resume file_name (not a job title semantic)
        resolved_target = (target_role or latest_session.get("position") or "").strip()
        if not resolved_target:
            raise ValueError("target_role is required. Please provide target position explicitly.")

        blueprint = self._role_blueprint(resolved_target)
        profile = self._derive_profile(user_id, resolved_target, context, blueprint)
        self._save_profile(profile)

        if not refresh and not target_role and not career_goal:
            existing_active = next((plan for plan in self._fetch_plans(user_id) if plan.get("status") == "active"), None)
            if existing_active:
                detail = self._fetch_plan_detail(int(existing_active["id"]), user_id) or {}
                return {
                    "profile": self._profile_with_metadata(self._fetch_profile(user_id)),
                    "plans": self._fetch_plans(user_id),
                    "current_plan": detail.get("plan") or existing_active,
                    "milestones": detail.get("milestones") or [],
                    "tasks": detail.get("tasks") or [],
                    "logs": detail.get("logs") or [],
                    "recommendations": existing_active.get("recommendation_json", []),
                }

        self._deactivate_current_plans(user_id)

        plan_bundle = self._create_plan_rows(
            user_id=user_id,
            target_role=resolved_target,
            goal=career_goal or f"围绕 {resolved_target} 构建可执行的发展路径",
            horizon_months=horizon_months,
            profile=profile,
            blueprint=blueprint,
        )

        detail = self._fetch_plan_detail(plan_bundle["plan_id"], user_id) or {}
        return {
            "profile": self._profile_with_metadata(self._fetch_profile(user_id)),
            "plans": self._fetch_plans(user_id),
            "current_plan": detail.get("plan") or {},
            "milestones": detail.get("milestones") or [],
            "tasks": detail.get("tasks") or [],
            "logs": detail.get("logs") or [],
            "recommendations": plan_bundle["recommendations"],
            "plan_bundle": plan_bundle,
        }

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

        return {
            "profile": profile,
            "plans": plans,
            "current_plan": current_plan or {},
            "milestones": milestones,
            "tasks": tasks,
            "logs": logs,
            "recommendations": recommendations,
            "stats": dashboard_stats,
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

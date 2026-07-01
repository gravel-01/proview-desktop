"""Career planning long-term / short-term memory module (phase 3).

The career planning subsystem distinguishes between two memory layers:

- **Short-term memory (working memory)**: a single :class:`CareerContext`
  built at the start of one ``generate_plan`` call. It lives only for
  that call and is held by :class:`MemoryBus.short_term`.
- **Long-term memory**: the persistent SQLite store (``career_profiles``,
  ``career_plans``, ``career_milestones``, ``career_tasks``,
  ``career_progress_logs``) plus the new ``career_skill_eval_logs`` table
  that records every skill invocation outcome.

:class:`MemoryBus` is the abstraction the rest of the subsystem uses to
talk to memory. It keeps the service layer decoupled from the SQLite
connection and gives tests a single seam to inject fake stores.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Optional


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_json_loads(raw: Any, default: Any) -> Any:
    if raw is None or raw == "":
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return default


def _serialize(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _restore_user_id(value: Any) -> Any:
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return value


# ---------------------------------------------------------------------------
# MemoryStore — long-term persistence facade
# ---------------------------------------------------------------------------

class MemoryStore:
    """High-level read / write helpers around the career planning schema.

    Wraps the existing :class:`CareerPlanningService` database connection
    so the rest of the subsystem can avoid hand-rolled SQL. The store is
    intentionally thin: it does not enforce business rules (those live
    in the service) but it does centralise connection management and
    dict conversions.
    """

    def __init__(self, service: Any):
        self._service = service

    # ----- connection -----
    @property
    def db_path(self) -> str:
        return str(self._service.db_path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            yield conn

    # ----- read helpers -----
    def fetch_active_plan(self, user_id: Any) -> Optional[Dict[str, Any]]:
        storage_user_id = str(user_id) if user_id is not None else ""
        with self.connection() as conn:
            row = conn.execute(
                "SELECT * FROM career_plans WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
                (storage_user_id,),
            ).fetchone()
            if not row:
                return None
            return _normalize_plan_row(dict(row))

    def fetch_plan_history(self, user_id: Any, *, limit: int = 10) -> List[Dict[str, Any]]:
        storage_user_id = str(user_id) if user_id is not None else ""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT * FROM career_plans WHERE user_id = ? ORDER BY updated_at DESC, id DESC LIMIT ?",
                (storage_user_id, int(limit)),
            ).fetchall()
            return [_normalize_plan_row(dict(row)) for row in rows]

    def fetch_plan_detail(self, plan_id: int, user_id: Any) -> Optional[Dict[str, Any]]:
        return self._service._fetch_plan_detail(plan_id, user_id)  # type: ignore[attr-defined]

    def fetch_profile(self, user_id: Any) -> Dict[str, Any]:
        return self._service._fetch_profile(user_id)  # type: ignore[attr-defined]

    # ----- write helpers -----
    def update_task(
        self,
        *,
        user_id: Any,
        task_id: int,
        status: str = "",
        progress: Optional[float] = None,
        note: str = "",
    ) -> Optional[Dict[str, Any]]:
        return self._service.update_task(  # type: ignore[attr-defined]
            user_id=user_id,
            task_id=task_id,
            status=status,
            progress=progress,
            note=note,
        )

    def aggregate_milestone_statuses(self, plan_id: int) -> None:
        with self.connection() as conn:
            self._service._aggregate_milestone_statuses(conn, int(plan_id))  # type: ignore[attr-defined]

    def deactivate_active_plans(self, user_id: Any) -> None:
        self._service._deactivate_current_plans(user_id)  # type: ignore[attr-defined]

    def persist_plan_bundle(
        self,
        *,
        user_id: Any,
        target_role: str,
        goal: str,
        horizon_months: int,
        profile: Dict[str, Any],
        blueprint: Any,
        context: Any,
        structured: Any = None,
    ) -> Dict[str, Any]:
        """Persist the plan rows. ``structured`` is an optional
        :class:`CareerPlanStructured` from the LLM. When ``None`` the
        service falls back to evidence-aware templates (phase 2)."""
        return self._service._create_plan_rows(  # type: ignore[attr-defined]
            user_id=user_id,
            target_role=target_role,
            goal=goal,
            horizon_months=horizon_months,
            profile=profile,
            blueprint=blueprint,
            context=context,
            structured=structured,
        )

    def save_profile(self, profile: Dict[str, Any]) -> None:
        self._service._save_profile(profile)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# DocReadEventStore — phase 4: persisted reading events
# ---------------------------------------------------------------------------

class DocReadEventStore:
    """Persists reading events for the resource-closure loop.

    One row per ``(user_id, doc_id, section_idx)`` event. Events are
    append-only; aggregations (per-doc read state, per-task progress
    delta) are computed on the fly so the schema stays small.
    """

    def __init__(self, service: Any):
        self._service = service

    def ensure_schema(self) -> None:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)

    @staticmethod
    def _create_table(conn: sqlite3.Connection) -> None:
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
            """
        )

    def insert(
        self,
        *,
        user_id: Any,
        doc_id: str,
        section_idx: int,
        read_seconds: int = 0,
        completed: bool = False,
        task_id: Optional[int] = None,
    ) -> int:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            cursor = conn.execute(
                """
                INSERT INTO career_doc_read_events
                    (user_id, doc_id, section_idx, read_seconds, completed, task_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(user_id),
                    str(doc_id),
                    int(section_idx),
                    int(read_seconds),
                    1 if completed else 0,
                    int(task_id) if task_id is not None else None,
                    _utc_now(),
                ),
            )
            return int(cursor.lastrowid)

    def list_for_user(
        self,
        user_id: Any,
        *,
        doc_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        clauses = ["user_id = ?"]
        params: List[Any] = [str(user_id)]
        if doc_id:
            clauses.append("doc_id = ?")
            params.append(str(doc_id))
        sql = (
            "SELECT * FROM career_doc_read_events WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, id DESC LIMIT ?"
        )
        params.append(int(limit))
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def doc_state(self, user_id: Any, doc_id: str) -> Dict[str, Any]:
        """Return ``{read_count, completed_count, last_read_at}`` for a doc."""
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            row = conn.execute(
                """
                SELECT
                    COUNT(*) AS read_count,
                    SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS completed_count,
                    MAX(created_at) AS last_read_at
                FROM career_doc_read_events
                WHERE user_id = ? AND doc_id = ?
                """,
                (str(user_id), str(doc_id)),
            ).fetchone()
        if not row:
            return {"read_count": 0, "completed_count": 0, "last_read_at": ""}
        return {
            "read_count": int(row["read_count"] or 0),
            "completed_count": int(row["completed_count"] or 0),
            "last_read_at": str(row["last_read_at"] or ""),
        }


# ---------------------------------------------------------------------------
# DocFavoriteStore — phase 4: persisted favorites
# ---------------------------------------------------------------------------

class DocFavoriteStore:
    """Persists doc favorites with idempotent toggle semantics."""

    def __init__(self, service: Any):
        self._service = service

    def ensure_schema(self) -> None:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)

    @staticmethod
    def _create_table(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS career_doc_favorites (
                user_id TEXT NOT NULL,
                doc_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (user_id, doc_id)
            );
            """
        )

    def toggle(self, user_id: Any, doc_id: str) -> bool:
        """Toggle favorite state. Returns the new state (True = favorited)."""
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            existing = conn.execute(
                "SELECT 1 FROM career_doc_favorites WHERE user_id = ? AND doc_id = ?",
                (str(user_id), str(doc_id)),
            ).fetchone()
            if existing:
                conn.execute(
                    "DELETE FROM career_doc_favorites WHERE user_id = ? AND doc_id = ?",
                    (str(user_id), str(doc_id)),
                )
                return False
            conn.execute(
                "INSERT OR IGNORE INTO career_doc_favorites (user_id, doc_id, created_at) VALUES (?, ?, ?)",
                (str(user_id), str(doc_id), _utc_now()),
            )
            return True

    def is_favorite(self, user_id: Any, doc_id: str) -> bool:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            row = conn.execute(
                "SELECT 1 FROM career_doc_favorites WHERE user_id = ? AND doc_id = ?",
                (str(user_id), str(doc_id)),
            ).fetchone()
            return bool(row)

    def list_for_user(self, user_id: Any) -> List[str]:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            rows = conn.execute(
                "SELECT doc_id FROM career_doc_favorites WHERE user_id = ? ORDER BY created_at DESC",
                (str(user_id),),
            ).fetchall()
            return [str(r["doc_id"]) for r in rows]


# ---------------------------------------------------------------------------
# TaskResourceRefStore — phase 4: task ↔ doc section links
# ---------------------------------------------------------------------------

class TaskResourceRefStore:
    """Persists (task_id, doc_id, section_idx) bindings produced by the recommender.

    The store mirrors the JSON column on ``career_tasks.resource_refs_json``
    so that lookups by ``task_id`` stay cheap and the recommender can be
    re-run idempotently. Inserts use ``OR REPLACE`` so re-running
    ``tag_resource_to_task`` updates the reason without creating
    duplicates.
    """

    def __init__(self, service: Any):
        self._service = service

    def ensure_schema(self) -> None:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)

    @staticmethod
    def _create_table(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
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

    def upsert(
        self,
        *,
        task_id: int,
        doc_id: str,
        section_idx: int,
        reason: str = "",
    ) -> None:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            conn.execute(
                """
                INSERT INTO career_task_resource_refs
                    (task_id, doc_id, section_idx, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(task_id, doc_id, section_idx) DO UPDATE SET
                    reason = excluded.reason
                """,
                (int(task_id), str(doc_id), int(section_idx), str(reason or ""), _utc_now()),
            )

    def list_for_task(self, task_id: int, user_id: Any = None) -> List[Dict[str, Any]]:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            if user_id is not None:
                rows = conn.execute(
                    """
                    SELECT r.* FROM career_task_resource_refs r
                    JOIN career_tasks t ON t.id = r.task_id
                    JOIN career_plans p ON p.id = t.plan_id
                    WHERE r.task_id = ? AND p.user_id = ?
                    ORDER BY r.created_at ASC
                    """,
                    (int(task_id), str(user_id)),
                ).fetchall()
                return [dict(r) for r in rows]
            rows = conn.execute(
                "SELECT * FROM career_task_resource_refs WHERE task_id = ? ORDER BY created_at ASC",
                (int(task_id),),
            ).fetchall()
            return [dict(r) for r in rows]

    def list_for_user(self, user_id: Any) -> Dict[int, List[Dict[str, Any]]]:
        """Bulk load all task→refs mappings for a user's plan in one query."""
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            rows = conn.execute(
                """
                SELECT r.* FROM career_task_resource_refs r
                JOIN career_tasks t ON t.id = r.task_id
                JOIN career_plans p ON p.id = t.plan_id
                WHERE p.user_id = ?
                """,
                (str(user_id),),
            ).fetchall()
        out: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            out.setdefault(int(r["task_id"]), []).append(dict(r))
        return out


# ---------------------------------------------------------------------------
# SkillEvalLogStore — procedural memory
# ---------------------------------------------------------------------------

@dataclass
class SkillEvalRecord:
    """In-memory representation of one skill invocation."""

    skill_name: str
    skill_version: str = "v1"
    user_id: Any = None
    plan_id: Optional[int] = None
    model_id: str = ""
    prompt_hash: str = ""
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    success: bool = True
    fallback_reason: str = ""
    created_at: str = field(default_factory=_utc_now)

    def to_row(self) -> Dict[str, Any]:
        return {
            "skill_name": self.skill_name,
            "skill_version": self.skill_version,
            "user_id": "" if self.user_id is None else str(self.user_id),
            "plan_id": self.plan_id,
            "model_id": self.model_id,
            "prompt_hash": self.prompt_hash,
            "inputs_json": _serialize(self.inputs),
            "outputs_json": _serialize(self.outputs),
            "latency_ms": int(self.latency_ms),
            "tokens_in": int(self.tokens_in),
            "tokens_out": int(self.tokens_out),
            "success": 1 if self.success else 0,
            "fallback_reason": self.fallback_reason,
            "created_at": self.created_at,
        }


class SkillEvalLogStore:
    """CRUD for the ``career_skill_eval_logs`` table.

    The table is created lazily via :meth:`ensure_schema` so tests can
    wire the store without booting the full service. Production code
    gets the schema via the service's ``_migrate_schema_if_needed_v3``.
    """

    def __init__(self, service: Any):
        self._service = service

    def ensure_schema(self) -> None:
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)

    def _create_table(self, conn: sqlite3.Connection) -> None:
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

    def insert(self, record: SkillEvalRecord) -> int:
        row = record.to_row()
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            cursor = conn.execute(
                """
                INSERT INTO career_skill_eval_logs (
                    skill_name, skill_version, user_id, plan_id, model_id, prompt_hash,
                    inputs_json, outputs_json, latency_ms, tokens_in, tokens_out,
                    success, fallback_reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["skill_name"],
                    row["skill_version"],
                    row["user_id"],
                    row["plan_id"],
                    row["model_id"],
                    row["prompt_hash"],
                    row["inputs_json"],
                    row["outputs_json"],
                    row["latency_ms"],
                    row["tokens_in"],
                    row["tokens_out"],
                    row["success"],
                    row["fallback_reason"],
                    row["created_at"],
                ),
            )
            return int(cursor.lastrowid)

    def read(
        self,
        *,
        skill_name: Optional[str] = None,
        user_id: Any = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM career_skill_eval_logs"
        clauses: List[str] = []
        params: List[Any] = []
        if skill_name:
            clauses.append("skill_name = ?")
            params.append(skill_name)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(str(user_id))
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
        params.append(int(limit))
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def summary(self, *, user_id: Any = None) -> Dict[str, Any]:
        """Return aggregated counts for dashboard/debug use."""
        clauses: List[str] = []
        params: List[Any] = []
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(str(user_id))
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._service._managed_connection() as conn:  # type: ignore[attr-defined]
            self._create_table(conn)
            total_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM career_skill_eval_logs{where}",
                params,
            ).fetchone()
            success_row = conn.execute(
                f"SELECT COUNT(*) AS c FROM career_skill_eval_logs{where}{(' AND' if where else ' WHERE')} success = 1",
                params,
            ).fetchone()
            latency_row = conn.execute(
                f"SELECT COALESCE(AVG(latency_ms), 0) AS a FROM career_skill_eval_logs{where}",
                params,
            ).fetchone()
        total = int(total_row["c"] or 0) if total_row else 0
        success = int(success_row["c"] or 0) if success_row else 0
        avg_latency = float(latency_row["a"] or 0) if latency_row else 0
        return {
            "total": total,
            "success": success,
            "failure": max(0, total - success),
            "success_rate": round(success / total, 3) if total else 0.0,
            "avg_latency_ms": round(avg_latency, 1),
        }


# ---------------------------------------------------------------------------
# MemoryBus — facade that ties short-term + long-term memory together
# ---------------------------------------------------------------------------

class MemoryBus:
    """Single facade for the career planning memory subsystem.

    The bus is cheap to construct and is the only object the rest of the
    subsystem should depend on. Tests can swap any of the three
    components by passing custom instances.
    """

    def __init__(
        self,
        *,
        service: Any,
        short_term: Optional[Any] = None,
        store: Optional[MemoryStore] = None,
        eval_log: Optional[SkillEvalLogStore] = None,
        doc_read_events: Optional[DocReadEventStore] = None,
        doc_favorites: Optional[DocFavoriteStore] = None,
        task_resource_refs: Optional[TaskResourceRefStore] = None,
    ):
        self._service = service
        self._short_term = short_term
        self._store = store or MemoryStore(service)
        self._eval_log = eval_log or SkillEvalLogStore(service)
        self._doc_read_events = doc_read_events or DocReadEventStore(service)
        self._doc_favorites = doc_favorites or DocFavoriteStore(service)
        self._task_resource_refs = task_resource_refs or TaskResourceRefStore(service)
        # Ensure all v3/v4 tables exist when the bus is constructed.
        try:
            self._eval_log.ensure_schema()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[career_memory] ensure eval_log schema failed: %s", exc)
        try:
            self._doc_read_events.ensure_schema()
            self._doc_favorites.ensure_schema()
            self._task_resource_refs.ensure_schema()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[career_memory] ensure v4 schema failed: %s", exc)

    # ----- short-term (working memory) -----
    def short_term(self) -> Any:
        return self._short_term

    def set_short_term(self, context: Any) -> None:
        self._short_term = context

    # ----- long-term (persistence) -----
    def long_term(self) -> MemoryStore:
        return self._store

    # ----- procedural memory -----
    def eval_log(self) -> SkillEvalLogStore:
        return self._eval_log

    # ----- phase 4: resource-closure memory -----
    def doc_read_events(self) -> DocReadEventStore:
        return self._doc_read_events

    def doc_favorites(self) -> DocFavoriteStore:
        return self._doc_favorites

    def task_resource_refs(self) -> TaskResourceRefStore:
        return self._task_resource_refs

    def log_skill_eval(
        self,
        *,
        skill_name: str,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any] = None,
        success: bool = True,
        latency_ms: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        skill_version: str = "v1",
        user_id: Any = None,
        plan_id: Optional[int] = None,
        model_id: str = "",
        prompt_hash: str = "",
        fallback_reason: str = "",
    ) -> int:
        record = SkillEvalRecord(
            skill_name=skill_name,
            skill_version=skill_version,
            user_id=user_id,
            plan_id=plan_id,
            model_id=model_id,
            prompt_hash=prompt_hash,
            inputs=inputs or {},
            outputs=outputs or {},
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            success=success,
            fallback_reason=fallback_reason,
        )
        return self._eval_log.insert(record)

    def recent_skill_evals(self, *, skill_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        return self._eval_log.read(skill_name=skill_name, limit=limit)

    def eval_summary(self, *, user_id: Any = None) -> Dict[str, Any]:
        return self._eval_log.summary(user_id=user_id)


# ---------------------------------------------------------------------------
# Timing helper used by skills / LLM
# ---------------------------------------------------------------------------

class Timer:
    """Context manager that records elapsed milliseconds.

    >>> with Timer() as t:
    ...     do_work()
    >>> t.elapsed_ms
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self.elapsed_ms: int = 0

    def __enter__(self) -> "Timer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.elapsed_ms = int((time.perf_counter() - self._start) * 1000)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_plan_row(row: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(row)
    if "user_id" in row:
        row["user_id"] = _restore_user_id(row["user_id"])
    if "assessment_json" in row:
        row["assessment_json"] = _safe_json_loads(row.get("assessment_json", ""), {})
    if "recommendation_json" in row:
        row["recommendation_json"] = _safe_json_loads(row.get("recommendation_json", ""), [])
    if "source_session_ids_json" in row:
        row["source_session_ids_json"] = _safe_json_loads(row.get("source_session_ids_json", ""), [])
    if "source_snapshot_json" in row:
        row["source_snapshot_json"] = _safe_json_loads(row.get("source_snapshot_json", ""), {})
    return row


__all__ = [
    "MemoryStore",
    "SkillEvalLogStore",
    "SkillEvalRecord",
    "DocReadEventStore",
    "DocFavoriteStore",
    "TaskResourceRefStore",
    "MemoryBus",
    "Timer",
]

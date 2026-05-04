import json
import importlib.util
import os
import re
import shutil
import uuid
from contextlib import contextmanager
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from werkzeug.security import generate_password_hash

import config as app_config
from services.local_embedding import LocalEmbeddingService
from services.ocr_result_utils import is_reusable_ocr_result
from services.resume_preview_service import (
    cleanup_resume_assets,
    ensure_resume_previews,
)
from sqlite_paths import get_primary_sqlite_path, resolve_sqlite_path


def _append_query_param(url: str, key: str, value: str) -> str:
    parsed = urlsplit(url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if key not in params:
        params[key] = value
    return urlunsplit(parsed._replace(query=urlencode(params)))


def _has_module(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _pick_postgres_driver() -> Optional[str]:
    if _has_module("psycopg"):
        return "psycopg"
    if _has_module("psycopg2"):
        return "psycopg2"
    if _has_module("pg8000"):
        return "pg8000"
    return None


def normalize_db_url(raw_url: str) -> str:
    url = (raw_url or "").strip()
    if not url:
        return f"sqlite:///{get_primary_sqlite_path().as_posix()}"

    if url.startswith("postgresql+"):
        pass
    elif url.startswith("postgres://") or url.startswith("postgresql://"):
        driver = _pick_postgres_driver()
        prefix = "postgres://" if url.startswith("postgres://") else "postgresql://"
        rest = url[len(prefix):]
        if driver:
            url = f"postgresql+{driver}://{rest}"
        else:
            url = f"postgresql://{rest}"
    elif "://" not in url:
        return f"sqlite:///{resolve_sqlite_path(url).as_posix()}"

    if "supabase.co" in url and "sslmode=" not in url:
        url = _append_query_param(url, "sslmode", "require")

    return url


def mask_db_url(url: str) -> str:
    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return url


def _loads_json(raw_value, fallback):
    if not raw_value:
        return fallback
    if isinstance(raw_value, (dict, list)):
        return raw_value
    try:
        return json.loads(raw_value)
    except Exception:
        return fallback


def _parse_iso_datetime(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _empty_evaluation_coverage_metrics() -> Dict:
    return {
        "summary": {
            "session_count": 0,
            "turn_count": 0,
            "answered_turn_count": 0,
            "evaluating_turn_count": 0,
            "evaluated_turn_count": 0,
            "failed_evaluation_count": 0,
            "skipped_turn_count": 0,
            "pending_turn_count": 0,
            "turn_evaluation_count": 0,
            "evaluation_failure_event_count": 0,
            "coverage_rate": None,
            "failure_rate": None,
            "pending_rate": None,
        },
        "sessions": [],
    }


def _build_session_evaluation_coverage(
    *,
    session,
    turns,
    evaluations_by_turn,
    failure_event_count: int,
) -> Dict:
    status_counts = {
        "pending": 0,
        "answered": 0,
        "evaluating": 0,
        "evaluated": 0,
        "evaluation_failed": 0,
        "skipped": 0,
    }
    evaluated_turn_ids = set()
    session_evaluation_count = 0
    latest_turn_no = 0

    for turn in turns:
        status = turn.get("status") or "pending"
        status_counts[status] = status_counts.get(status, 0) + 1
        latest_turn_no = max(latest_turn_no, int(turn.get("turn_no") or 0))
        turn_evaluations = evaluations_by_turn.get(turn.get("turn_id"), [])
        session_evaluation_count += len(turn_evaluations)
        if status == "evaluated" or turn_evaluations:
            evaluated_turn_ids.add(turn.get("turn_id"))

    answered_turn_count = sum(
        status_counts.get(status, 0)
        for status in ("answered", "evaluating", "evaluated", "evaluation_failed")
    )
    evaluated_turn_count = len(evaluated_turn_ids)
    turn_count = len(turns)

    return {
        "session_id": session.get("session_id") or "",
        "candidate_name": session.get("candidate_name") or "",
        "position": session.get("position") or "",
        "status": session.get("status") or "",
        "start_time": session.get("start_time") or "",
        "end_time": session.get("end_time") or "",
        "latest_turn_no": latest_turn_no,
        "turn_count": turn_count,
        "answered_turn_count": answered_turn_count,
        "evaluating_turn_count": status_counts.get("evaluating", 0),
        "evaluated_turn_count": evaluated_turn_count,
        "failed_evaluation_count": status_counts.get("evaluation_failed", 0),
        "skipped_turn_count": status_counts.get("skipped", 0),
        "pending_turn_count": status_counts.get("pending", 0),
        "turn_evaluation_count": session_evaluation_count,
        "evaluation_failure_event_count": int(failure_event_count or 0),
        "coverage_rate": round(evaluated_turn_count / answered_turn_count, 4) if answered_turn_count else None,
        "failure_rate": (
            round(status_counts.get("evaluation_failed", 0) / answered_turn_count, 4)
            if answered_turn_count else None
        ),
        "status_counts": status_counts,
    }


def _normalize_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _slugify_key(text_value: str) -> str:
    value = _normalize_text(text_value).lower()
    value = value.replace("/", "-").replace("\\", "-")
    value = re.sub(r"\s+", "-", value)
    value = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", value)
    value = re.sub(r"-{2,}", "-", value).strip("-_")
    return value or "all"


def _vector_literal(vector: Optional[List[float]]) -> Optional[str]:
    if not vector:
        return None
    return "[" + ",".join(f"{value:.8f}" for value in vector) + "]"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[str] = mapped_column(String(64), default="")


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    candidate_name: Mapped[str | None] = mapped_column(String(255), default="")
    position: Mapped[str | None] = mapped_column(String(255), default="")
    interview_style: Mapped[str | None] = mapped_column(String(64), default="default")
    start_time: Mapped[str | None] = mapped_column(String(64), default="")
    end_time: Mapped[str | None] = mapped_column(String(64), default=None)
    status: Mapped[str | None] = mapped_column(String(32), default="active")
    metadata_json: Mapped[str | None] = mapped_column("metadata", Text, default="{}")
    eval_strengths: Mapped[str | None] = mapped_column(Text, default="")
    eval_weaknesses: Mapped[str | None] = mapped_column(Text, default="")
    eval_summary: Mapped[str | None] = mapped_column(Text, default="")
    eval_draft_json: Mapped[str | None] = mapped_column(Text, default="")


class ChatMessage(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_sessions.session_id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[str] = mapped_column(String(64), default="")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_sessions.session_id"), index=True)
    dimension: Mapped[str] = mapped_column(String(255))
    score: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, default="")
    timestamp: Mapped[str] = mapped_column(String(64), default="")


class InterviewTurn(Base):
    __tablename__ = "interview_turns"

    turn_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_sessions.session_id"), index=True)
    turn_no: Mapped[int] = mapped_column(Integer, index=True)
    question_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    answer_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    question_text_snapshot: Mapped[str | None] = mapped_column(Text, default="")
    answer_text_snapshot: Mapped[str | None] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[str] = mapped_column(String(64), default="")
    answered_at: Mapped[str | None] = mapped_column(String(64), default=None)
    updated_at: Mapped[str] = mapped_column(String(64), default="")


class QuestionMetadata(Base):
    __tablename__ = "question_metadata"

    question_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_sessions.session_id"), index=True)
    turn_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_turns.turn_id"), unique=True, index=True)
    turn_no: Mapped[int] = mapped_column(Integer, index=True)
    question_text_snapshot: Mapped[str | None] = mapped_column(Text, default="")
    dimensions_json: Mapped[str | None] = mapped_column(Text, default="[]")
    difficulty: Mapped[str | None] = mapped_column(String(64), default="")
    question_type: Mapped[str | None] = mapped_column(String(64), default="")
    source: Mapped[str | None] = mapped_column(String(64), default="")
    metadata_refs_json: Mapped[str | None] = mapped_column(Text, default="[]")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")


class TurnEvaluation(Base):
    __tablename__ = "turn_evaluations"
    __table_args__ = (
        UniqueConstraint("turn_id", "dimension", "evaluator_version", name="uq_turn_eval_dimension_version"),
    )

    evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_sessions.session_id"), index=True)
    turn_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_turns.turn_id"), index=True)
    turn_no: Mapped[int] = mapped_column(Integer, index=True)
    dimension: Mapped[str] = mapped_column(String(255), default="")
    score: Mapped[int] = mapped_column(Integer, default=0)
    pass_level: Mapped[str | None] = mapped_column(String(64), default="")
    evidence: Mapped[str | None] = mapped_column(Text, default="")
    suggestion: Mapped[str | None] = mapped_column(Text, default="")
    evaluator_version: Mapped[str] = mapped_column(String(64), default="eval_observer_v1")
    created_at: Mapped[str] = mapped_column(String(64), default="")
    updated_at: Mapped[str] = mapped_column(String(64), default="")


class AgentEvent(Base):
    __tablename__ = "agent_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_sessions.session_id"), index=True)
    turn_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_role: Mapped[str | None] = mapped_column(String(64), default="")
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    payload_json: Mapped[str | None] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(64), default="")


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("interview_sessions.session_id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(1024))
    ocr_result: Mapped[str | None] = mapped_column(Text, default="")
    upload_time: Mapped[str] = mapped_column(String(64), default="")


class DirectDataStore:
    LOCAL_MODE_USERNAME = "__proview_local__"

    def __init__(self, db_url: str, upload_dir: str, secret_key: str):
        self.db_url = normalize_db_url(db_url)
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.serializer = URLSafeTimedSerializer(secret_key or "proview-dev-secret", salt="proview-auth")

        if self.db_url.startswith("postgresql") and not _pick_postgres_driver():
            raise RuntimeError(
                "PostgreSQL driver is not installed. Install psycopg[binary], psycopg2-binary, or pg8000."
            )

        engine_kwargs: dict = {"pool_pre_ping": True}
        if self.db_url.startswith("sqlite"):
            db_path = Path(self.db_url.replace("sqlite:///", "", 1))
            db_path.parent.mkdir(parents=True, exist_ok=True)
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_recycle"] = 300

        self.engine = create_engine(self.db_url, **engine_kwargs)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=self.engine)
        self.resume_user_id_mode = self._detect_resume_user_id_mode()
        self._rag_embedder = self._init_rag_embedder()

    @property
    def masked_db_url(self) -> str:
        return mask_db_url(self.db_url)

    def _init_rag_embedder(self) -> Optional[LocalEmbeddingService]:
        model_dir = getattr(app_config, "LOCAL_EMBEDDING_MODEL_DIR", "")
        max_length = getattr(app_config, "LOCAL_EMBEDDING_MAX_LENGTH", 256)
        if not model_dir:
            return None
        embedder = LocalEmbeddingService(model_dir=model_dir, max_length=max_length)
        return embedder if embedder.is_available() else None

    def _embed_query_literal(self, query: str) -> Optional[str]:
        if not self._rag_embedder or not _normalize_text(query):
            return None
        try:
            return _vector_literal(self._rag_embedder.embed_text(query))
        except Exception as exc:
            print(f"[DirectStore] local embedding failed: {exc}")
            return None

    def _rag_metadata(self, row: Dict, *keys: str) -> Dict:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        for key in keys:
            value = row.get(key)
            if value is not None and key not in metadata:
                metadata[key] = value
        return metadata

    def _fetch_rag_rows(self, sql_text: str, params: Dict) -> List[Dict]:
        with self.engine.connect() as conn:
            result = conn.execute(text(sql_text), params)
            return [dict(row) for row in result.mappings().all()]

    @contextmanager
    def session(self):
        db: Session = self.SessionLocal()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def health(self) -> Dict:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {
                "db_ok": True,
                "mode": "direct",
                "db_url": self.masked_db_url,
            }
        except Exception as exc:
            return {
                "db_ok": False,
                "mode": "direct",
                "db_url": self.masked_db_url,
                "db_error": str(exc),
            }

    def _user_to_dict(self, row: User) -> Dict:
        return {
            "id": row.id,
            "username": row.username,
            "display_name": row.display_name or "",
            "created_at": row.created_at,
        }

    def _session_to_dict(self, row: InterviewSession) -> Dict:
        metadata = {}
        if row.metadata_json:
            try:
                metadata = json.loads(row.metadata_json)
            except Exception:
                metadata = {}
        return {
            "session_id": row.session_id,
            "user_id": row.user_id,
            "candidate_name": row.candidate_name,
            "position": row.position,
            "interview_style": row.interview_style,
            "start_time": row.start_time,
            "end_time": row.end_time,
            "status": row.status,
            "metadata": metadata,
            "eval_strengths": row.eval_strengths or "",
            "eval_weaknesses": row.eval_weaknesses or "",
            "eval_summary": row.eval_summary or "",
            "eval_draft_json": row.eval_draft_json or "",
        }

    def _resume_to_dict(self, row: Resume) -> Dict:
        return {
            "id": row.id,
            "user_id": row.user_id,
            "session_id": row.session_id,
            "file_name": row.file_name,
            "file_path": row.file_path,
            "ocr_result": row.ocr_result or "",
            "upload_time": row.upload_time,
        }

    def _message_to_dict(self, row: ChatMessage) -> Dict:
        return {
            "id": row.id,
            "session_id": row.session_id,
            "role": row.role,
            "content": row.content,
            "timestamp": row.timestamp,
        }

    def _turn_to_dict(self, row: InterviewTurn) -> Dict:
        return {
            "turn_id": row.turn_id,
            "session_id": row.session_id,
            "turn_no": row.turn_no,
            "question_message_id": row.question_message_id,
            "answer_message_id": row.answer_message_id,
            "question_text": row.question_text_snapshot or "",
            "answer_text": row.answer_text_snapshot or "",
            "status": row.status,
            "created_at": row.created_at,
            "answered_at": row.answered_at,
            "updated_at": row.updated_at,
        }

    def _question_metadata_to_dict(self, row: QuestionMetadata) -> Dict:
        return {
            "question_id": row.question_id,
            "session_id": row.session_id,
            "turn_id": row.turn_id,
            "turn_no": row.turn_no,
            "question_text": row.question_text_snapshot or "",
            "dimensions": _loads_json(row.dimensions_json, []),
            "difficulty": row.difficulty or "",
            "question_type": row.question_type or "",
            "source": row.source or "",
            "metadata_refs": _loads_json(row.metadata_refs_json, []),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _agent_event_to_dict(self, row: AgentEvent) -> Dict:
        return {
            "event_id": row.event_id,
            "session_id": row.session_id,
            "turn_id": row.turn_id or "",
            "agent_role": row.agent_role or "",
            "event_type": row.event_type,
            "payload": _loads_json(row.payload_json, {}),
            "created_at": row.created_at,
        }

    def _detect_resume_user_id_mode(self) -> str:
        try:
            inspector = inspect(self.engine)
            columns = {col["name"]: col for col in inspector.get_columns("resumes")}
            user_id_col = columns.get("user_id")
            if not user_id_col:
                return "resume_user_id"

            python_type = getattr(user_id_col.get("type"), "python_type", None)
            if python_type is int:
                return "resume_user_id"
        except Exception:
            pass

        return "session_join"

    def get_user(self, jwt_token: str) -> Optional[Dict]:
        try:
            payload = self.serializer.loads(jwt_token, max_age=60 * 60 * 24 * 30)
            user_id = int(payload["uid"])
        except (BadSignature, SignatureExpired, KeyError, ValueError):
            return None

        try:
            with self.session() as db:
                user = db.get(User, user_id)
                return self._user_to_dict(user) if user else None
        except Exception as exc:
            print(f"[DirectStore] get_user failed: {exc}")
            return None

    def get_or_create_local_user(self, profile_name: str = "") -> Optional[Dict]:
        alias = _normalize_text(profile_name) or "本地用户"

        try:
            with self.session() as db:
                user = db.scalar(select(User).where(User.username == self.LOCAL_MODE_USERNAME))
                if not user:
                    user = User(
                        username=self.LOCAL_MODE_USERNAME,
                        password_hash=generate_password_hash(uuid.uuid4().hex),
                        display_name=alias,
                        created_at=datetime.now().isoformat(),
                    )
                    db.add(user)
                    db.flush()
                elif (user.display_name or "") != alias:
                    user.display_name = alias

                self._claim_local_orphan_data(db, user.id)
                return self._user_to_dict(user)
        except Exception as exc:
            print(f"[DirectStore] get_or_create_local_user failed: {exc}")
            return None

    def _claim_local_orphan_data(self, db: Session, user_id: int) -> None:
        orphan_sessions = db.scalars(
            select(InterviewSession).where(InterviewSession.user_id.is_(None))
        ).all()
        for row in orphan_sessions:
            row.user_id = user_id

        if self.resume_user_id_mode == "resume_user_id":
            orphan_resumes = db.scalars(
                select(Resume).where(Resume.user_id.is_(None))
            ).all()
            for row in orphan_resumes:
                row.user_id = user_id

    def create_session(
        self,
        session_id: str,
        candidate_name: str = "",
        position: str = "",
        interview_style: str = "default",
        metadata: Optional[Dict] = None,
        user_id: Optional[int] = None,
        start_time: Optional[str] = None,
    ) -> bool:
        try:
            with self.session() as db:
                row = InterviewSession(
                    session_id=session_id,
                    user_id=user_id,
                    candidate_name=candidate_name,
                    position=position,
                    interview_style=interview_style,
                    start_time=start_time or datetime.now().isoformat(),
                    status="active",
                    metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
                )
                db.add(row)
            return True
        except IntegrityError:
            return False
        except Exception as exc:
            print(f"[DirectStore] create_session failed: {exc}")
            return False

    def end_session(self, session_id: str) -> bool:
        try:
            with self.session() as db:
                row = db.get(InterviewSession, session_id)
                if not row:
                    return False
                row.end_time = datetime.now().isoformat()
                row.status = "completed"
            return True
        except Exception as exc:
            print(f"[DirectStore] end_session failed: {exc}")
            return False

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        try:
            with self.session() as db:
                row = db.get(InterviewSession, session_id)
                return self._session_to_dict(row) if row else None
        except Exception as exc:
            print(f"[DirectStore] get_session_info failed: {exc}")
            return None

    def list_sessions(self, limit: Optional[int] = 50, user_id: Optional[int] = None) -> List[Dict]:
        try:
            with self.session() as db:
                stmt = select(InterviewSession).order_by(InterviewSession.start_time.desc())
                if user_id is not None:
                    stmt = stmt.where(InterviewSession.user_id == user_id)
                if limit is not None and limit > 0:
                    stmt = stmt.limit(limit)
                rows = db.scalars(stmt).all()
                return [self._session_to_dict(row) for row in rows]
        except Exception as exc:
            print(f"[DirectStore] list_sessions failed: {exc}")
            return []

    def count_user_sessions(self, user_id: int) -> int:
        try:
            with self.session() as db:
                return db.scalar(
                    select(func.count(InterviewSession.session_id)).where(InterviewSession.user_id == user_id)
                ) or 0
        except Exception as exc:
            print(f"[DirectStore] count_user_sessions failed: {exc}")
            return 0

    def delete_session(self, session_id: str, user_id: int) -> bool:
        try:
            resume_paths: List[str] = []
            with self.session() as db:
                row = db.scalar(
                    select(InterviewSession).where(
                        InterviewSession.session_id == session_id,
                        InterviewSession.user_id == user_id,
                    )
                )
                if not row:
                    return False

                resume_rows = db.scalars(
                    select(Resume).where(Resume.session_id == session_id)
                ).all()
                message_rows = db.scalars(
                    select(ChatMessage).where(ChatMessage.session_id == session_id)
                ).all()
                eval_rows = db.scalars(
                    select(Evaluation).where(Evaluation.session_id == session_id)
                ).all()
                turn_rows = db.scalars(
                    select(InterviewTurn).where(InterviewTurn.session_id == session_id)
                ).all()
                question_metadata_rows = db.scalars(
                    select(QuestionMetadata).where(QuestionMetadata.session_id == session_id)
                ).all()
                turn_eval_rows = db.scalars(
                    select(TurnEvaluation).where(TurnEvaluation.session_id == session_id)
                ).all()
                event_rows = db.scalars(
                    select(AgentEvent).where(AgentEvent.session_id == session_id)
                ).all()

                resume_paths = [item.file_path for item in resume_rows if item.file_path]

                for item in turn_eval_rows:
                    db.delete(item)
                for item in question_metadata_rows:
                    db.delete(item)
                for item in event_rows:
                    db.delete(item)
                for item in turn_rows:
                    db.delete(item)
                for item in resume_rows:
                    db.delete(item)
                for item in message_rows:
                    db.delete(item)
                for item in eval_rows:
                    db.delete(item)
                db.delete(row)

            for file_path in resume_paths:
                cleanup_resume_assets(file_path)
            return True
        except Exception as exc:
            print(f"[DirectStore] delete_session failed: {exc}")
            return False

    def storage_capabilities(self) -> Dict:
        return {
            "append_message_returns_id": True,
            "structured_turns": True,
            "question_metadata": True,
            "turn_evaluations": True,
            "agent_events": True,
        }

    def append_message(self, session_id: str, role: str, content: str) -> Optional[Dict]:
        try:
            timestamp = datetime.now().isoformat()
            with self.session() as db:
                row = ChatMessage(
                    session_id=session_id,
                    role=role,
                    content=content,
                    timestamp=timestamp,
                )
                db.add(row)
                db.flush()
                return self._message_to_dict(row)
        except Exception as exc:
            print(f"[DirectStore] append_message failed: {exc}")
            return None

    def save_message(self, session_id: str, role: str, content: str) -> bool:
        return self.append_message(session_id, role, content) is not None

    def get_session_history(self, session_id: str) -> List[Dict]:
        try:
            with self.session() as db:
                rows = db.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == session_id)
                    .order_by(ChatMessage.timestamp.asc(), ChatMessage.id.asc())
                ).all()
                return [
                    {"id": row.id, "role": row.role, "content": row.content, "timestamp": row.timestamp}
                    for row in rows
                ]
        except Exception as exc:
            print(f"[DirectStore] get_session_history failed: {exc}")
            return []

    def save_evaluation(self, session_id: str, dimension: str, score: int, comment: str = "") -> bool:
        try:
            with self.session() as db:
                db.add(
                    Evaluation(
                        session_id=session_id,
                        dimension=dimension,
                        score=score,
                        comment=comment,
                        timestamp=datetime.now().isoformat(),
                    )
                )
            return True
        except Exception as exc:
            print(f"[DirectStore] save_evaluation failed: {exc}")
            return False

    def get_session_statistics(self, session_id: str) -> Dict:
        try:
            with self.session() as db:
                turn_count = db.scalar(
                    select(func.count(ChatMessage.id)).where(
                        ChatMessage.session_id == session_id,
                        ChatMessage.role == "user",
                    )
                ) or 0
                eval_rows = db.scalars(
                    select(Evaluation).where(Evaluation.session_id == session_id)
                ).all()
                evaluations = [
                    {"dimension": row.dimension, "score": row.score, "comment": row.comment or ""}
                    for row in eval_rows
                ]
                avg_score = (
                    sum(item["score"] for item in evaluations) / len(evaluations)
                    if evaluations else 0
                )
                return {
                    "turn_count": turn_count,
                    "evaluations": evaluations,
                    "avg_score": avg_score,
                }
        except Exception as exc:
            print(f"[DirectStore] get_session_statistics failed: {exc}")
            return {"turn_count": 0, "evaluations": [], "avg_score": 0}

    def save_eval_summary(self, session_id: str, strengths: str = "", weaknesses: str = "", summary: str = "") -> bool:
        try:
            with self.session() as db:
                row = db.get(InterviewSession, session_id)
                if not row:
                    return False
                row.eval_strengths = strengths
                row.eval_weaknesses = weaknesses
                row.eval_summary = summary
            return True
        except Exception as exc:
            print(f"[DirectStore] save_eval_summary failed: {exc}")
            return False

    def save_eval_draft(self, session_id: str, draft: dict) -> bool:
        try:
            with self.session() as db:
                row = db.get(InterviewSession, session_id)
                if not row:
                    return False
                row.eval_draft_json = json.dumps(draft, ensure_ascii=False)
            return True
        except Exception as exc:
            print(f"[DirectStore] save_eval_draft failed: {exc}")
            return False

    def create_interview_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        turn_no: int,
        question_message_id: str = "",
        question_text: str = "",
        status: str = "pending",
    ) -> Optional[Dict]:
        try:
            now = datetime.now().isoformat()
            with self.session() as db:
                row = InterviewTurn(
                    turn_id=turn_id,
                    session_id=session_id,
                    turn_no=turn_no,
                    question_message_id=str(question_message_id or "") or None,
                    question_text_snapshot=question_text or "",
                    status=status or "pending",
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
                db.flush()
                return self._turn_to_dict(row)
        except IntegrityError:
            return None
        except Exception as exc:
            print(f"[DirectStore] create_interview_turn failed: {exc}")
            return None

    def get_latest_pending_turn(self, session_id: str) -> Optional[Dict]:
        try:
            with self.session() as db:
                row = db.scalars(
                    select(InterviewTurn)
                    .where(InterviewTurn.session_id == session_id, InterviewTurn.status == "pending")
                    .order_by(InterviewTurn.turn_no.desc(), InterviewTurn.created_at.desc())
                    .limit(1)
                ).first()
                return self._turn_to_dict(row) if row else None
        except Exception as exc:
            print(f"[DirectStore] get_latest_pending_turn failed: {exc}")
            return None

    def get_next_turn_no(self, session_id: str) -> int:
        try:
            with self.session() as db:
                current_max = db.scalar(
                    select(func.max(InterviewTurn.turn_no)).where(InterviewTurn.session_id == session_id)
                ) or 0
                return int(current_max) + 1
        except Exception as exc:
            print(f"[DirectStore] get_next_turn_no failed: {exc}")
            return 1

    def answer_interview_turn(
        self,
        turn_id: str,
        *,
        answer_message_id: str = "",
        answer_text: str = "",
    ) -> Optional[Dict]:
        try:
            now = datetime.now().isoformat()
            with self.session() as db:
                row = db.get(InterviewTurn, turn_id)
                if not row:
                    return None
                row.answer_message_id = str(answer_message_id or "") or None
                row.answer_text_snapshot = answer_text or ""
                row.status = "answered"
                row.answered_at = now
                row.updated_at = now
                db.flush()
                return self._turn_to_dict(row)
        except Exception as exc:
            print(f"[DirectStore] answer_interview_turn failed: {exc}")
            return None

    def update_interview_turn_status(self, turn_id: str, status: str) -> Optional[Dict]:
        allowed = {"pending", "answered", "evaluating", "evaluated", "evaluation_failed", "skipped"}
        if status not in allowed:
            return None
        try:
            now = datetime.now().isoformat()
            with self.session() as db:
                row = db.get(InterviewTurn, turn_id)
                if not row:
                    return None
                row.status = status
                row.updated_at = now
                db.flush()
                return self._turn_to_dict(row)
        except Exception as exc:
            print(f"[DirectStore] update_interview_turn_status failed: {exc}")
            return None

    def skip_pending_turns(self, session_id: str) -> int:
        try:
            now = datetime.now().isoformat()
            with self.session() as db:
                rows = db.scalars(
                    select(InterviewTurn)
                    .where(InterviewTurn.session_id == session_id, InterviewTurn.status == "pending")
                    .order_by(InterviewTurn.turn_no.asc(), InterviewTurn.created_at.asc())
                ).all()
                skipped = 0
                for row in rows:
                    if (row.answer_text_snapshot or "").strip():
                        continue
                    row.status = "skipped"
                    row.updated_at = now
                    skipped += 1
                return skipped
        except Exception as exc:
            print(f"[DirectStore] skip_pending_turns failed: {exc}")
            return 0

    def get_interview_turn(self, turn_id: str) -> Optional[Dict]:
        try:
            with self.session() as db:
                row = db.get(InterviewTurn, turn_id)
                return self._turn_to_dict(row) if row else None
        except Exception as exc:
            print(f"[DirectStore] get_interview_turn failed: {exc}")
            return None

    def list_interview_turns(self, session_id: str) -> List[Dict]:
        try:
            with self.session() as db:
                rows = db.scalars(
                    select(InterviewTurn)
                    .where(InterviewTurn.session_id == session_id)
                    .order_by(InterviewTurn.turn_no.asc(), InterviewTurn.created_at.asc())
                ).all()
                return [self._turn_to_dict(row) for row in rows]
        except Exception as exc:
            print(f"[DirectStore] list_interview_turns failed: {exc}")
            return []

    def save_question_metadata(
        self,
        *,
        session_id: str,
        turn_id: str,
        turn_no: int,
        question_text: str = "",
        dimensions: Optional[List[Dict]] = None,
        difficulty: str = "",
        question_type: str = "",
        source: str = "",
        metadata_refs: Optional[List[Dict]] = None,
    ) -> Optional[Dict]:
        try:
            now = datetime.now().isoformat()
            with self.session() as db:
                row = db.scalar(select(QuestionMetadata).where(QuestionMetadata.turn_id == turn_id))
                if not row:
                    row = QuestionMetadata(
                        question_id=uuid.uuid4().hex,
                        session_id=session_id,
                        turn_id=turn_id,
                        turn_no=turn_no,
                        created_at=now,
                    )
                    db.add(row)
                row.question_text_snapshot = question_text or ""
                row.dimensions_json = json.dumps(dimensions or [], ensure_ascii=False)
                row.difficulty = difficulty or ""
                row.question_type = question_type or ""
                row.source = source or ""
                row.metadata_refs_json = json.dumps(metadata_refs or [], ensure_ascii=False)
                row.updated_at = now
                db.flush()
                return self._question_metadata_to_dict(row)
        except Exception as exc:
            print(f"[DirectStore] save_question_metadata failed: {exc}")
            return None

    def get_question_metadata(self, turn_id: str) -> Optional[Dict]:
        try:
            with self.session() as db:
                row = db.scalar(select(QuestionMetadata).where(QuestionMetadata.turn_id == turn_id))
                return self._question_metadata_to_dict(row) if row else None
        except Exception as exc:
            print(f"[DirectStore] get_question_metadata failed: {exc}")
            return None

    def list_question_metadata(self, session_id: str) -> List[Dict]:
        try:
            with self.session() as db:
                rows = db.scalars(
                    select(QuestionMetadata)
                    .where(QuestionMetadata.session_id == session_id)
                    .order_by(QuestionMetadata.turn_no.asc(), QuestionMetadata.created_at.asc())
                ).all()
                return [self._question_metadata_to_dict(row) for row in rows]
        except Exception as exc:
            print(f"[DirectStore] list_question_metadata failed: {exc}")
            return []

    def upsert_turn_evaluation(
        self,
        *,
        session_id: str,
        turn_id: str,
        turn_no: int,
        dimension: str,
        score: int,
        pass_level: str = "",
        evidence: str = "",
        suggestion: str = "",
        evaluator_version: str = "eval_observer_v1",
    ) -> Optional[Dict]:
        try:
            now = datetime.now().isoformat()
            with self.session() as db:
                row = db.scalar(
                    select(TurnEvaluation).where(
                        TurnEvaluation.turn_id == turn_id,
                        TurnEvaluation.dimension == dimension,
                        TurnEvaluation.evaluator_version == evaluator_version,
                    )
                )
                if not row:
                    row = TurnEvaluation(
                        evaluation_id=uuid.uuid4().hex,
                        session_id=session_id,
                        turn_id=turn_id,
                        turn_no=turn_no,
                        dimension=dimension,
                        evaluator_version=evaluator_version,
                        created_at=now,
                    )
                    db.add(row)
                row.score = int(score or 0)
                row.pass_level = pass_level or ""
                row.evidence = evidence or ""
                row.suggestion = suggestion or ""
                row.updated_at = now
                db.flush()
                return {
                    "evaluation_id": row.evaluation_id,
                    "session_id": row.session_id,
                    "turn_id": row.turn_id,
                    "turn_no": row.turn_no,
                    "dimension": row.dimension,
                    "score": row.score,
                    "pass_level": row.pass_level or "",
                    "evidence": row.evidence or "",
                    "suggestion": row.suggestion or "",
                    "evaluator_version": row.evaluator_version,
                    "created_at": row.created_at,
                    "updated_at": row.updated_at,
                }
        except Exception as exc:
            print(f"[DirectStore] upsert_turn_evaluation failed: {exc}")
            return None

    def list_turn_evaluations(self, session_id: str) -> List[Dict]:
        try:
            with self.session() as db:
                rows = db.scalars(
                    select(TurnEvaluation)
                    .where(TurnEvaluation.session_id == session_id)
                    .order_by(TurnEvaluation.turn_no.asc(), TurnEvaluation.dimension.asc())
                ).all()
                return [
                    {
                        "evaluation_id": row.evaluation_id,
                        "session_id": row.session_id,
                        "turn_id": row.turn_id,
                        "turn_no": row.turn_no,
                        "dimension": row.dimension,
                        "score": row.score,
                        "pass_level": row.pass_level or "",
                        "evidence": row.evidence or "",
                        "suggestion": row.suggestion or "",
                        "evaluator_version": row.evaluator_version,
                        "created_at": row.created_at,
                        "updated_at": row.updated_at,
                    }
                    for row in rows
                ]
        except Exception as exc:
            print(f"[DirectStore] list_turn_evaluations failed: {exc}")
            return []

    def get_evaluation_coverage_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 100) -> Dict:
        try:
            cutoff = None
            if hours is not None and int(hours) > 0:
                cutoff = datetime.now() - timedelta(hours=int(hours))

            with self.session() as db:
                stmt = select(InterviewSession).order_by(InterviewSession.start_time.desc())
                if cutoff is not None:
                    sessions = [
                        row for row in db.scalars(stmt).all()
                        if _parse_iso_datetime(row.start_time) is None
                        or _parse_iso_datetime(row.start_time) >= cutoff
                    ]
                else:
                    sessions = db.scalars(stmt).all()
                if limit is not None and int(limit) > 0:
                    sessions = sessions[: int(limit)]

                session_rows = [
                    {
                        "session_id": row.session_id,
                        "candidate_name": row.candidate_name or "",
                        "position": row.position or "",
                        "status": row.status or "",
                        "start_time": row.start_time or "",
                        "end_time": row.end_time or "",
                    }
                    for row in sessions
                ]
                session_ids = [row["session_id"] for row in session_rows]
                if not session_ids:
                    return _empty_evaluation_coverage_metrics()

                turn_rows = db.scalars(
                    select(InterviewTurn)
                    .where(InterviewTurn.session_id.in_(session_ids))
                    .order_by(InterviewTurn.session_id.asc(), InterviewTurn.turn_no.asc())
                ).all()
                turns = [
                    {
                        "turn_id": row.turn_id,
                        "session_id": row.session_id,
                        "turn_no": row.turn_no,
                        "status": row.status or "pending",
                    }
                    for row in turn_rows
                ]
                evaluation_rows = db.scalars(
                    select(TurnEvaluation).where(TurnEvaluation.session_id.in_(session_ids))
                ).all()
                evaluations = [
                    {
                        "turn_id": row.turn_id,
                        "session_id": row.session_id,
                    }
                    for row in evaluation_rows
                ]
                event_rows = db.scalars(
                    select(AgentEvent).where(AgentEvent.session_id.in_(session_ids))
                ).all()
                events = [
                    {
                        "session_id": row.session_id,
                        "event_type": row.event_type,
                    }
                    for row in event_rows
                ]

            evaluations_by_turn = defaultdict(list)
            for item in evaluations:
                evaluations_by_turn[item["turn_id"]].append(item)

            events_by_session = defaultdict(int)
            for item in events:
                if item["event_type"] == "turn_evaluation_failed":
                    events_by_session[item["session_id"]] += 1

            turns_by_session = defaultdict(list)
            for item in turns:
                turns_by_session[item["session_id"]].append(item)

            sessions_payload = []
            summary = {
                "session_count": len(session_rows),
                "turn_count": 0,
                "answered_turn_count": 0,
                "evaluating_turn_count": 0,
                "evaluated_turn_count": 0,
                "failed_evaluation_count": 0,
                "skipped_turn_count": 0,
                "pending_turn_count": 0,
                "turn_evaluation_count": len(evaluations),
                "evaluation_failure_event_count": sum(events_by_session.values()),
            }

            for session in session_rows:
                session_turns = turns_by_session.get(session["session_id"], [])
                session_metrics = _build_session_evaluation_coverage(
                    session=session,
                    turns=session_turns,
                    evaluations_by_turn=evaluations_by_turn,
                    failure_event_count=events_by_session.get(session["session_id"], 0),
                )
                sessions_payload.append(session_metrics)
                for key in (
                    "turn_count",
                    "answered_turn_count",
                    "evaluating_turn_count",
                    "evaluated_turn_count",
                    "failed_evaluation_count",
                    "skipped_turn_count",
                    "pending_turn_count",
                ):
                    summary[key] += session_metrics[key]

            denominator = summary["answered_turn_count"]
            summary["coverage_rate"] = (
                round(summary["evaluated_turn_count"] / denominator, 4)
                if denominator else None
            )
            summary["failure_rate"] = (
                round(summary["failed_evaluation_count"] / denominator, 4)
                if denominator else None
            )
            summary["pending_rate"] = (
                round(summary["pending_turn_count"] / summary["turn_count"], 4)
                if summary["turn_count"] else None
            )

            return {
                "summary": summary,
                "sessions": sessions_payload,
            }
        except Exception as exc:
            print(f"[DirectStore] get_evaluation_coverage_metrics failed: {exc}")
            return _empty_evaluation_coverage_metrics()

    def record_agent_event(
        self,
        session_id: str,
        event_type: str,
        *,
        turn_id: str = "",
        agent_role: str = "",
        payload: Optional[Dict] = None,
    ) -> bool:
        try:
            with self.session() as db:
                db.add(
                    AgentEvent(
                        event_id=uuid.uuid4().hex,
                        session_id=session_id,
                        turn_id=turn_id or None,
                        agent_role=agent_role or "",
                        event_type=event_type,
                        payload_json=json.dumps(payload or {}, ensure_ascii=False),
                        created_at=datetime.now().isoformat(),
                    )
                )
            return True
        except Exception as exc:
            print(f"[DirectStore] record_agent_event failed: {exc}")
            return False

    def list_agent_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[Dict]:
        try:
            if limit is not None and limit <= 0:
                return []
            with self.session() as db:
                stmt = select(AgentEvent).where(AgentEvent.session_id == session_id)
                if event_type:
                    stmt = stmt.where(AgentEvent.event_type == event_type)
                stmt = stmt.order_by(AgentEvent.created_at.desc(), AgentEvent.event_id.desc())
                if limit is not None:
                    stmt = stmt.limit(limit)
                rows = db.scalars(stmt).all()
                return [self._agent_event_to_dict(row) for row in rows]
        except Exception as exc:
            print(f"[DirectStore] list_agent_events failed: {exc}")
            return []

    def upload_resume_file(self, session_id: str, file_path: str) -> Optional[Dict]:
        try:
            src = Path(file_path)
            if not src.exists():
                return None

            target_name = f"{session_id}_{uuid.uuid4().hex}_{src.name}"
            target = self.upload_dir / target_name

            if src.resolve() != target.resolve():
                if src.parent.resolve() == self.upload_dir.resolve():
                    shutil.move(str(src), str(target))
                else:
                    shutil.copy2(src, target)

            return {
                "ok": True,
                "file_path": str(target),
                "file_name": src.name,
            }
        except Exception as exc:
            print(f"[DirectStore] upload_resume_file failed: {exc}")
            return None

    def save_resume(
        self,
        session_id: str,
        file_name: str,
        file_path: str,
        ocr_result: str = "",
        user_id: int = None,
    ) -> bool:
        try:
            resume_user_id = user_id if self.resume_user_id_mode == "resume_user_id" else None
            with self.session() as db:
                db.add(
                    Resume(
                        user_id=resume_user_id,
                        session_id=session_id,
                        file_name=file_name,
                        file_path=file_path,
                        ocr_result=ocr_result,
                        upload_time=datetime.now().isoformat(),
                    )
                )
            ensure_resume_previews(file_path, file_name)
            return True
        except Exception as exc:
            print(f"[DirectStore] save_resume failed: {exc}")
            return False

    def get_resume_by_session(self, session_id: str) -> Optional[Dict]:
        try:
            with self.session() as db:
                row = db.scalars(
                    select(Resume)
                    .where(Resume.session_id == session_id)
                    .order_by(Resume.upload_time.desc(), Resume.id.desc())
                ).first()
                return self._resume_to_dict(row) if row else None
        except Exception as exc:
            print(f"[DirectStore] get_resume_by_session failed: {exc}")
            return None

    def get_latest_resume(self, user_id: int = None) -> Optional[Dict]:
        try:
            with self.session() as db:
                stmt = (
                    select(Resume)
                    .where(Resume.ocr_result.is_not(None), Resume.ocr_result != "")
                    .order_by(Resume.upload_time.desc(), Resume.id.desc())
                )
                if user_id is not None:
                    if self.resume_user_id_mode == "resume_user_id":
                        stmt = stmt.where(Resume.user_id == user_id)
                    else:
                        stmt = stmt.join(
                            InterviewSession,
                            Resume.session_id == InterviewSession.session_id,
                        ).where(InterviewSession.user_id == user_id)
                rows = db.scalars(stmt.limit(20)).all()
                for row in rows:
                    if is_reusable_ocr_result(row.ocr_result):
                        return self._resume_to_dict(row)
                return None
        except Exception as exc:
            print(f"[DirectStore] get_latest_resume failed: {exc}")
            return None

    def list_user_resumes(self, user_id: int) -> List[Dict]:
        try:
            with self.session() as db:
                stmt = self._apply_resume_user_scope(
                    select(Resume).order_by(Resume.upload_time.desc(), Resume.id.desc()),
                    user_id,
                )
                rows = db.scalars(stmt).all()
                return [self._resume_to_dict(row) for row in rows]
        except Exception as exc:
            print(f"[DirectStore] list_user_resumes failed: {exc}")
            return []

    def get_resume_file_record(self, resume_id: int, user_id: int = None) -> Optional[Dict]:
        try:
            with self.session() as db:
                stmt = select(Resume).where(Resume.id == resume_id)
                if user_id is not None:
                    stmt = self._apply_resume_user_scope(stmt, user_id)
                row = db.scalars(stmt).first()
                return self._resume_to_dict(row) if row else None
        except Exception as exc:
            print(f"[DirectStore] get_resume_file_record failed: {exc}")
            return None

    def delete_resume(self, resume_id: int, user_id: int) -> bool:
        try:
            file_path = ""
            with self.session() as db:
                stmt = self._apply_resume_user_scope(select(Resume).where(Resume.id == resume_id), user_id)
                row = db.scalars(stmt).first()
                if not row:
                    return False
                file_path = row.file_path
                db.delete(row)

            if file_path:
                cleanup_resume_assets(file_path)
            return True
        except Exception as exc:
            print(f"[DirectStore] delete_resume failed: {exc}")
            return False

    def _apply_resume_user_scope(self, stmt, user_id: int):
        if self.resume_user_id_mode == "resume_user_id":
            return stmt.where(Resume.user_id == user_id)
        return stmt.join(
            InterviewSession,
            Resume.session_id == InterviewSession.session_id,
        ).where(InterviewSession.user_id == user_id)

    def search_questions(
        self,
        query: str,
        job_filter: str = None,
        top_k: int = 5,
        difficulty: str = None,
        interview_type: str = None,
        style: str = None,
        stage: str = None,
    ) -> List[Dict]:
        try:
            job_title = _normalize_text(job_filter)
            job_key = _slugify_key(job_title) if job_title else ""
            query_text = _normalize_text(query) or job_title
            query_like = f"%{query_text}%" if query_text else "%"
            embedding = self._embed_query_literal(query_text)
            semantic_score = "0.0"
            if embedding:
                semantic_score = "greatest(0, 1 - (embedding <=> cast(:embedding as vector)))"

            sql_text = f"""
                select
                    external_id,
                    canonical_job_title,
                    question_text,
                    followup_guide,
                    rubric_5,
                    rubric_3,
                    rubric_1,
                    dimension,
                    stage,
                    metadata,
                    priority,
                    (
                        case
                            when :job_key <> '' and lower(job_key) = lower(:job_key) then 2
                            when upper(canonical_job_title) = 'ALL' then 1
                            else 0
                        end
                    ) as job_rank,
                    (
                        case
                            when :difficulty = '' then 1
                            when :difficulty = any(difficulty_tags) or 'all' = any(difficulty_tags) then 1
                            else 0
                        end
                    ) as difficulty_rank,
                    (
                        case
                            when :interview_type = '' then 1
                            when :interview_type = any(interview_types) or 'all' = any(interview_types) then 1
                            else 0
                        end
                    ) as interview_rank,
                    (
                        case
                            when :style = '' then 1
                            when :style = any(style_tags) or 'all' = any(style_tags) then 1
                            else 0
                        end
                    ) as style_rank,
                    (
                        case
                            when :stage = '' then 1
                            when lower(stage) = lower(:stage) then 1
                            when lower(stage) = 'core' then 1
                            else 0
                        end
                    ) as stage_rank,
                    (
                        case
                            when question_text ilike :query_like or followup_guide ilike :query_like then 1
                            else 0
                        end
                    ) as lexical_rank,
                    {semantic_score} as semantic_rank
                from rag.question_bank
                where is_active = true
                  and (
                    :job_key = ''
                    or lower(job_key) = lower(:job_key)
                    or upper(canonical_job_title) = 'ALL'
                  )
                  and (
                    :difficulty = ''
                    or :difficulty = any(difficulty_tags)
                    or 'all' = any(difficulty_tags)
                  )
                  and (
                    :interview_type = ''
                    or :interview_type = any(interview_types)
                    or 'all' = any(interview_types)
                  )
                  and (
                    :style = ''
                    or :style = any(style_tags)
                    or 'all' = any(style_tags)
                  )
                  and (
                    :stage = ''
                    or lower(stage) = lower(:stage)
                    or lower(stage) = 'core'
                  )
                order by
                    job_rank desc,
                    difficulty_rank desc,
                    interview_rank desc,
                    style_rank desc,
                    stage_rank desc,
                    lexical_rank desc,
                    semantic_rank desc,
                    priority desc
                limit :top_k
            """
            params = {
                "job_key": job_key,
                "difficulty": _normalize_text(difficulty).lower(),
                "interview_type": _normalize_text(interview_type).lower(),
                "style": _normalize_text(style).lower(),
                "stage": _normalize_text(stage).lower(),
                "query_like": query_like,
                "top_k": max(1, int(top_k)),
            }
            if embedding:
                params["embedding"] = embedding

            rows = self._fetch_rag_rows(sql_text, params)
            return [
                {
                    "id": row.get("external_id"),
                    "document": row.get("question_text") or "",
                    "content": row.get("question_text") or "",
                    "metadata": self._rag_metadata(
                        row,
                        "canonical_job_title",
                        "dimension",
                        "stage",
                        "rubric_5",
                        "rubric_3",
                        "rubric_1",
                    ) | {
                        "score_5": row.get("rubric_5") or "",
                        "score_3": row.get("rubric_3") or "",
                        "score_1": row.get("rubric_1") or "",
                    },
                }
                for row in rows
            ]
        except Exception as exc:
            print(f"[DirectStore] search_questions failed: {exc}")
            return []

    def search_job_descriptions(
        self,
        query: str,
        top_k: int = 3,
        difficulty: str = None,
        interview_type: str = None,
    ) -> List[Dict]:
        try:
            query_text = _normalize_text(query)
            job_key = _slugify_key(query_text) if query_text else ""
            query_like = f"%{query_text}%" if query_text else "%"
            embedding = self._embed_query_literal(query_text)
            semantic_score = "0.0"
            if embedding:
                semantic_score = "greatest(0, 1 - (embedding <=> cast(:embedding as vector)))"

            sql_text = f"""
                select
                    external_id,
                    canonical_job_title,
                    content,
                    metadata,
                    tech_tags,
                    domain_tags,
                    must_have_skills,
                    priority,
                    (
                        case
                            when :job_key <> '' and lower(job_key) = lower(:job_key) then 2
                            when canonical_job_title ilike :query_like then 1
                            else 0
                        end
                    ) as title_rank,
                    (
                        case
                            when content ilike :query_like then 1
                            else 0
                        end
                    ) as lexical_rank,
                    {semantic_score} as semantic_rank
                from rag.job_profiles
                where is_active = true
                  and (
                    :difficulty = ''
                    or :difficulty = any(difficulty_tags)
                    or 'all' = any(difficulty_tags)
                  )
                  and (
                    :interview_type = ''
                    or :interview_type = any(interview_types)
                    or 'all' = any(interview_types)
                  )
                order by
                    title_rank desc,
                    lexical_rank desc,
                    semantic_rank desc,
                    priority desc
                limit :top_k
            """
            params = {
                "job_key": job_key,
                "query_like": query_like,
                "difficulty": _normalize_text(difficulty).lower(),
                "interview_type": _normalize_text(interview_type).lower(),
                "top_k": max(1, int(top_k)),
            }
            if embedding:
                params["embedding"] = embedding

            rows = self._fetch_rag_rows(sql_text, params)
            return [
                {
                    "id": row.get("external_id"),
                    "document": row.get("content") or "",
                    "content": row.get("content") or "",
                    "metadata": self._rag_metadata(
                        row,
                        "canonical_job_title",
                        "tech_tags",
                        "domain_tags",
                        "must_have_skills",
                    ) | {
                        "job_name": row.get("canonical_job_title") or "",
                        "tags": ", ".join(row.get("tech_tags") or []),
                    },
                }
                for row in rows
            ]
        except Exception as exc:
            print(f"[DirectStore] search_job_descriptions failed: {exc}")
            return []

    def search_hr_scripts(
        self,
        query: str,
        stage: str = None,
        top_k: int = 3,
        interview_type: str = None,
        style: str = None,
    ) -> List[Dict]:
        try:
            query_text = _normalize_text(query)
            stage_text = _normalize_text(stage)
            stage_like = f"%{stage_text}%" if stage_text else "%"
            query_like = f"%{query_text}%" if query_text else "%"
            embedding = self._embed_query_literal(query_text)
            semantic_score = "0.0"
            if embedding:
                semantic_score = "greatest(0, 1 - (embedding <=> cast(:embedding as vector)))"

            sql_text = f"""
                select
                    external_id,
                    stage,
                    intent,
                    script_text,
                    fallback_text,
                    metadata,
                    priority,
                    (
                        case
                            when :stage_text <> '' and stage ilike :stage_like then 2
                            when script_text ilike :query_like then 1
                            else 0
                        end
                    ) as stage_rank,
                    (
                        case
                            when :interview_type = '' then 1
                            when :interview_type = any(interview_types) or 'all' = any(interview_types) then 1
                            else 0
                        end
                    ) as interview_rank,
                    (
                        case
                            when :style = '' then 1
                            when :style = any(style_tags) or 'all' = any(style_tags) then 1
                            else 0
                        end
                    ) as style_rank,
                    {semantic_score} as semantic_rank
                from rag.script_library
                where is_active = true
                  and (
                    :stage_text = ''
                    or stage ilike :stage_like
                    or script_text ilike :query_like
                  )
                  and (
                    :interview_type = ''
                    or :interview_type = any(interview_types)
                    or 'all' = any(interview_types)
                  )
                  and (
                    :style = ''
                    or :style = any(style_tags)
                    or 'all' = any(style_tags)
                  )
                order by
                    stage_rank desc,
                    interview_rank desc,
                    style_rank desc,
                    semantic_rank desc,
                    priority desc
                limit :top_k
            """
            params = {
                "stage_text": stage_text,
                "stage_like": stage_like,
                "query_like": query_like,
                "interview_type": _normalize_text(interview_type).lower(),
                "style": _normalize_text(style).lower(),
                "top_k": max(1, int(top_k)),
            }
            if embedding:
                params["embedding"] = embedding

            rows = self._fetch_rag_rows(sql_text, params)
            return [
                {
                    "id": row.get("external_id"),
                    "document": row.get("script_text") or "",
                    "content": row.get("script_text") or "",
                    "metadata": self._rag_metadata(row, "stage", "intent") | {
                        "fallback_text": row.get("fallback_text") or "",
                    },
                }
                for row in rows
            ]
        except Exception as exc:
            print(f"[DirectStore] search_hr_scripts failed: {exc}")
            return []

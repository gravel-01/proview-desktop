"""Storage client backed directly by Supabase/Postgres."""

import os
from pathlib import Path
from typing import Dict, List, Optional

import config as app_config
from direct_store import DirectDataStore
from services.rag_search_service import RAGSearchService
from supabase_http_store import SupabaseHTTPStore


class DataServiceClient:
    """Compatibility wrapper that prefers direct DB, then legacy Supabase HTTP."""

    def __init__(self, _base_url: str = ""):
        supabase_url = getattr(app_config, "SUPABASE_URL", None) or os.getenv("SUPABASE_URL")
        service_role_key = (
            getattr(app_config, "SUPABASE_SERVICE_ROLE_KEY", None)
            or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        )
        anon_key = getattr(app_config, "SUPABASE_ANON_KEY", None) or os.getenv("SUPABASE_ANON_KEY")

        direct_db_url = (
            getattr(app_config, "BACKEND_DB_URL", None)
            or getattr(app_config, "DATABASE_URL", None)
            or getattr(app_config, "SUPABASE_DB_URL", None)
            or os.getenv("BACKEND_DB_URL")
            or os.getenv("DATABASE_URL")
            or os.getenv("SUPABASE_DB_URL")
        )

        upload_folder = getattr(
            app_config,
            "UPLOAD_FOLDER",
            str(Path(__file__).resolve().parent / "uploaded_resumes"),
        )
        secret_key = getattr(app_config, "SECRET_KEY", "proview-dev-secret")
        self.mode = ""
        self._store = None
        self._fallback_reason = ""

        candidates = []
        if direct_db_url:
            candidates.append(
                (
                    "direct",
                    lambda: DirectDataStore(
                        db_url=direct_db_url,
                        upload_dir=upload_folder,
                        secret_key=secret_key,
                    ),
                )
            )

        if supabase_url and service_role_key:
            candidates.append(
                (
                    "supabase_http",
                    lambda: SupabaseHTTPStore(
                        supabase_url=supabase_url,
                        service_key=service_role_key,
                        upload_dir=upload_folder,
                        secret_key=secret_key,
                        anon_key=anon_key,
                        local_model_dir=getattr(app_config, "LOCAL_EMBEDDING_MODEL_DIR", ""),
                        local_max_length=getattr(app_config, "LOCAL_EMBEDDING_MAX_LENGTH", 256),
                    ),
                )
            )

        candidates.append(
            (
                "sqlite_fallback",
                lambda: DirectDataStore(
                    db_url="",
                    upload_dir=upload_folder,
                    secret_key=secret_key,
                ),
            )
        )

        init_errors = []
        for mode, factory in candidates:
            try:
                store = factory()
                health = store.health() or {}
                if health.get("db_ok"):
                    self.mode = mode
                    self._store = store
                    break
                init_errors.append(f"{mode}: {health.get('db_error') or 'health check failed'}")
            except Exception as exc:
                init_errors.append(f"{mode}: {exc}")

        if not self._store:
            raise RuntimeError(
                " ; ".join(init_errors)
                or "Missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY or BACKEND_DB_URL, DATABASE_URL, SUPABASE_DB_URL."
            )

        if self.mode == "sqlite_fallback" and init_errors:
            self._fallback_reason = " | ".join(init_errors)

        self._rag_store = None
        if self.mode == "direct" and direct_db_url:
            try:
                self._rag_store = RAGSearchService(
                    db_url=direct_db_url,
                    local_model_dir=getattr(app_config, "LOCAL_EMBEDDING_MODEL_DIR", ""),
                    local_max_length=getattr(app_config, "LOCAL_EMBEDDING_MAX_LENGTH", 256),
                )
            except Exception as exc:
                print(f"[DataServiceClient] RAG direct store init failed: {exc}")

    def health(self) -> Dict:
        health = dict(self._store.health())
        health["mode"] = self.mode
        if self._fallback_reason:
            health["fallback_reason"] = self._fallback_reason
        return health

    def storage_capabilities(self) -> Dict:
        if hasattr(self._store, "storage_capabilities"):
            return self._store.storage_capabilities()
        return {
            "append_message_returns_id": False,
            "structured_turns": False,
            "question_metadata": False,
            "turn_evaluations": False,
            "agent_events": False,
        }

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
        return self._store.create_session(
            session_id,
            candidate_name,
            position,
            interview_style,
            metadata,
            user_id,
            start_time,
        )

    def end_session(self, session_id: str) -> bool:
        return self._store.end_session(session_id)

    def get_session_statistics(self, session_id: str) -> Dict:
        return self._store.get_session_statistics(session_id)

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        return self._store.get_session_info(session_id)

    def list_sessions(self, limit: Optional[int] = 50, user_id: Optional[int] = None) -> List[Dict]:
        return self._store.list_sessions(limit=limit, user_id=user_id)

    def count_user_sessions(self, user_id) -> int:
        return self._store.count_user_sessions(user_id)

    def delete_session(self, session_id: str, user_id) -> bool:
        return self._store.delete_session(session_id, user_id)

    def append_message(self, session_id: str, role: str, content: str) -> Optional[Dict]:
        if hasattr(self._store, "append_message"):
            return self._store.append_message(session_id, role, content)
        ok = self._store.save_message(session_id, role, content)
        if not ok:
            return None
        return {"id": None, "session_id": session_id, "role": role, "content": content, "timestamp": ""}

    def save_message(self, session_id: str, role: str, content: str) -> bool:
        return self._store.save_message(session_id, role, content)

    def get_session_history(self, session_id: str) -> List[Dict]:
        return self._store.get_session_history(session_id)

    def save_evaluation(self, session_id: str, dimension: str, score: int, comment: str = "") -> bool:
        return self._store.save_evaluation(session_id, dimension, score, comment)

    def save_eval_summary(self, session_id: str, strengths: str = "", weaknesses: str = "", summary: str = "") -> bool:
        return self._store.save_eval_summary(session_id, strengths, weaknesses, summary)

    def save_eval_draft(self, session_id: str, draft: dict) -> bool:
        return self._store.save_eval_draft(session_id, draft)

    def create_interview_turn(self, **kwargs) -> Optional[Dict]:
        if hasattr(self._store, "create_interview_turn"):
            return self._store.create_interview_turn(**kwargs)
        return None

    def get_latest_pending_turn(self, session_id: str) -> Optional[Dict]:
        if hasattr(self._store, "get_latest_pending_turn"):
            return self._store.get_latest_pending_turn(session_id)
        return None

    def get_next_turn_no(self, session_id: str) -> int:
        if hasattr(self._store, "get_next_turn_no"):
            return self._store.get_next_turn_no(session_id)
        return 1

    def answer_interview_turn(self, turn_id: str, **kwargs) -> Optional[Dict]:
        if hasattr(self._store, "answer_interview_turn"):
            return self._store.answer_interview_turn(turn_id, **kwargs)
        return None

    def update_interview_turn_status(self, turn_id: str, status: str) -> Optional[Dict]:
        if hasattr(self._store, "update_interview_turn_status"):
            return self._store.update_interview_turn_status(turn_id, status)
        return None

    def skip_pending_turns(self, session_id: str) -> int:
        if hasattr(self._store, "skip_pending_turns"):
            return int(self._store.skip_pending_turns(session_id) or 0)
        return 0

    def get_interview_turn(self, turn_id: str) -> Optional[Dict]:
        if hasattr(self._store, "get_interview_turn"):
            return self._store.get_interview_turn(turn_id)
        return None

    def list_interview_turns(self, session_id: str) -> List[Dict]:
        if hasattr(self._store, "list_interview_turns"):
            return self._store.list_interview_turns(session_id)
        return []

    def save_question_metadata(self, **kwargs) -> Optional[Dict]:
        if hasattr(self._store, "save_question_metadata"):
            return self._store.save_question_metadata(**kwargs)
        return None

    def get_question_metadata(self, turn_id: str) -> Optional[Dict]:
        if hasattr(self._store, "get_question_metadata"):
            return self._store.get_question_metadata(turn_id)
        return None

    def list_question_metadata(self, session_id: str) -> List[Dict]:
        if hasattr(self._store, "list_question_metadata"):
            return self._store.list_question_metadata(session_id)
        return []

    def upsert_turn_evaluation(self, **kwargs) -> Optional[Dict]:
        if hasattr(self._store, "upsert_turn_evaluation"):
            return self._store.upsert_turn_evaluation(**kwargs)
        return None

    def list_turn_evaluations(self, session_id: str) -> List[Dict]:
        if hasattr(self._store, "list_turn_evaluations"):
            return self._store.list_turn_evaluations(session_id)
        return []

    def get_evaluation_coverage_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 100) -> Dict:
        if hasattr(self._store, "get_evaluation_coverage_metrics"):
            return self._store.get_evaluation_coverage_metrics(hours=hours, limit=limit)
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

    def record_agent_event(
        self,
        session_id: str,
        event_type: str,
        *,
        turn_id: str = "",
        agent_role: str = "",
        payload: Optional[Dict] = None,
    ) -> bool:
        if hasattr(self._store, "record_agent_event"):
            return self._store.record_agent_event(
                session_id,
                event_type,
                turn_id=turn_id,
                agent_role=agent_role,
                payload=payload,
            )
        return False

    def list_agent_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[Dict]:
        if hasattr(self._store, "list_agent_events"):
            return self._store.list_agent_events(session_id, event_type=event_type, limit=limit)
        return []

    def save_resume(
        self,
        session_id: str,
        file_name: str,
        file_path: str,
        ocr_result: str = "",
        user_id: int = None,
    ) -> bool:
        return self._store.save_resume(session_id, file_name, file_path, ocr_result, user_id)

    def upload_resume_file(self, session_id: str, file_path: str) -> Optional[Dict]:
        return self._store.upload_resume_file(session_id, file_path)

    def get_resume_by_session(self, session_id: str) -> Optional[Dict]:
        return self._store.get_resume_by_session(session_id)

    def get_latest_resume(self, user_id: int = None) -> Optional[Dict]:
        return self._store.get_latest_resume(user_id=user_id)

    def list_user_resumes(self, user_id: int) -> List[Dict]:
        return self._store.list_user_resumes(user_id)

    def get_resume_file_record(self, resume_id: int, user_id: int = None) -> Optional[Dict]:
        return self._store.get_resume_file_record(resume_id, user_id)

    def delete_resume(self, resume_id: int, user_id: int) -> bool:
        return self._store.delete_resume(resume_id, user_id)

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
        store = self._rag_store or self._store
        return store.search_questions(
            query,
            job_filter=job_filter,
            top_k=top_k,
            difficulty=difficulty,
            interview_type=interview_type,
            style=style,
            stage=stage,
        )

    def search_job_descriptions(
        self,
        query: str,
        top_k: int = 3,
        difficulty: str = None,
        interview_type: str = None,
    ) -> List[Dict]:
        store = self._rag_store or self._store
        return store.search_job_descriptions(
            query,
            top_k=top_k,
            difficulty=difficulty,
            interview_type=interview_type,
        )

    def search_hr_scripts(
        self,
        query: str,
        stage: str = None,
        top_k: int = 3,
        interview_type: str = None,
        style: str = None,
    ) -> List[Dict]:
        store = self._rag_store or self._store
        return store.search_hr_scripts(
            query,
            stage=stage,
            top_k=top_k,
            interview_type=interview_type,
            style=style,
        )

    def get_user(self, jwt_token: str) -> Optional[Dict]:
        return self._store.get_user(jwt_token)

    def get_or_create_local_user(self, profile_name: str = "") -> Optional[Dict]:
        return self._store.get_or_create_local_user(profile_name)

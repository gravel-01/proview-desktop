import json
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from services.local_embedding import LocalEmbeddingService
from services.ocr_result_utils import is_reusable_ocr_result
from services.resume_preview_service import (
    cleanup_resume_assets,
    ensure_resume_previews,
)
from utils.http_fallback import request_with_curl_fallback


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


class SupabaseHTTPStore:
    LOCAL_MODE_PROFILE_ID = "00000000-0000-0000-0000-000000000001"
    LOCAL_MODE_USERNAME = "__proview_local__"

    def __init__(
        self,
        supabase_url: str,
        service_key: str,
        upload_dir: str,
        secret_key: str,
        anon_key: Optional[str] = None,
        local_model_dir: str = "",
        local_max_length: int = 256,
    ):
        self.base_url = (supabase_url or "").rstrip("/")
        self.service_key = (service_key or "").strip()
        self.public_key = (anon_key or service_key or "").strip()
        if not self.base_url or not self.service_key:
            raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = 20
        self.headers = {
            "apikey": self.service_key,
            "Authorization": f"Bearer {self.service_key}",
            "Content-Type": "application/json",
        }
        self.auth_headers = {
            "apikey": self.public_key,
            "Content-Type": "application/json",
        }
        self._embedder = None
        if local_model_dir:
            embedder = LocalEmbeddingService(local_model_dir, local_max_length)
            self._embedder = embedder if embedder.is_available() else None

    @property
    def masked_db_url(self) -> str:
        return f"{self.base_url}/rest/v1"

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: Optional[List[tuple[str, str]]] = None,
        json_body: Optional[Dict] = None,
        prefer: str = "",
    ):
        headers = dict(self.headers)
        if prefer:
            headers["Prefer"] = prefer

        response = request_with_curl_fallback(
            method=method,
            url=f"{self.base_url}/rest/v1/{table}",
            headers=headers,
            params=params,
            json_body=json_body,
            timeout=self.timeout,
        )
        response.raise_for_status()

        if not response.text:
            return None

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def _rpc_request(self, function_name: str, payload: Optional[Dict] = None):
        response = request_with_curl_fallback(
            "POST",
            url=f"{self.base_url}/rest/v1/rpc/{function_name}",
            headers=dict(self.headers),
            json_body=payload or {},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            raise RuntimeError(
                f"Supabase RPC `{function_name}` not found. "
                "Run docs/SUPABASE_RAG_HTTP_RPC.sql in the same Supabase project first."
            )
        response.raise_for_status()

        if not response.text:
            return []

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return []

    def _auth_request(
        self,
        method: str,
        path: str,
        *,
        bearer_token: Optional[str] = None,
        json_body: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ):
        headers = dict(self.auth_headers)
        if bearer_token:
            headers["Authorization"] = f"Bearer {bearer_token}"

        response = request_with_curl_fallback(
            method=method,
            url=f"{self.base_url}/auth/v1/{path.lstrip('/')}",
            headers=headers,
            json_body=json_body,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()

        if not response.text:
            return None

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    def _user_to_dict(self, row: Dict) -> Dict:
        return {
            "id": row.get("id"),
            "username": row.get("username"),
            "display_name": row.get("display_name") or "",
            "created_at": row.get("created_at") or "",
        }

    def _session_to_dict(self, row: Dict) -> Dict:
        metadata = {}
        raw_metadata = row.get("metadata")
        if isinstance(raw_metadata, str) and raw_metadata:
            try:
                metadata = json.loads(raw_metadata)
            except Exception:
                metadata = {}
        elif isinstance(raw_metadata, dict):
            metadata = raw_metadata

        return {
            "session_id": row.get("session_id"),
            "user_id": row.get("user_id"),
            "candidate_name": row.get("candidate_name") or "",
            "position": row.get("position") or "",
            "interview_style": row.get("interview_style") or "default",
            "start_time": row.get("start_time") or "",
            "end_time": row.get("end_time"),
            "status": row.get("status") or "",
            "metadata": metadata,
            "eval_strengths": row.get("eval_strengths") or "",
            "eval_weaknesses": row.get("eval_weaknesses") or "",
            "eval_summary": row.get("eval_summary") or "",
            "eval_draft_json": row.get("eval_draft_json") or {},
        }

    def _resume_to_dict(self, row: Dict) -> Dict:
        return {
            "id": row.get("id"),
            "user_id": row.get("user_id"),
            "session_id": row.get("session_id"),
            "file_name": row.get("file_name") or "",
            "file_path": row.get("file_path") or "",
            "ocr_result": row.get("ocr_result") or "",
            "upload_time": row.get("upload_time") or "",
        }

    def _embed_query_literal(self, query: str) -> Optional[str]:
        if not self._embedder or not _normalize_text(query):
            return None
        try:
            return _vector_literal(self._embedder.embed_text(query))
        except Exception as exc:
            print(f"[SupabaseHTTPStore] local embedding failed: {exc}")
            return None

    @staticmethod
    def _rag_metadata(row: Dict, *keys: str) -> Dict:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        for key in keys:
            value = row.get(key)
            if value is not None and key not in metadata:
                metadata[key] = value
        return metadata

    def _get_profile_by_username(self, username: str) -> Optional[Dict]:
        rows = self._request(
            "GET",
            "profiles",
            params=[("select", "id,username,display_name,created_at"), ("username", f"eq.{username}"), ("limit", "1")],
        ) or []
        return rows[0] if rows else None

    def _get_profile_by_id(self, user_id: str) -> Optional[Dict]:
        rows = self._request(
            "GET",
            "profiles",
            params=[("select", "id,username,display_name,created_at"), ("id", f"eq.{user_id}"), ("limit", "1")],
        ) or []
        return rows[0] if rows else None

    def _upsert_profile(self, user_id: str, username: str, display_name: str = "") -> Optional[Dict]:
        rows = self._request(
            "POST",
            "profiles",
            json_body={
                "id": user_id,
                "username": username,
                "display_name": display_name or username,
                "created_at": datetime.now().isoformat(),
            },
            prefer="resolution=merge-duplicates,return=representation",
        ) or []
        return rows[0] if rows else self._get_profile_by_id(user_id)

    def health(self) -> Dict:
        try:
            self._request("GET", "profiles", params=[("select", "id"), ("limit", "1")])
            return {"db_ok": True, "mode": "supabase_http", "db_url": self.masked_db_url}
        except Exception as exc:
            return {"db_ok": False, "mode": "supabase_http", "db_url": self.masked_db_url, "db_error": str(exc)}

    def get_user(self, jwt_token: str) -> Optional[Dict]:
        try:
            auth_user = self._auth_request("GET", "user", bearer_token=jwt_token)
            user_id = auth_user.get("id")
            if not user_id:
                return None

            profile = self._get_profile_by_id(user_id)
            if not profile:
                metadata = auth_user.get("user_metadata") or {}
                username = metadata.get("username") or auth_user.get("email", "").split("@")[0]
                profile = self._upsert_profile(user_id, username, metadata.get("display_name") or username)
            return self._user_to_dict(profile) if profile else None
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_user failed: {exc}")
            return None

    def get_or_create_local_user(self, profile_name: str = "") -> Optional[Dict]:
        alias = _normalize_text(profile_name) or "本地用户"
        try:
            profile = self._upsert_profile(
                self.LOCAL_MODE_PROFILE_ID,
                self.LOCAL_MODE_USERNAME,
                alias,
            )
            self._claim_local_orphan_data(self.LOCAL_MODE_PROFILE_ID)
            return self._user_to_dict(profile) if profile else None
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_or_create_local_user failed: {exc}")
            return None

    def _claim_local_orphan_data(self, user_id: str) -> None:
        try:
            self._request(
                "PATCH",
                "sessions",
                params=[("user_id", "is.null")],
                json_body={"user_id": user_id},
            )
        except Exception:
            pass

        try:
            self._request(
                "PATCH",
                "resumes",
                params=[("user_id", "is.null")],
                json_body={"user_id": user_id},
            )
        except Exception:
            pass

    def create_session(
        self,
        session_id: str,
        candidate_name: str = "",
        position: str = "",
        interview_style: str = "default",
        metadata: Optional[Dict] = None,
        user_id: Optional[str] = None,
        start_time: Optional[str] = None,
    ) -> bool:
        try:
            self._request(
                "POST",
                "sessions",
                json_body={
                    "session_id": session_id,
                    "user_id": user_id,
                    "candidate_name": candidate_name,
                    "position": position,
                    "interview_style": interview_style,
                    "start_time": start_time or datetime.now().isoformat(),
                    "status": "active",
                    "metadata": metadata or {},
                },
            )
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] create_session failed: {exc}")
            return False

    def end_session(self, session_id: str) -> bool:
        try:
            self._request(
                "PATCH",
                "sessions",
                params=[("session_id", f"eq.{session_id}")],
                json_body={"end_time": datetime.now().isoformat(), "status": "completed"},
            )
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] end_session failed: {exc}")
            return False

    def get_session_info(self, session_id: str) -> Optional[Dict]:
        try:
            rows = self._request("GET", "sessions", params=[("select", "*"), ("session_id", f"eq.{session_id}"), ("limit", "1")]) or []
            return self._session_to_dict(rows[0]) if rows else None
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_session_info failed: {exc}")
            return None

    def list_sessions(self, limit: Optional[int] = 50, user_id: Optional[str] = None) -> List[Dict]:
        params: List[tuple[str, str]] = [("select", "*"), ("order", "start_time.desc")]
        if limit is not None and limit > 0:
            params.append(("limit", str(limit)))
        if user_id is not None:
            params.append(("user_id", f"eq.{user_id}"))

        try:
            rows = self._request("GET", "sessions", params=params) or []
            return [self._session_to_dict(row) for row in rows]
        except Exception as exc:
            print(f"[SupabaseHTTPStore] list_sessions failed: {exc}")
            return []

    def count_user_sessions(self, user_id: str) -> int:
        try:
            rows = self._request(
                "GET",
                "sessions",
                params=[("select", "session_id"), ("user_id", f"eq.{user_id}")],
            ) or []
            return len(rows)
        except Exception as exc:
            print(f"[SupabaseHTTPStore] count_user_sessions failed: {exc}")
            return 0

    def delete_session(self, session_id: str, user_id: str) -> bool:
        try:
            session_rows = self._request(
                "GET",
                "sessions",
                params=[("select", "session_id"), ("session_id", f"eq.{session_id}"), ("user_id", f"eq.{user_id}"), ("limit", "1")],
            ) or []
            if not session_rows:
                return False

            resume_rows = self._request(
                "GET",
                "resumes",
                params=[("select", "id,file_path"), ("session_id", f"eq.{session_id}")],
            ) or []

            self._request("DELETE", "messages", params=[("session_id", f"eq.{session_id}")])
            self._request("DELETE", "evaluations", params=[("session_id", f"eq.{session_id}")])
            self._request("DELETE", "resumes", params=[("session_id", f"eq.{session_id}")])
            self._request(
                "DELETE",
                "sessions",
                params=[("session_id", f"eq.{session_id}"), ("user_id", f"eq.{user_id}")],
            )

            for row in resume_rows:
                cleanup_resume_assets(row.get("file_path") or "")
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] delete_session failed: {exc}")
            return False

    def storage_capabilities(self) -> Dict:
        return {
            "append_message_returns_id": True,
            "structured_turns": False,
            "question_metadata": False,
            "turn_evaluations": False,
            "agent_events": False,
        }

    def append_message(self, session_id: str, role: str, content: str) -> Optional[Dict]:
        try:
            created_at = datetime.now().isoformat()
            rows = self._request(
                "POST",
                "messages",
                json_body={
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "created_at": created_at,
                },
                prefer="return=representation",
            ) or []
            row = rows[0] if isinstance(rows, list) and rows else {}
            return {
                "id": row.get("id"),
                "session_id": row.get("session_id") or session_id,
                "role": row.get("role") or role,
                "content": row.get("content") or content,
                "timestamp": row.get("created_at") or created_at,
            }
        except Exception as exc:
            print(f"[SupabaseHTTPStore] append_message failed: {exc}")
            return None

    def save_message(self, session_id: str, role: str, content: str) -> bool:
        return self.append_message(session_id, role, content) is not None

    def get_session_history(self, session_id: str) -> List[Dict]:
        try:
            rows = self._request(
                "GET",
                "messages",
                params=[("select", "role,content,created_at,id"), ("session_id", f"eq.{session_id}"), ("order", "created_at.asc"), ("order", "id.asc")],
            ) or []
            return [{"role": row.get("role", ""), "content": row.get("content", ""), "timestamp": row.get("created_at", "")} for row in rows]
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_session_history failed: {exc}")
            return []

    def save_evaluation(self, session_id: str, dimension: str, score: int, comment: str = "") -> bool:
        try:
            self._request(
                "POST",
                "evaluations",
                json_body={"session_id": session_id, "dimension": dimension, "score": score, "comment": comment, "created_at": datetime.now().isoformat()},
            )
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] save_evaluation failed: {exc}")
            return False

    def get_session_statistics(self, session_id: str) -> Dict:
        try:
            message_rows = self._request("GET", "messages", params=[("select", "role"), ("session_id", f"eq.{session_id}"), ("role", "eq.user")]) or []
            eval_rows = self._request("GET", "evaluations", params=[("select", "dimension,score,comment"), ("session_id", f"eq.{session_id}")]) or []
            evaluations = [{"dimension": row.get("dimension", ""), "score": row.get("score", 0), "comment": row.get("comment") or ""} for row in eval_rows]
            avg_score = sum(item["score"] for item in evaluations) / len(evaluations) if evaluations else 0
            return {"turn_count": len(message_rows), "evaluations": evaluations, "avg_score": avg_score}
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_session_statistics failed: {exc}")
            return {"turn_count": 0, "evaluations": [], "avg_score": 0}

    def save_eval_summary(self, session_id: str, strengths: str = "", weaknesses: str = "", summary: str = "") -> bool:
        try:
            self._request(
                "PATCH",
                "sessions",
                params=[("session_id", f"eq.{session_id}")],
                json_body={"eval_strengths": strengths, "eval_weaknesses": weaknesses, "eval_summary": summary},
            )
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] save_eval_summary failed: {exc}")
            return False

    def save_eval_draft(self, session_id: str, draft: dict) -> bool:
        try:
            self._request("PATCH", "sessions", params=[("session_id", f"eq.{session_id}")], json_body={"eval_draft_json": draft or {}})
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] save_eval_draft failed: {exc}")
            return False

    def create_interview_turn(self, **kwargs) -> Optional[Dict]:
        return None

    def get_latest_pending_turn(self, session_id: str) -> Optional[Dict]:
        return None

    def get_next_turn_no(self, session_id: str) -> int:
        return 1

    def answer_interview_turn(self, turn_id: str, **kwargs) -> Optional[Dict]:
        return None

    def update_interview_turn_status(self, turn_id: str, status: str) -> Optional[Dict]:
        return None

    def skip_pending_turns(self, session_id: str) -> int:
        return 0

    def get_interview_turn(self, turn_id: str) -> Optional[Dict]:
        return None

    def list_interview_turns(self, session_id: str) -> List[Dict]:
        return []

    def save_question_metadata(self, **kwargs) -> Optional[Dict]:
        return None

    def get_question_metadata(self, turn_id: str) -> Optional[Dict]:
        return None

    def list_question_metadata(self, session_id: str) -> List[Dict]:
        return []

    def upsert_turn_evaluation(self, **kwargs) -> Optional[Dict]:
        return None

    def list_turn_evaluations(self, session_id: str) -> List[Dict]:
        return []

    def get_evaluation_coverage_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 100) -> Dict:
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

    def get_context_compaction_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 100) -> Dict:
        return {
            "summary": {
                "session_count": 0,
                "compacted_session_count": 0,
                "context_compacted_event_count": 0,
                "context_summary_failure_event_count": 0,
                "latest_context_version": None,
                "max_context_version": None,
                "latest_compacted_at": "",
                "summary_failure_rate": None,
            },
            "sessions": [],
            "failure_reasons": [],
        }

    def get_agent_event_rollup_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 100) -> Dict:
        return {
            "summary": {
                "total_event_count": 0,
                "failure_event_count": 0,
                "distinct_session_count": 0,
                "event_type_count": 0,
                "agent_role_count": 0,
                "latest_event_at": "",
            },
            "event_types": [],
            "agent_roles": [],
            "failure_event_types": [],
            "event_type_agent_role_rollups": [],
        }

    def get_report_generation_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 100) -> Dict:
        return {
            "summary": {
                "total_event_count": 0,
                "success_count": 0,
                "failure_count": 0,
                "fallback_success_count": 0,
                "success_rate": None,
                "latest_report_event_at": "",
                "latest_success_at": "",
                "latest_failure_at": "",
            },
            "sources": [],
            "failure_reasons": [],
            "routes": [],
        }

    def get_rag_retrieval_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 100) -> Dict:
        return {
            "summary": {
                "total_event_count": 0,
                "success_count": 0,
                "miss_count": 0,
                "failure_count": 0,
                "hit_rate": None,
                "miss_rate": None,
                "failure_rate": None,
                "latest_retrieval_at": "",
                "latest_success_at": "",
                "latest_miss_at": "",
                "latest_failure_at": "",
                "job_title_matched_count": 0,
                "title_candidate_count": 0,
                "title_candidates_examined_count": 0,
                "jobs_count": 0,
                "questions_count": 0,
                "scripts_count": 0,
            },
            "stages": [],
            "statuses": [],
            "error_types": [],
        }

    def get_learning_signal_summary_metrics(self, *, hours: Optional[int] = None, limit: Optional[int] = 200) -> Dict:
        return {
            "status": "ok",
            "summary": {
                "session_count": 0,
                "turn_count": 0,
                "question_metadata_count": 0,
                "evaluation_count": 0,
                "low_score_count": 0,
                "low_score_rate": None,
                "evidence_missing_or_short_count": 0,
                "evidence_missing_or_short_rate": None,
                "suggestion_present_count": 0,
                "suggestion_present_rate": None,
                "pass_level_count": 0,
                "question_type_count": 0,
                "question_source_count": 0,
                "intended_dimension_count": 0,
                "rag_success_count": 0,
                "rag_miss_count": 0,
                "rag_failure_count": 0,
                "report_success_count": 0,
                "report_failure_count": 0,
                "report_fallback_success_count": 0,
                "agent_failure_event_count": 0,
                "low_score_threshold": 5,
                "evidence_short_threshold_chars": 24,
            },
            "dimensions": [],
            "pass_levels": [],
            "question_types": [],
            "question_sources": [],
            "intended_dimensions": [],
            "rag_retrieval": self.get_rag_retrieval_metrics(hours=hours, limit=limit),
            "report_generation": self.get_report_generation_metrics(hours=hours, limit=limit),
            "agent_failures": {
                "summary": self.get_agent_event_rollup_metrics(hours=hours, limit=limit).get("summary", {}),
                "failure_event_types": [],
                "event_type_agent_role_rollups": [],
            },
            "alerts": [],
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
        return False

    def list_agent_events(
        self,
        session_id: str,
        event_type: Optional[str] = None,
        limit: Optional[int] = 100,
    ) -> List[Dict]:
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
            return {"ok": True, "file_path": str(target), "file_name": src.name}
        except Exception as exc:
            print(f"[SupabaseHTTPStore] upload_resume_file failed: {exc}")
            return None

    def save_resume(self, session_id: str, file_name: str, file_path: str, ocr_result: str = "", user_id: Optional[str] = None) -> bool:
        try:
            self._request(
                "POST",
                "resumes",
                json_body={
                    "user_id": user_id,
                    "session_id": session_id,
                    "file_name": file_name,
                    "file_path": file_path,
                    "ocr_result": ocr_result,
                    "upload_time": datetime.now().isoformat(),
                },
            )
            ensure_resume_previews(file_path, file_name)
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] save_resume failed: {exc}")
            return False

    def get_resume_by_session(self, session_id: str) -> Optional[Dict]:
        try:
            rows = self._request(
                "GET",
                "resumes",
                params=[("select", "*"), ("session_id", f"eq.{session_id}"), ("order", "upload_time.desc"), ("order", "id.desc"), ("limit", "1")],
            ) or []
            return self._resume_to_dict(rows[0]) if rows else None
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_resume_by_session failed: {exc}")
            return None

    def get_latest_resume(self, user_id: Optional[str] = None) -> Optional[Dict]:
        params: List[tuple[str, str]] = [("select", "*"), ("ocr_result", "not.is.null"), ("ocr_result", "neq."), ("order", "upload_time.desc"), ("order", "id.desc"), ("limit", "20")]
        if user_id is not None:
            params.append(("user_id", f"eq.{user_id}"))
        try:
            rows = self._request("GET", "resumes", params=params) or []
            for row in rows:
                if is_reusable_ocr_result(row.get("ocr_result")):
                    return self._resume_to_dict(row)
            return None
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_latest_resume failed: {exc}")
            return None

    def list_user_resumes(self, user_id: str) -> List[Dict]:
        try:
            rows = self._request(
                "GET",
                "resumes",
                params=[("select", "*"), ("user_id", f"eq.{user_id}"), ("order", "upload_time.desc"), ("order", "id.desc")],
            ) or []
            return [self._resume_to_dict(row) for row in rows]
        except Exception as exc:
            print(f"[SupabaseHTTPStore] list_user_resumes failed: {exc}")
            return []

    def get_resume_file_record(self, resume_id: int, user_id: Optional[str] = None) -> Optional[Dict]:
        try:
            params: List[tuple[str, str]] = [("select", "*"), ("id", f"eq.{resume_id}"), ("limit", "1")]
            if user_id is not None:
                params.append(("user_id", f"eq.{user_id}"))
            rows = self._request("GET", "resumes", params=params) or []
            return self._resume_to_dict(rows[0]) if rows else None
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_resume_file_record failed: {exc}")
            return None

    def delete_resume(self, resume_id: int, user_id: str) -> bool:
        try:
            record = self.get_resume_file_record(resume_id, user_id=user_id)
            if not record:
                return False

            self._request(
                "DELETE",
                "resumes",
                params=[("id", f"eq.{resume_id}"), ("user_id", f"eq.{user_id}")],
            )
            cleanup_resume_assets(record.get("file_path") or "")
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] delete_resume failed: {exc}")
            return False

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
        query_text = _normalize_text(query) or _normalize_text(job_filter)
        job_title = _normalize_text(job_filter)
        try:
            rows = self._rpc_request(
                "rag_match_questions",
                {
                    "p_query": query_text,
                    "p_job_key": _slugify_key(job_title) if job_title else "",
                    "p_top_k": max(1, int(top_k)),
                    "p_difficulty": _normalize_text(difficulty).lower(),
                    "p_interview_type": _normalize_text(interview_type).lower(),
                    "p_style": _normalize_text(style).lower(),
                    "p_stage": _normalize_text(stage).lower(),
                    "p_embedding": self._embed_query_literal(query_text),
                },
            ) or []
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
            print(f"[SupabaseHTTPStore] search_questions failed: {exc}")
            return []

    def search_job_descriptions(
        self,
        query: str,
        top_k: int = 3,
        difficulty: str = None,
        interview_type: str = None,
    ) -> List[Dict]:
        query_text = _normalize_text(query)
        try:
            rows = self._rpc_request(
                "rag_match_job_profiles",
                {
                    "p_query": query_text,
                    "p_job_key": _slugify_key(query_text) if query_text else "",
                    "p_top_k": max(1, int(top_k)),
                    "p_difficulty": _normalize_text(difficulty).lower(),
                    "p_interview_type": _normalize_text(interview_type).lower(),
                    "p_embedding": self._embed_query_literal(query_text),
                },
            ) or []
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
            print(f"[SupabaseHTTPStore] search_job_descriptions failed: {exc}")
            return []

    def search_hr_scripts(
        self,
        query: str,
        stage: str = None,
        top_k: int = 3,
        interview_type: str = None,
        style: str = None,
    ) -> List[Dict]:
        query_text = _normalize_text(query)
        try:
            rows = self._rpc_request(
                "rag_match_scripts",
                {
                    "p_query": query_text,
                    "p_stage": _normalize_text(stage),
                    "p_top_k": max(1, int(top_k)),
                    "p_interview_type": _normalize_text(interview_type).lower(),
                    "p_style": _normalize_text(style).lower(),
                    "p_embedding": self._embed_query_literal(query_text),
                },
            ) or []
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
            print(f"[SupabaseHTTPStore] search_hr_scripts failed: {exc}")
            return []

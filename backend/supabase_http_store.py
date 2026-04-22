import json
import re
import shutil
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests

from services.local_embedding import LocalEmbeddingService
from services.ocr_result_utils import is_reusable_ocr_result
from services.resume_preview_service import (
    MAX_USER_RESUMES,
    cleanup_resume_assets,
    ensure_resume_previews,
)


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

        response = requests.request(
            method=method,
            url=f"{self.base_url}/rest/v1/{table}",
            headers=headers,
            params=params,
            json=json_body,
            timeout=self.timeout,
        )
        response.raise_for_status()

        if not response.text:
            return None

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return response.text

    @staticmethod
    def _first_row_from_postgrest_json(data: object) -> Optional[Dict]:
        if isinstance(data, list):
            return data[0] if data else None
        if isinstance(data, dict) and data:
            return data
        return None

    def _rpc_request(self, function_name: str, payload: Optional[Dict] = None):
        response = requests.post(
            url=f"{self.base_url}/rest/v1/rpc/{function_name}",
            headers=dict(self.headers),
            json=payload or {},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            raise RuntimeError(
                f"Supabase RPC `{function_name}` not found. "
                "Run docs/database/SUPABASE_RAG_HTTP_RPC.sql in the same Supabase project first."
            )
        response.raise_for_status()

        if not response.text:
            return []

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        return []

    @staticmethod
    def _auth_http_error_message(exc: requests.HTTPError) -> str:
        resp = exc.response
        if resp is None:
            return str(exc) or "HTTP error"
        try:
            data = resp.json()
        except Exception:
            text = (resp.text or "").strip()
            return text[:300] if text else str(exc)
        if isinstance(data, dict):
            for key in ("error_description", "message", "msg", "error"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
        return str(exc) or "HTTP error"

    def _auth_request(
        self,
        method: str,
        path: str,
        *,
        bearer_token: Optional[str] = None,
        json_body: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ):
        path_norm = path.lstrip("/")
        # GoTrue Admin API expects the service role as both apikey and Authorization.
        # Password grant and user JWT calls use the anon (public) apikey.
        use_service_key = path_norm.startswith("admin/") or bearer_token == self.service_key
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if use_service_key:
            headers["apikey"] = self.service_key
            auth_bearer = bearer_token if bearer_token is not None else self.service_key
            headers["Authorization"] = f"Bearer {auth_bearer}"
        else:
            headers["apikey"] = self.public_key
            if bearer_token:
                headers["Authorization"] = f"Bearer {bearer_token}"

        response = requests.request(
            method=method,
            url=f"{self.base_url}/auth/v1/{path_norm}",
            headers=headers,
            json=json_body,
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

    def _username_to_auth_email(self, username: str) -> str:
        username = (username or "").strip().lower()
        if "@" in username:
            return username
        return f"{username}@proview.local"

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
        """Lightweight REST probe; retries a few times on transient TLS / connection drops."""
        last_err: Optional[Exception] = None
        for attempt in range(3):
            try:
                self._request("GET", "profiles", params=[("select", "id"), ("limit", "1")])
                return {"db_ok": True, "mode": "supabase_http", "db_url": self.masked_db_url}
            except Exception as exc:
                last_err = exc
                if attempt < 2:
                    time.sleep(0.35 * (attempt + 1))
        return {
            "db_ok": False,
            "mode": "supabase_http",
            "db_url": self.masked_db_url,
            "db_error": str(last_err) if last_err else "unknown",
        }

    def register(self, username: str, password: str, display_name: str = "") -> Optional[Dict]:
        username = (username or "").strip().lower()
        password = password or ""
        display_name = (display_name or "").strip()

        if not username or not password:
            return {"error": "用户名和密码不能为空", "status_code": 400}

        try:
            if self._get_profile_by_username(username):
                return {"error": "用户名已存在", "status_code": 409}

            auth_user = self._auth_request(
                "POST",
                "admin/users",
                bearer_token=self.service_key,
                json_body={
                    "email": self._username_to_auth_email(username),
                    "password": password,
                    "email_confirm": True,
                    "user_metadata": {"username": username, "display_name": display_name or username},
                },
            )
            if not isinstance(auth_user, dict):
                return {
                    "error": "注册失败：Auth 返回格式异常",
                    "status_code": 502,
                }
            user_id = auth_user.get("id")
            if not user_id:
                return {
                    "error": "注册失败：未获得用户 ID，请检查 Supabase Auth 与密钥配置",
                    "status_code": 502,
                }

            profile = self._upsert_profile(user_id, username, display_name or username)
            login_result = self.login(username, password)
            if not login_result:
                return {
                    "error": "注册成功但无法完成登录，请稍后重试或尝试手动登录",
                    "status_code": 502,
                }
            if login_result.get("error"):
                return {
                    "error": f"注册成功但登录失败：{login_result.get('error')}",
                    "status_code": int(login_result.get("status_code") or 502),
                }
            if profile:
                login_result["user"] = self._user_to_dict(profile)
            return login_result
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 422:
                return {"error": "用户名已存在", "status_code": 409}
            detail = self._auth_http_error_message(exc)
            print(f"[SupabaseHTTPStore] register failed: {exc} — {detail}")
            code = exc.response.status_code if exc.response is not None else 502
            return {"error": f"注册失败：{detail}", "status_code": code if 400 <= code < 600 else 502}
        except requests.RequestException as exc:
            print(f"[SupabaseHTTPStore] register network/transport error: {exc!r}")
            tip = (str(exc).strip() or type(exc).__name__)[:200]
            return {
                "error": (
                    "注册失败：无法访问 Supabase（"
                    f"{tip}"
                    "）。请核对 SUPABASE_URL（须为 https://xxx.supabase.co）、网络/代理/VPN，"
                    "以及 SUPABASE_SERVICE_ROLE_KEY 是否为「service_role」密钥。"
                ),
                "status_code": 502,
            }
        except Exception as exc:
            print(f"[SupabaseHTTPStore] register failed: {exc!r}")
            tip = (str(exc).strip() or type(exc).__name__)[:200]
            return {
                "error": (
                    "注册失败："
                    f"{tip}"
                    "。请查看后端日志中的完整堆栈；常见原因还包括 Auth 返回非 JSON、profiles 表缺失或 RLS 拒绝。"
                ),
                "status_code": 502,
            }

    def login(self, username: str, password: str) -> Optional[Dict]:
        username = (username or "").strip().lower()
        password = password or ""

        try:
            auth_result = self._auth_request(
                "POST",
                "token",
                params={"grant_type": "password"},
                json_body={"email": self._username_to_auth_email(username), "password": password},
            )
            token = auth_result.get("access_token")
            auth_user = auth_result.get("user") or {}
            if not token:
                return {"error": "invalid credentials", "status_code": 401}

            profile = self._get_profile_by_id(auth_user.get("id")) if auth_user.get("id") else None
            if not profile and auth_user.get("id"):
                profile = self._upsert_profile(
                    auth_user["id"],
                    username,
                    (auth_user.get("user_metadata") or {}).get("display_name") or username,
                )

            user_dict = self._user_to_dict(profile) if profile else {
                "id": auth_user.get("id"),
                "username": username,
                "display_name": (auth_user.get("user_metadata") or {}).get("display_name") or username,
                "created_at": auth_user.get("created_at") or "",
            }
            return {"token": token, "user": user_dict}
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code in (400, 401):
                return {"error": "用户名或密码错误", "status_code": 401}
            detail = self._auth_http_error_message(exc)
            print(f"[SupabaseHTTPStore] login failed: {exc} — {detail}")
            code = exc.response.status_code if exc.response is not None else 502
            return {"error": f"登录失败：{detail}", "status_code": code if 400 <= code < 600 else 502}
        except requests.RequestException as exc:
            print(f"[SupabaseHTTPStore] login network/transport error: {exc!r}")
            tip = (str(exc).strip() or type(exc).__name__)[:200]
            return {
                "error": (
                    "登录失败：无法访问 Supabase（"
                    f"{tip}"
                    "）。请核对 SUPABASE_URL、网络与 SUPABASE_ANON_KEY / 密钥配置。"
                ),
                "status_code": 502,
            }
        except Exception as exc:
            print(f"[SupabaseHTTPStore] login failed: {exc!r}")
            tip = (str(exc).strip() or type(exc).__name__)[:200]
            return {"error": f"登录失败：{tip}。请查看后端日志。", "status_code": 502}

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

    def get_nav_preferences(self, user_id: str) -> Dict:
        try:
            rows = self._request(
                "GET",
                "user_nav_preferences",
                params=[("select", "goal,stage,difficulty,career,updated_at"), ("user_id", f"eq.{user_id}"), ("limit", "1")],
            ) or []
            return rows[0] if rows else {}
        except Exception as exc:
            print(f"[SupabaseHTTPStore] get_nav_preferences failed: {exc}")
            return {}

    def upsert_nav_preferences(self, user_id: str, goal: str, stage: str, difficulty: str, career: str) -> Dict:
        """Upsert nav prefs. PostgREST may return 2xx with an empty body; in that case read back the row."""
        headers = dict(self.headers)
        headers["Prefer"] = "resolution=merge-duplicates,return=representation"
        url = f"{self.base_url}/rest/v1/user_nav_preferences"
        json_body = {
            "user_id": user_id,
            "goal": goal,
            "stage": stage,
            "difficulty": difficulty,
            "career": career,
            "updated_at": datetime.now().isoformat(),
        }
        response = requests.post(url, headers=headers, json=json_body, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            detail = ""
            if exc.response is not None and exc.response.text:
                detail = exc.response.text[:800]
            raise RuntimeError(f"user_nav_preferences REST upsert failed: {exc} {detail}".strip()) from exc

        row = None
        if response.text and "application/json" in response.headers.get("content-type", ""):
            row = self._first_row_from_postgrest_json(response.json())
        if row:
            return row

        stored = self.get_nav_preferences(user_id)
        if stored:
            return stored

        raise RuntimeError(
            "user_nav_preferences upsert returned no representation and GET returned empty. "
            "Run docs/database/SUPABASE_USER_NAV_PREFERENCES.sql in your Supabase project, "
            "and ensure public.profiles contains this user_id (FK)."
        )

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

    def list_sessions(self, limit: int = 50, user_id: Optional[str] = None) -> List[Dict]:
        params: List[tuple[str, str]] = [("select", "*"), ("order", "start_time.desc"), ("limit", str(limit))]
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

    def save_message(self, session_id: str, role: str, content: str) -> bool:
        try:
            self._request(
                "POST",
                "messages",
                json_body={"session_id": session_id, "role": role, "content": content, "created_at": datetime.now().isoformat()},
            )
            return True
        except Exception as exc:
            print(f"[SupabaseHTTPStore] save_message failed: {exc}")
            return False

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
            if user_id is not None:
                self.enforce_resume_limit(user_id, MAX_USER_RESUMES)
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

    def enforce_resume_limit(self, user_id: str, keep: int) -> int:
        removed_count = 0
        try:
            rows = self._request(
                "GET",
                "resumes",
                params=[("select", "*"), ("user_id", f"eq.{user_id}"), ("order", "upload_time.desc"), ("order", "id.desc")],
            ) or []
            stale_rows = rows[max(0, keep):]
            for row in stale_rows:
                resume_id = row.get("id")
                if resume_id is None:
                    continue
                self._request(
                    "DELETE",
                    "resumes",
                    params=[("id", f"eq.{resume_id}"), ("user_id", f"eq.{user_id}")],
                )
                cleanup_resume_assets(row.get("file_path") or "")
                removed_count += 1
            return removed_count
        except Exception as exc:
            print(f"[SupabaseHTTPStore] enforce_resume_limit failed: {exc}")
            return removed_count

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

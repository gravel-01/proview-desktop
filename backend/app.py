import base64
import os
import uuid
import json as json_mod
import traceback
import queue
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename
from config import (
    UPLOAD_FOLDER, DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
    SECRET_KEY, CORS_ORIGINS, BAIDU_APP_KEY, BAIDU_SECRET_KEY,
    ERNIE_API_KEY, ERNIE_BASE_URL, RAG_DB_PATH
)
from auth import create_token, require_session, revoke_session
from core.model_registry import init_providers, get_provider, get_default_provider, list_available_providers
from services.ocr_result_utils import is_reusable_ocr_result, normalize_reusable_ocr_result
from services.resume_preview_service import MAX_USER_RESUMES, get_resume_preview_summary
from services.career_planning_service import CareerPlanningService
from services.career_planning_docs import CareerPlanningDocumentRepository
from services.navigation_preferences_service import calculate_module_order, sanitize_preferences

# 直接导入 OCR 工具（不再依赖 Agent 自主决策）
try:
    from core.tools.ocr_processing import perform_ocr, perform_ocr_full
    OCR_AVAILABLE = True
except Exception as e:
    print(f"[WARN] Import OCR tools failed: {e}")
    OCR_AVAILABLE = False

# 创建 Flask app 实例
app = Flask(__name__)
app.secret_key = SECRET_KEY
CORS(app, origins=CORS_ORIGINS, supports_credentials=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 初始化模型注册表
init_providers(
    deepseek_api_key=DEEPSEEK_API_KEY,
    deepseek_base_url=DEEPSEEK_BASE_URL,
    ernie_api_key=ERNIE_API_KEY,
    ernie_base_url=ERNIE_BASE_URL,
)

# 加载岗位数据（启动时一次性读取 Excel）
_positions: list[str] = []
def _decode_legacy_mojibake(value: str) -> str:
    return base64.b64decode(value).decode("utf-8")


_LEGACY_GARBLED_SENIOR_FRONTEND_TITLE_A = _decode_legacy_mojibake(
    "5qWC5qiG6aqC5Zus5bSc5ayl5LyC54C14oaC4oCT6Za45qyS5Z615rW85oSu57Kz54Cj7oeO"
)
_LEGACY_GARBLED_SENIOR_FRONTEND_TITLE_B = _decode_legacy_mojibake(
    "5qWg5qiH5rW36Y2Z5qiA5Zus7oGs5a+u7pKC5bGd6Y+C7oCX5aCu55KHz7flmp8="
)
_garbled_job_title_map = {
    _LEGACY_GARBLED_SENIOR_FRONTEND_TITLE_A: "高级前端开发工程师",
    _LEGACY_GARBLED_SENIOR_FRONTEND_TITLE_B: "高级前端开发工程师",
}
try:
    import openpyxl
    if os.path.exists(RAG_DB_PATH):
        _wb = openpyxl.load_workbook(RAG_DB_PATH, read_only=True)
        _ws = _wb[_wb.sheetnames[0]]
        _seen = set()
        for row in _ws.iter_rows(min_row=2, values_only=True):
            name = row[1]  # B 列：岗位名称
            if name and str(name).strip() and str(name).strip() not in _seen:
                _seen.add(str(name).strip())
                _positions.append(str(name).strip())
        _wb.close()
        print(f"[OK] Loaded {len(_positions)} positions")
    else:
        print(f"[WARN] RAG database file not found: {RAG_DB_PATH}")
except Exception as e:
    print(f"[WARN] Failed to load positions: {e}")

# 导入核心模块
def normalize_job_title(value):
    text = str(value or "").strip()
    if not text:
        return ""
    return _garbled_job_title_map.get(text, text)


def normalize_session_info(session_info):
    if not isinstance(session_info, dict):
        return session_info
    normalized = dict(session_info)
    if "position" in normalized:
        normalized["position"] = normalize_job_title(normalized.get("position"))
    return normalized


def normalize_session_list(sessions):
    return [normalize_session_info(session) for session in (sessions or [])]


def _get_current_user_id_from_auth_header():
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or not data_client:
        return None

    user_info = data_client.get_user(auth_header[7:])
    if user_info and "id" in user_info:
        return user_info["id"]
    return None


def _parse_career_plan_generate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("请求体必须是 JSON 对象")

    target_role = str(payload.get("target_role") or "").strip()
    career_goal = str(payload.get("career_goal") or "").strip()

    try:
        horizon_months = int(payload.get("horizon_months") or 6)
    except (TypeError, ValueError) as exc:
        raise ValueError("horizon_months 必须是整数") from exc

    refresh = bool(payload.get("refresh", False))
    return target_role, career_goal, horizon_months, refresh


def _build_nav_preference_payload(raw_prefs):
    prefs, warnings = sanitize_preferences(raw_prefs)
    for message in warnings:
        print(message)
    module_order = calculate_module_order(prefs)
    return {
        "preferences": prefs,
        "module_order": module_order,
    }


def _friendly_nav_preferences_save_error(exc: BaseException) -> str:
    """Map storage/PostgREST errors to actionable UI text (e.g. missing Supabase table)."""
    raw = str(exc)
    if "PGRST205" in raw or (
        "Could not find the table" in raw and "user_nav_preferences" in raw
    ):
        return (
            "Supabase 中还没有数据表 public.user_nav_preferences。"
            "请登录 Supabase 控制台 → SQL Editor，执行本仓库 "
            "docs/database/SUPABASE_USER_NAV_PREFERENCES.sql 中的全部语句，"
            "执行成功后等待约 1 分钟再点击提交。"
        )
    if "SSL" in raw or "SSLError" in raw or "UNEXPECTED_EOF" in raw:
        return (
            "连接 Supabase 时出现 SSL/网络中断，请检查网络、代理或 VPN 后重试。"
            "若频繁出现，可尝试更换网络或稍后重试。"
        )
    return "保存导航偏好失败，请稍后重试"


def _build_history_quota(user_id):
    saved_count = data_client.count_user_sessions(user_id) if data_client else 0
    remaining = max(0, MAX_SAVED_HISTORY - saved_count)
    return {
        "saved_count": saved_count,
        "max_saved": MAX_SAVED_HISTORY,
        "remaining": remaining,
        "can_save": remaining > 0,
    }


def _parse_iso_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        return None

    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_new_user(user_info):
    if not user_info or "id" not in user_info:
        return False

    created_at = _parse_iso_datetime(user_info.get("created_at"))
    if not created_at:
        return False

    return datetime.now(timezone.utc) - created_at <= NEW_USER_HISTORY_GRACE_PERIOD


def _serialize_resume_library_record(record):
    payload = dict(record or {})
    preview_summary = get_resume_preview_summary(payload.get("file_path") or "", payload.get("file_name") or "")
    payload["file_kind"] = preview_summary["file_kind"]
    payload["preview_page_count"] = preview_summary["preview_page_count"]
    payload["can_preview"] = preview_summary["has_preview"]
    payload["preview_cover_url"] = (
        f"/api/my-resumes/{payload['id']}/preview/1" if preview_summary["has_preview"] else ""
    )
    payload["preview_image_urls"] = [
        f"/api/my-resumes/{payload['id']}/preview/{index + 1}"
        for index in range(preview_summary["preview_page_count"])
    ]
    return payload


AGENT_AVAILABLE = False
STORAGE_AVAILABLE = False
STORAGE_STATUS = {
    "connected": False,
    "mode": None,
    "url": None,
    "db_error": None,
    "fallback_reason": None,
}
STORAGE_INIT_ERROR = None
data_client = None
career_planning_service = None
career_planning_docs = CareerPlanningDocumentRepository()
MAX_SAVED_HISTORY = 15
NEW_USER_HISTORY_GRACE_PERIOD = timedelta(minutes=30)


def _refresh_storage_status():
    global STORAGE_AVAILABLE, STORAGE_STATUS

    if not data_client:
        STORAGE_AVAILABLE = False
        STORAGE_STATUS = {
            "connected": False,
            "mode": None,
            "url": None,
            "db_error": STORAGE_INIT_ERROR or "storage client not initialized",
            "fallback_reason": None,
        }
        return STORAGE_STATUS

    health = data_client.health() or {}
    probe_ok = bool(health.get("db_ok"))
    # 客户端已创建即可走业务 API（注册/登录等）；瞬时 SSL/网络失败不应把 STORAGE_AVAILABLE 永久打成 False。
    # 真实连通性看 STORAGE_STATUS["connected"]（/api/health 等）。
    STORAGE_AVAILABLE = True
    STORAGE_STATUS = {
        "connected": probe_ok,
        "mode": health.get("mode", getattr(data_client, "mode", None)),
        "url": health.get("db_url") or health.get("url"),
        "db_error": health.get("db_error") if not probe_ok else None,
        "fallback_reason": health.get("fallback_reason"),
    }
    return STORAGE_STATUS

try:
    from core.langchain_agent import LangChainInterviewAgent
    AGENT_AVAILABLE = True
except Exception as e:
    print(f"[WARN] Import langchain_agent failed: {e}")

# Supabase/Postgres 存储客户端
try:
    from data_client import DataServiceClient
    data_client = DataServiceClient()
    _storage = _refresh_storage_status()
    if _storage.get("connected"):
        print(f"[storage] connected via {_storage.get('mode')}: {_storage.get('url')}")
    else:
        print(
            f"[storage] client ready; health probe failed (registration/login will still be attempted): "
            f"{_storage.get('db_error')}"
        )
    try:
        career_planning_service = CareerPlanningService(data_client)
        print(f"[career] schema ready: {career_planning_service.health()}")
    except Exception as career_error:
        career_planning_service = None
        print(f"[career] unavailable: {career_error}")
except Exception as e:
    STORAGE_INIT_ERROR = str(e)
    print(f"[storage] unavailable: {e}")
    data_client = None
    career_planning_service = None
    _refresh_storage_status()

# 健康探测失败时，按间隔重跑 health()，更新 STORAGE_STATUS["connected"]（供 /api/health 与运维观察）。
_storage_last_reprobe_monotonic = None
_STORAGE_REPROBE_MIN_INTERVAL_SEC = 10.0


def _maybe_reprobe_storage():
    global _storage_last_reprobe_monotonic
    if data_client is None or STORAGE_STATUS.get("connected"):
        return
    import time

    now = time.monotonic()
    if (
        _storage_last_reprobe_monotonic is not None
        and now - _storage_last_reprobe_monotonic < _STORAGE_REPROBE_MIN_INTERVAL_SEC
    ):
        return
    _storage_last_reprobe_monotonic = now
    _refresh_storage_status()
    if STORAGE_STATUS.get("connected"):
        print(f"[storage] health recovered: {STORAGE_STATUS.get('mode')} {STORAGE_STATUS.get('url')}")


@app.before_request
def _before_request_reprobe_storage():
    _maybe_reprobe_storage()


# 导入简历分析模块
ANALYZER_AVAILABLE = False
try:
    from core.resume_analyzer import ResumeAnalyzer
    ANALYZER_AVAILABLE = True
except Exception as e:
    print(f"[WARN] Import ResumeAnalyzer failed: {e}")

# 导入百度语音模块
SPEECH_AVAILABLE = False
_speech_client = None
try:
    if BAIDU_APP_KEY and BAIDU_SECRET_KEY:
        from core.baidu_speech import BaiduSpeechClient
        _speech_client = BaiduSpeechClient(
            app_key=BAIDU_APP_KEY, secret_key=BAIDU_SECRET_KEY
        )
        SPEECH_AVAILABLE = True
        print("[OK] Baidu speech module loaded")
    else:
        print("[WARN] BAIDU_APP_KEY / BAIDU_SECRET_KEY not configured, speech unavailable")
except Exception as e:
    print(f"[WARN] Import Baidu speech module failed: {e}")

# Per-session agent 管理
_agents: dict[str, object] = {}
_chat_stop_flags: dict[str, bool] = {}
_session_models: dict[str, str] = {}  # session_id → model provider key

# Per-session 评估观察者
try:
    from core.eval_observer import EvalObserver
    _observers: dict[str, "EvalObserver"] = {}
    OBSERVER_AVAILABLE = True
except Exception as _e:
    print(f"[WARN] Import EvalObserver failed: {_e}")
    _observers = {}
    OBSERVER_AVAILABLE = False


def get_agent(session_id: str, model_provider: str = ""):
    """获取或创建 session 对应的 agent 实例"""
    if session_id in _agents:
        return _agents[session_id]
    if not AGENT_AVAILABLE:
        return None

    # 根据前端选择的模型提供商获取配置
    provider = get_provider(model_provider) if model_provider else None
    if not provider or not provider.available:
        provider = get_default_provider()

    agent = LangChainInterviewAgent(
        api_key=provider.api_key,
        base_url=provider.base_url,
        model=provider.model,
        temperature=0.7,
        verbose=False
    )
    _agents[session_id] = agent
    _session_models[session_id] = provider.key

    # 创建评估观察者
    if OBSERVER_AVAILABLE and hasattr(agent, 'llm_client') and agent.llm_client:
        observer = EvalObserver(
            session_id=session_id,
            llm_client=agent.llm_client,
            data_client=data_client,
        )
        # 设置 SSE 推送回调（将在 chat-stream 中绑定到具体 SSE 响应）
        _observers[session_id] = observer

    return agent


def _build_debug_info(agent, session_id: str = ""):
    """收集 agent 调试信息"""
    if not agent:
        return {}
    provider_key = _session_models.get(session_id, "unknown")
    provider = get_provider(provider_key)
    info = {
        "system_prompt": getattr(agent, 'prompt', ''),
        "chat_history": agent.get_chat_history() if hasattr(agent, 'get_chat_history') else [],
        "agent_mode": "LangChain" if hasattr(agent, 'agent_executor') and agent.agent_executor else "Fallback",
        "tools_available": [tool.name for tool in agent.tools] if hasattr(agent, 'tools') else [],
        "model_provider": provider_key,
        "model_name": provider.model if provider else getattr(agent, 'model_name', 'unknown'),
        "model_label": provider.label if provider else provider_key,
        "data_service": {
            **STORAGE_STATUS,
        },
    }
    return info


def _build_rag_debug_details(
    *,
    query: str = "",
    job_title: str = "",
    difficulty: str = "",
    interview_type: str = "",
    style: str = "",
    stage: str = "",
    status: str = "empty",
    error: str = "",
    jobs: list | None = None,
    questions: list | None = None,
    scripts: list | None = None,
):
    jobs = jobs or []
    questions = questions or []
    scripts = scripts or []

    def _truncate(value: str, limit: int = 240) -> str:
        text = (value or "").strip()
        if len(text) <= limit:
            return text
        return text[:limit] + "..."

    return {
        "query": query,
        "job_title": job_title,
        "difficulty": difficulty,
        "interview_type": interview_type,
        "style": style,
        "stage": stage,
        "status": status,
        "error": error,
        "counts": {
            "jobs": len(jobs),
            "questions": len(questions),
            "scripts": len(scripts),
        },
        "jobs": [
            {
                "id": item.get("id"),
                "document": _truncate(item.get("document") or item.get("content") or "", 400),
                "metadata": item.get("metadata") or {},
            }
            for item in jobs
        ],
        "questions": [
            {
                "id": item.get("id"),
                "document": _truncate(item.get("document") or item.get("content") or "", 260),
                "metadata": item.get("metadata") or {},
            }
            for item in questions
        ],
        "scripts": [
            {
                "id": item.get("id"),
                "document": _truncate(item.get("document") or item.get("content") or "", 260),
                "metadata": item.get("metadata") or {},
            }
            for item in scripts
        ],
    }


def _has_self_intro_request(response_text: str) -> bool:
    text = (response_text or "").strip()
    if not text:
        return False
    keywords = [
        "自我介绍",
        "介绍一下自己",
        "介绍一下",
        "介绍自己",
        "简要介绍自己",
        "简单介绍自己",
        "先做一个介绍",
        "先做个介绍",
    ]
    if any(keyword in text for keyword in keywords):
        return True
    if ("2-3分钟" in text or "两三分钟" in text or "几分钟" in text) and "介绍" in text:
        return True
    return False


# PromptGenerator 延迟导入（问题4完整实现后启用）
_prompt_generator = None
EVAL_OBSERVER_DRAIN_TIMEOUT_SECONDS = 3.0


def _try_generate_prompt(job_title, interview_type, difficulty, style, resume_summary):
    """尝试使用 PromptGenerator 生成定制 prompt，失败返回空字符串（降级到静态模板）"""
    global _prompt_generator
    try:
        if _prompt_generator is None:
            from core.prompt_generator import PromptGenerator
            _prompt_generator = PromptGenerator(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL
            )
        return _prompt_generator.generate(
            job_title=job_title,
            interview_type=interview_type,
            difficulty=difficulty,
            style=style,
            resume_summary=resume_summary
        )
    except ImportError:
        # prompt_generator.py 尚未创建，静默降级
        return ""
    except Exception as e:
        print(f"[WARN] PromptGenerator call failed, fallback to static template: {e}")
        return ""


@app.route('/api/health', methods=['GET'])
def health():
    _refresh_storage_status()
    return jsonify({
        "status": "ok",
        "data_service": {
            **STORAGE_STATUS,
        },
        "agent_available": AGENT_AVAILABLE,
        "ocr_available": OCR_AVAILABLE,
    })


@app.route('/api/models', methods=['GET'])
def get_models():
    """返回可用的模型提供商列表"""
    return jsonify({"models": list_available_providers()})


@app.route('/api/positions', methods=['GET'])
def get_positions():
    """返回岗位列表"""
    return jsonify({"positions": _positions})


# ==========================================
# 用户认证 API（转发到数据服务）
# ==========================================

@app.route('/api/auth/register', methods=['POST'])
def auth_register():
    if not data_client:
        return jsonify({
            "status": "error",
            "message": "数据服务未初始化。请配置 SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY（推荐）或 BACKEND_DB_URL / DATABASE_URL。",
        }), 503
    data = request.json or {}
    result = data_client.register(
        username=data.get('username', ''),
        password=data.get('password', ''),
        display_name=data.get('display_name', ''),
    )
    if not result:
        return jsonify({"status": "error", "message": "数据服务连接失败"}), 502
    if "error" in result:
        return jsonify({"status": "error", "message": result["error"]}), result.get("status_code", 400)
    return jsonify({"status": "success", **result})


@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    if not data_client:
        return jsonify({
            "status": "error",
            "message": "数据服务未初始化。请配置 SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY（推荐）或 BACKEND_DB_URL / DATABASE_URL。",
        }), 503
    data = request.json or {}
    result = data_client.login(
        username=data.get('username', ''),
        password=data.get('password', ''),
    )
    if not result:
        return jsonify({"status": "error", "message": "数据服务连接失败"}), 502
    if "error" in result:
        return jsonify({"status": "error", "message": result["error"]}), result.get("status_code", 401)
    return jsonify({"status": "success", **result})


@app.route('/api/auth/me', methods=['GET'])
def auth_me():
    if not data_client:
        return jsonify({
            "status": "error",
            "message": "数据服务未初始化。请配置 SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY（推荐）或 BACKEND_DB_URL / DATABASE_URL。",
        }), 503
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return jsonify({"status": "error", "message": "缺少认证 token"}), 401
    jwt_token = auth_header[7:]
    user = data_client.get_user(jwt_token)
    if not user:
        return jsonify({"status": "error", "message": "token 无效或已过期"}), 401
    return jsonify({"status": "success", "user": user})


@app.route('/api/nav-preferences', methods=['GET'])
def get_nav_preferences():
    if not data_client:
        return jsonify({"status": "error", "message": "数据服务不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    stored = data_client.get_nav_preferences(user_id) or {}
    payload = _build_nav_preference_payload(stored)
    return jsonify({"status": "success", "has_saved": bool(stored), **payload})


@app.route('/api/nav-preferences', methods=['PUT'])
def update_nav_preferences():
    if not data_client:
        return jsonify({"status": "error", "message": "数据服务不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    incoming = request.get_json(silent=True) or {}
    payload = _build_nav_preference_payload(incoming)
    prefs = payload["preferences"]
    try:
        saved = data_client.upsert_nav_preferences(
            user_id=user_id,
            goal=prefs["goal"],
            stage=prefs["stage"],
            difficulty=prefs["difficulty"],
            career=prefs["career"],
        )
    except Exception as exc:
        print(f"[app] upsert_nav_preferences failed: {exc}")
        return jsonify({"status": "error", "message": _friendly_nav_preferences_save_error(exc)}), 502
    if not saved:
        return jsonify({"status": "error", "message": "保存导航偏好失败，请稍后重试"}), 502
    return jsonify({
        "status": "success",
        "has_saved": True,
        "preferences": {
            "goal": saved.get("goal", prefs["goal"]),
            "stage": saved.get("stage", prefs["stage"]),
            "difficulty": saved.get("difficulty", prefs["difficulty"]),
            "career": saved.get("career", prefs["career"]),
        },
        "module_order": payload["module_order"],
    })


# ── 面试历史 ──

@app.route('/api/history/sessions', methods=['GET'])
def list_user_sessions():
    """获取当前登录用户的面试历史列表"""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer ") or not data_client:
        return jsonify([])
    user_info = data_client.get_user(auth_header[7:])
    if not user_info or "id" not in user_info:
        return jsonify([])
    user_id = user_info["id"]
    sessions = data_client.list_sessions(limit=50, user_id=user_id)
    # 兼容旧数据：如果按 user_id 查不到，也返回 user_id 为空的 session
    if not sessions and not _is_new_user(user_info):
        all_sessions = data_client.list_sessions(limit=20)
        sessions = [s for s in all_sessions if not s.get("user_id")]
    return jsonify(normalize_session_list(sessions))


@app.route('/api/history/sessions/<session_id>', methods=['GET'])
def get_session_detail(session_id):
    """获取某次面试的完整详情（元信息 + 聊天记录 + 评分）"""
    if not data_client:
        return jsonify({"error": "数据服务不可用"}), 503
    session_info = normalize_session_info(data_client.get_session_info(session_id))
    if not session_info:
        return jsonify({"error": "会话不存在"}), 404
    messages = data_client.get_session_history(session_id)
    stats = data_client.get_session_statistics(session_id)
    return jsonify({
        "session": session_info,
        "messages": messages,
        "stats": stats,
    })


@app.route('/api/history/sessions/<session_id>', methods=['DELETE'])
def delete_session_detail(session_id):
    if not data_client:
        return jsonify({"status": "error", "message": "storage unavailable"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "missing auth token"}), 401

    deleted = data_client.delete_session(session_id, user_id)
    if not deleted:
        return jsonify({"status": "error", "message": "session not found"}), 404

    return jsonify({
        "status": "success",
        "quota": _build_history_quota(user_id),
    })


@app.route('/api/history/quota', methods=['GET'])
def get_history_quota():
    if not data_client:
        return jsonify({"status": "error", "message": "storage unavailable"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "missing auth token"}), 401

    return jsonify(_build_history_quota(user_id))


@app.route('/api/history/resume/<session_id>', methods=['GET'])
def get_session_resume(session_id):
    """获取某次面试关联的简历 OCR 文本"""
    if not data_client:
        return jsonify(None)
    resume = data_client.get_resume_by_session(session_id)
    return jsonify(resume)


@app.route('/api/history/resume/latest', methods=['GET'])
def get_latest_resume():
    """获取当前用户最近一条有 OCR 结果的简历"""
    if not data_client:
        return jsonify(None)
    user_id = _get_current_user_id_from_auth_header()
    resume = data_client.get_latest_resume(user_id=user_id)
    return jsonify(resume)


@app.route('/api/my-resumes', methods=['GET'])
def list_my_resumes():
    """获取当前用户的所有简历列表"""
    if not data_client:
        return jsonify([])
    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify([])
    data_client.enforce_resume_limit(user_id, MAX_USER_RESUMES)
    resumes = data_client.list_user_resumes(user_id)
    return jsonify([_serialize_resume_library_record(record) for record in resumes])


@app.route('/api/my-resumes/<int:resume_id>/file', methods=['GET'])
def get_resume_file(resume_id):
    """获取简历原始文件"""
    if not data_client:
        return jsonify({"error": "存储服务不可用"}), 503
    try:
        record = data_client.get_resume_file_record(resume_id)
        if not record:
            return jsonify({"error": "文件不存在"}), 404

        file_path = record.get("file_path") or ""
        if not file_path or not os.path.exists(file_path):
            return jsonify({"error": "文件不存在"}), 404

        return send_file(
            file_path,
            mimetype="application/octet-stream",
            as_attachment=False,
            download_name=record.get("file_name") or os.path.basename(file_path),
        )
    except Exception as e:
        print(f"[API] get_resume_file failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/my-resumes/<int:resume_id>', methods=['DELETE'])
def delete_my_resume(resume_id):
    """删除当前用户的简历，并清理服务器文件与预览图。"""
    if not data_client:
        return jsonify({"status": "error", "message": "存储服务不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    deleted = data_client.delete_resume(resume_id, user_id)
    if not deleted:
        return jsonify({"status": "error", "message": "简历不存在或无权删除"}), 404
    return jsonify({"status": "success"})


@app.route('/api/my-resumes/<int:resume_id>/preview/<int:page>', methods=['GET'])
def get_resume_preview(resume_id, page):
    """返回简历的图片化预览页。"""
    if not data_client:
        return jsonify({"error": "存储服务不可用"}), 503

    try:
        record = data_client.get_resume_file_record(resume_id)
        if not record:
            return jsonify({"error": "简历不存在"}), 404

        preview_summary = get_resume_preview_summary(record.get("file_path") or "", record.get("file_name") or "")
        preview_paths = preview_summary["preview_paths"]
        if page < 1 or page > len(preview_paths):
            return jsonify({"error": "预览页不存在"}), 404

        preview_path = preview_paths[page - 1]
        if not preview_path or not os.path.exists(preview_path):
            return jsonify({"error": "预览文件不存在"}), 404

        return send_file(preview_path, mimetype="image/png", as_attachment=False)
    except Exception as e:
        print(f"[API] get_resume_preview failed: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/career/dashboard', methods=['GET'])
def get_career_dashboard():
    if not data_client or not career_planning_service:
        return jsonify({"status": "error", "message": "职业规划服务暂不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    try:
        dashboard = career_planning_service.build_dashboard(user_id)
        return jsonify({"status": "success", "data": dashboard})
    except Exception as e:
        print(f"[API] get_career_dashboard failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/career/docs', methods=['GET'])
def get_career_docs():
    if not data_client:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    try:
        return jsonify({"status": "success", "data": career_planning_docs.get_catalog()})
    except Exception as e:
        print(f"[API] get_career_docs failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/career/docs/<doc_id>', methods=['GET'])
def get_career_doc(doc_id):
    if not data_client:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    try:
        document = career_planning_docs.get_document(doc_id)
        if not document:
            return jsonify({"status": "error", "message": "文档不存在"}), 404
        return jsonify({"status": "success", "data": document})
    except Exception as e:
        print(f"[API] get_career_doc failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/career/plans', methods=['GET'])
def list_career_plans():
    if not data_client or not career_planning_service:
        return jsonify({"status": "error", "message": "职业规划服务暂不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    try:
        dashboard = career_planning_service.build_dashboard(user_id)
        return jsonify({"status": "success", "data": {"plans": dashboard.get("plans", [])}})
    except Exception as e:
        print(f"[API] list_career_plans failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/career/plans/generate', methods=['POST'])
def generate_career_plan():
    if not data_client or not career_planning_service:
        return jsonify({"status": "error", "message": "职业规划服务暂不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    payload = request.get_json(silent=True) or {}
    try:
        target_role, career_goal, horizon_months, refresh = _parse_career_plan_generate_payload(payload)
        dashboard = career_planning_service.generate_plan(
            user_id=user_id,
            target_role=target_role,
            career_goal=career_goal,
            horizon_months=horizon_months,
            refresh=refresh,
        )
        return jsonify({"status": "success", "data": dashboard})
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        print(f"[API] generate_career_plan failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/career/plans/<int:plan_id>', methods=['GET'])
def get_career_plan(plan_id):
    if not data_client or not career_planning_service:
        return jsonify({"status": "error", "message": "职业规划服务暂不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    try:
        detail = career_planning_service._fetch_plan_detail(plan_id, user_id)
        if not detail:
            return jsonify({"status": "error", "message": "规划不存在或无权限访问"}), 404
        return jsonify({"status": "success", "data": detail})
    except Exception as e:
        print(f"[API] get_career_plan failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/career/tasks/<int:task_id>', methods=['PATCH'])
def update_career_task(task_id):
    if not data_client or not career_planning_service:
        return jsonify({"status": "error", "message": "职业规划服务暂不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    payload = request.get_json(silent=True) or {}
    try:
        detail = career_planning_service.update_task(
            user_id=user_id,
            task_id=task_id,
            status=str(payload.get("status") or "").strip(),
            progress=payload.get("progress"),
            note=str(payload.get("note") or "").strip(),
        )
        if not detail:
            return jsonify({"status": "error", "message": "任务不存在或无权限访问"}), 404
        return jsonify({"status": "success", "data": career_planning_service.build_dashboard(user_id)})
    except Exception as e:
        print(f"[API] update_career_task failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/career/tasks/<int:task_id>/logs', methods=['POST'])
def append_career_task_log(task_id):
    if not data_client or not career_planning_service:
        return jsonify({"status": "error", "message": "职业规划服务暂不可用"}), 503

    user_id = _get_current_user_id_from_auth_header()
    if user_id is None:
        return jsonify({"status": "error", "message": "请先登录"}), 401

    payload = request.get_json(silent=True) or {}
    try:
        detail = career_planning_service.update_task(
            user_id=user_id,
            task_id=task_id,
            status=str(payload.get("status") or "").strip(),
            progress=payload.get("progress"),
            note=str(payload.get("note") or "").strip(),
        )
        if not detail:
            return jsonify({"status": "error", "message": "任务不存在或无权限访问"}), 404
        return jsonify({"status": "success", "data": career_planning_service.build_dashboard(user_id)})
    except Exception as e:
        print(f"[API] append_career_task_log failed: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/setup', methods=['POST'])
def setup_interview():
    """初始化面试配置与简历上传"""
    job_title = normalize_job_title(request.form.get('job_title', '高级前端开发工程师'))
    style = request.form.get('style', 'strict')
    interview_type = request.form.get('interview_type', 'technical')
    difficulty = request.form.get('difficulty', 'mid')
    feature_vad = request.form.get('feature_vad', 'true') == 'true'
    feature_deep = request.form.get('feature_deep', 'true') == 'true'
    model_provider = request.form.get('model_provider', '')
    resume_ocr_text = request.form.get('resume_ocr_text', '')

    session_id = str(uuid.uuid4())
    token = create_token(session_id)

    # 尝试从 JWT 提取当前登录用户 ID
    current_user_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and STORAGE_AVAILABLE and data_client:
        user_info = data_client.get_user(auth_header[7:])
        if user_info and "id" in user_info:
            current_user_id = user_info["id"]

    if STORAGE_AVAILABLE:
        data_client.create_session(
            session_id=session_id,
            candidate_name="求职者",
            position=job_title,
            interview_style=style,
            metadata={"type": interview_type, "diff": difficulty, "vad": feature_vad, "deep": feature_deep},
            user_id=current_user_id,
        )

    agent = get_agent(session_id, model_provider=model_provider)

    has_resume = False
    file_path = ""
    filename = ""

    if 'resume' in request.files:
        file = request.files['resume']
        if file.filename != '':
            has_resume = True
            raw_name = file.filename
            ext = os.path.splitext(raw_name)[-1].lower()
            if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.webp', '.heic', '.heif'):
                ext = '.pdf'
            filename = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

    try:
        resume_summary = ""
        ocr_raw_text = ""
        ocr_status = "not_called"  # not_called | success | error | unavailable
        prompt_source = "static"

        if agent:
            parse_result_text = ""
            all_steps = []

            # ── 阶段 1：获取 OCR 文本（串行，后续步骤依赖它） ──
            if has_resume:
                if OCR_AVAILABLE:
                    try:
                        print(f"[OCR] Parsing resume via OCR: {file_path}")
                        ocr_result = perform_ocr(image_path=file_path, use_preprocessing=True)
                        ocr_raw_text = ocr_result
                        ocr_status = "success" if "解析成功" in ocr_result else "error"
                        all_steps.append({
                            "tool": "perform_ocr",
                            "tool_input": file_path,
                            "log": "直接调用 OCR（非 Agent 自主决策）",
                            "observation": ocr_result[:2000]
                        })
                    except Exception as ocr_err:
                        ocr_status = "error"
                        ocr_raw_text = f"OCR 调用异常: {str(ocr_err)}"
                        print(f"[FAIL] OCR call failed: {ocr_err}")
                else:
                    ocr_status = "unavailable"
                    ocr_raw_text = "OCR 模块未加载，无法解析简历"

                if STORAGE_AVAILABLE:
                    stored_path = file_path
                    upload_result = data_client.upload_resume_file(session_id, file_path)
                    if upload_result and upload_result.get("file_path"):
                        stored_path = upload_result["file_path"]
                        print(f"[OK] Resume file saved: {stored_path}")
                    else:
                        print("[WARN] Resume file save failed, metadata only")
                    data_client.save_resume(
                        session_id,
                        filename,
                        stored_path,
                        normalize_reusable_ocr_result(ocr_raw_text if ocr_status == "success" else ""),
                        user_id=current_user_id,
                    )

            elif resume_ocr_text:
                has_resume = True
                ocr_raw_text = resume_ocr_text
                ocr_status = "success"
                print(f"[OCR] Reusing historical resume OCR text ({len(resume_ocr_text)} chars)")
                all_steps.append({
                    "tool": "resume_reuse",
                    "tool_input": "历史 OCR 文本",
                    "log": "复用上次面试的简历 OCR 结果",
                    "observation": resume_ocr_text[:500]
                })

            else:
                # 未上传简历：自动加载该用户最近一次有 OCR 结果的简历
                if STORAGE_AVAILABLE and data_client and current_user_id:
                    try:
                        latest_resume = data_client.get_latest_resume(user_id=current_user_id)
                        if latest_resume and is_reusable_ocr_result(latest_resume.get("ocr_result")):
                            hist_ocr = latest_resume["ocr_result"]
                            has_resume = True
                            ocr_raw_text = hist_ocr
                            ocr_status = "success"
                            print(f"[OCR] Auto-loaded user historical resume ({len(hist_ocr)} chars)")
                            all_steps.append({
                                "tool": "resume_auto_load",
                                "tool_input": f"user_id={current_user_id}",
                                "log": "自动加载用户最近一次简历 OCR",
                                "observation": hist_ocr[:500]
                            })
                    except Exception as e:
                        print(f"[WARN] Auto-load historical resume failed: {e}")

            # ── 阶段 2：LLM 简历摘要 + RAG 检索 并行执行 ──
            rag_context = ""
            rag_debug_details = _build_rag_debug_details(
                query="",
                job_title=job_title,
                difficulty=difficulty,
                interview_type=interview_type,
                style=style,
                stage="opening",
                status="not_started",
            )

            def _task_summary():
                """LLM 生成简历摘要"""
                if ocr_status != "success" or not ocr_raw_text:
                    return "", []
                q = f"请用简洁的中文总结以下简历的核心信息（姓名、技能、项目经历、教育背景），不要遗漏关键细节：\n\n{ocr_raw_text[:6000]}"
                resp, steps = agent.run(q)
                return resp, steps

            def _task_rag():
                """RAG 检索（用 OCR 原文片段代替 LLM 摘要做查询enrichment）"""
                if not (STORAGE_AVAILABLE and data_client):
                    return ""
                try:
                    rag_parts = []
                    jobs = []
                    questions = []
                    scripts = []
                    # 直接用 OCR 原文前 300 字做查询enrichment，不等 LLM 摘要
                    resume_keywords = ocr_raw_text[:300] if ocr_raw_text else ""
                    enriched_query = f"{job_title} {resume_keywords}".strip()

                    jobs = data_client.search_job_descriptions(
                        job_title,
                        top_k=1,
                        difficulty=difficulty,
                        interview_type=interview_type,
                    )
                    if jobs:
                        j = jobs[0]
                        meta = j.get("metadata", {})
                        must_have = ", ".join(meta.get("must_have_skills") or [])
                        tech_tags = ", ".join(meta.get("tech_tags") or []) or meta.get("tags", "")
                        rag_parts.append(
                            f"### 岗位画像\n"
                            f"- 岗位：{meta.get('job_name', '') or meta.get('canonical_job_title', '')}\n"
                            f"- 关键技能：{must_have}\n"
                            f"- 技术标签：{tech_tags}\n"
                            f"- 要求：{j.get('document', '')[:500]}"
                        )

                    questions = data_client.search_questions(
                        enriched_query,
                        job_filter=job_title,
                        top_k=5,
                        difficulty=difficulty,
                        interview_type=interview_type,
                        style=style,
                        stage="core",
                    )
                    if questions:
                        q_lines = []
                        for idx, q in enumerate(questions, 1):
                            meta = q.get("metadata", {})
                            q_lines.append(f"{idx}. [{meta.get('dimension', '')}] {(q.get('document', '') or q.get('content', ''))[:200]}")
                            if meta.get("score_5"):
                                q_lines.append(f"   5分标准：{meta['score_5'][:150]}")
                            if meta.get("score_1"):
                                q_lines.append(f"   1分标准：{meta['score_1'][:100]}")
                        rag_parts.append("### 推荐面试题及评分标准\n" + "\n".join(q_lines))

                    scripts = data_client.search_hr_scripts(
                        f"{job_title} {style} 面试 开场 自我介绍",
                        stage="开场",
                        top_k=2,
                        interview_type=interview_type,
                        style=style,
                    )
                    if scripts:
                        s_lines = [
                            f"- [{s.get('metadata', {}).get('stage', '')}] {(s.get('document', '') or s.get('content', ''))[:200]}"
                            for s in scripts
                        ]
                        rag_parts.append("### 参考话术\n" + "\n".join(s_lines))

                    rag_debug_details = _build_rag_debug_details(
                        query=enriched_query,
                        job_title=job_title,
                        difficulty=difficulty,
                        interview_type=interview_type,
                        style=style,
                        stage="opening",
                        status="matched" if rag_parts else "empty",
                        jobs=jobs,
                        questions=questions,
                        scripts=scripts,
                    )

                    if rag_parts:
                        result = "\n\n".join(rag_parts)
                        print(f"[OK] RAG retrieval complete: {len(jobs)} jobs, {len(questions)} questions, {len(scripts)} scripts")
                        return result
                except Exception as e:
                    print(f"[WARN] RAG retrieval failed, fallback to no-knowledge-base mode: {e}")
                    rag_debug_details = _build_rag_debug_details(
                        query=enriched_query if 'enriched_query' in locals() else "",
                        job_title=job_title,
                        difficulty=difficulty,
                        interview_type=interview_type,
                        style=style,
                        stage="opening",
                        status="error",
                        error=str(e),
                        jobs=jobs if 'jobs' in locals() else [],
                        questions=questions if 'questions' in locals() else [],
                        scripts=scripts if 'scripts' in locals() else [],
                    )
                return ""

            # 并行执行 LLM 摘要 + RAG 检索
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_summary = executor.submit(_task_summary)
                future_rag = executor.submit(_task_rag)

                resume_summary, summary_steps = future_summary.result()
                all_steps.extend(summary_steps)
                rag_context = future_rag.result()

            print(f"[OK] Parallel stage complete: summary {len(resume_summary)} chars, RAG {len(rag_context)} chars")

            # 第三步：用简历摘要 + RAG 上下文重新注入 prompt（反幻觉锚点）
            if hasattr(agent, 'update_dynamic_prompt'):
                # 尝试使用 PromptGenerator 生成定制 prompt
                generated_prompt = ""
                try:
                    generated_prompt = _try_generate_prompt(
                        job_title, interview_type, difficulty, style, resume_summary
                    )
                    if generated_prompt:
                        prompt_source = "prompt_generator"
                except Exception as e:
                    print(f"[WARN] PromptGenerator degraded: {e}")

                agent.update_dynamic_prompt(
                    job_title=job_title,
                    interview_type=interview_type,
                    difficulty=difficulty,
                    style=style,
                    feature_vad=feature_vad,
                    feature_deep=feature_deep,
                    resume_summary=resume_summary,
                    custom_prompt=generated_prompt,
                    rag_context=rag_context
                )
            else:
                agent.update_system_prompt(style=style)
            agent.reset_memory()

            # 第三步：让面试官开场
            if has_resume:
                setup_query = f"我应聘的岗位是【{job_title}】。你刚才已经解析了我的真实简历，现在面试正式开始。请以面试官的身份用一段话向我打招呼，简述对我简历的第一印象，然后**明确要求候选人做 2-3 分钟的自我介绍**。切记：绝对不要自己编造任何经历！"
                response, steps2 = agent.run(setup_query)
                
                # [CHECK] Verify: Check if AI's first sentence includes self-introduction request
                if _has_self_intro_request(response):
                    print(f"[OK] Verification passed: AI requires candidate self-introduction")
                else:
                    print(f"[FAIL] Verification failed: AI did not require self-introduction")
                    print(f"[AI] AI response: {response[:200]}")
                
                parse_result_text = "[OK] Resume parsed successfully, interviewer has locked real project details. Please introduce yourself first."
                all_steps = all_steps + steps2
            else:
                parse_result_text = "No resume provided"
                setup_query = f"我应聘的岗位是【{job_title}】。我没有提供简历。请以面试官的身份向我打招呼，并要求候选人先做自我介绍。"
                response, steps_setup = agent.run(setup_query)
                
                # [CHECK] Verify: Check if AI's first sentence includes self-introduction request
                if _has_self_intro_request(response):
                    print(f"[OK] Verification passed: AI requires candidate self-introduction")
                else:
                    print(f"[FAIL] Verification failed: AI did not require self-introduction")
                    print(f"[AI] AI response: {response[:200]}")
                
                all_steps = all_steps + steps_setup

            if STORAGE_AVAILABLE:
                data_client.save_message(session_id, "assistant", response)

            debug_info = _build_debug_info(agent, session_id)
            debug_info["intermediate_steps"] = all_steps
            debug_info["prompt_source"] = prompt_source
            debug_info["resume_summary"] = resume_summary[:2000] if resume_summary else ""
            debug_info["ocr_raw_text"] = ocr_raw_text
            debug_info["ocr_status"] = ocr_status
            debug_info["rag_context"] = rag_context[:1000] if rag_context else ""
            debug_info["rag_details"] = rag_debug_details

            return jsonify({
                "status": "success",
                "token": token,
                "system_message": f"[OK] Interview room created (ID: {session_id[:8]})",
                "parse_result": parse_result_text,
                "ai_response": response,
                "ocr_text": ocr_raw_text if ocr_status == "success" else "",
                "debug_info": debug_info
            })
        else:
            import time
            time.sleep(1)
            ai_resp = f"你好，我是今天的AI面试官。我已经了解了你应聘【{job_title}】的意向。"
            parse_result_mock = ""
            if has_resume:
                ai_resp += f"我也初步看了你的简历（{filename}），发现你在项目经历上有几个点很值得探讨。准备好的话，请先做一个结合项目的简单自我介绍吧。"
                parse_result_mock = "发现简历中存在跨度较大的项目经历，将作为重点深挖对象。"
            else:
                ai_resp += "准备好的话，请先做一个简单的自我介绍吧。"
            if STORAGE_AVAILABLE:
                data_client.save_message(session_id, "assistant", ai_resp)
            return jsonify({
                "status": "success",
                "token": token,
                "system_message": "[Mock 模式] 未检测到 Agent，使用模拟逻辑",
                "parse_result": parse_result_mock,
                "ai_response": ai_resp
            })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/setup-stream', methods=['POST'])
def setup_interview_stream():
    """流式面试初始化：通过 SSE 实时输出 LLM 思考过程。"""
    job_title = normalize_job_title(request.form.get('job_title', '高级前端开发工程师'))
    style = request.form.get('style', 'strict')
    interview_type = request.form.get('interview_type', 'technical')
    difficulty = request.form.get('difficulty', 'mid')
    feature_vad = request.form.get('feature_vad', 'true') == 'true'
    feature_deep = request.form.get('feature_deep', 'true') == 'true'
    model_provider = request.form.get('model_provider', '')
    resume_ocr_text = request.form.get('resume_ocr_text', '')

    session_id = str(uuid.uuid4())
    token = create_token(session_id)

    current_user_id = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer ") and STORAGE_AVAILABLE and data_client:
        user_info = data_client.get_user(auth_header[7:])
        if user_info and "id" in user_info:
            current_user_id = user_info["id"]

    if STORAGE_AVAILABLE:
        data_client.create_session(
            session_id=session_id, candidate_name="求职者",
            position=job_title, interview_style=style,
            metadata={"type": interview_type, "diff": difficulty, "vad": feature_vad, "deep": feature_deep},
            user_id=current_user_id,
        )

    agent = get_agent(session_id, model_provider=model_provider)

    # 文件处理必须在 generator 外完成（generator 内 request context 不可用）
    has_resume = False
    file_path = ""
    filename = ""

    if 'resume' in request.files:
        file = request.files['resume']
        if file.filename != '':
            has_resume = True
            raw_name = file.filename
            ext = os.path.splitext(raw_name)[-1].lower()
            if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.webp', '.heic', '.heif'):
                ext = '.pdf'
            filename = f"{uuid.uuid4().hex}{ext}"
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

    def generate():
        nonlocal has_resume, file_path, filename
        try:
            resume_summary = ""
            ocr_raw_text = ""
            ocr_status = "not_called"
            prompt_source = "static"
            all_steps = []

            if not agent:
                # Mock 模式
                import time
                time.sleep(1)
                ai_resp = f"你好，我是今天的AI面试官。我已经了解了你应聘【{job_title}】的意向。准备好的话，请先做一个简单的自我介绍吧。"
                yield _sse_event("done", {
                    "status": "success", "token": token,
                    "system_message": "[Mock 模式]", "parse_result": "",
                    "ai_response": ai_resp, "ocr_text": "",
                    "debug_info": {}
                })
                return

            # 阶段 1：OCR
            if has_resume and file_path:
                yield _sse_event("stage", {"stage": "正在解析简历..."})
                if OCR_AVAILABLE:
                    try:
                        ocr_result = perform_ocr(image_path=file_path, use_preprocessing=True)
                        ocr_raw_text = ocr_result
                        ocr_status = "success" if "解析成功" in ocr_result else "error"
                    except Exception as ocr_err:
                        ocr_status = "error"
                        ocr_raw_text = f"OCR 调用异常: {str(ocr_err)}"
                else:
                    ocr_status = "unavailable"
                    ocr_raw_text = "OCR 模块未加载"

                if STORAGE_AVAILABLE:
                    stored_path = file_path
                    upload_result = data_client.upload_resume_file(session_id, file_path)
                    if upload_result and upload_result.get("file_path"):
                        stored_path = upload_result["file_path"]
                    data_client.save_resume(
                        session_id,
                        filename,
                        stored_path,
                        normalize_reusable_ocr_result(ocr_raw_text if ocr_status == "success" else ""),
                        user_id=current_user_id,
                    )

            elif resume_ocr_text:
                has_resume = True
                ocr_raw_text = resume_ocr_text
                ocr_status = "success"
            else:
                if STORAGE_AVAILABLE and data_client and current_user_id:
                    try:
                        latest_resume = data_client.get_latest_resume(user_id=current_user_id)
                        if latest_resume and is_reusable_ocr_result(latest_resume.get("ocr_result")):
                            has_resume = True
                            ocr_raw_text = latest_resume["ocr_result"]
                            ocr_status = "success"
                    except Exception:
                        pass

            # 阶段 2：LLM 摘要（流式输出思考过程）
            rag_context = ""
            rag_debug_details = _build_rag_debug_details(
                query="",
                job_title=job_title,
                difficulty=difficulty,
                interview_type=interview_type,
                style=style,
                stage="opening",
                status="not_started",
            )
            if ocr_status == "success" and ocr_raw_text and agent:
                yield _sse_event("stage", {"stage": "AI 正在分析简历..."})
                q = f"请用简洁的中文总结以下简历的核心信息（姓名、技能、项目经历、教育背景），不要遗漏关键细节：\n\n{ocr_raw_text[:6000]}"
                # 流式获取摘要
                if hasattr(agent, 'llm_client') and agent.llm_client:
                    messages = [{"role": "user", "content": q}]
                    for chunk in agent.llm_client.generate_stream(messages):
                        resume_summary += chunk
                        yield _sse_event("thinking", {"chunk": chunk})
                else:
                    resume_summary, steps = agent.run(q)
                    all_steps.extend(steps)

                # RAG 检索（并行，不阻塞流式输出）
                yield _sse_event("stage", {"stage": "正在检索知识库..."})
                if STORAGE_AVAILABLE and data_client:
                    try:
                        rag_parts = []
                        jobs = []
                        questions = []
                        scripts = []
                        resume_keywords = ocr_raw_text[:300]
                        enriched_query = f"{job_title} {resume_keywords}".strip()
                        jobs = data_client.search_job_descriptions(
                            job_title,
                            top_k=1,
                            difficulty=difficulty,
                            interview_type=interview_type,
                        )
                        if jobs:
                            j = jobs[0]
                            meta = j.get("metadata", {})
                            must_have = ", ".join(meta.get("must_have_skills") or [])
                            tech_tags = ", ".join(meta.get("tech_tags") or []) or meta.get("tags", "")
                            rag_parts.append(
                                f"### 岗位画像\n"
                                f"- 岗位：{meta.get('job_name', '') or meta.get('canonical_job_title', '')}\n"
                                f"- 关键技能：{must_have}\n"
                                f"- 技术标签：{tech_tags}\n"
                                f"- 要求：{j.get('document', '')[:500]}"
                            )
                        questions = data_client.search_questions(
                            enriched_query,
                            job_filter=job_title,
                            top_k=5,
                            difficulty=difficulty,
                            interview_type=interview_type,
                            style=style,
                            stage="core",
                        )
                        if questions:
                            q_lines = []
                            for idx, q in enumerate(questions, 1):
                                meta = q.get("metadata", {})
                                q_lines.append(f"{idx}. [{meta.get('dimension', '')}] {(q.get('document', '') or q.get('content', ''))[:200]}")
                            rag_parts.append("### 推荐面试题\n" + "\n".join(q_lines))
                        scripts = data_client.search_hr_scripts(
                            f"{job_title} {style} 面试 开场 自我介绍",
                            stage="开场",
                            top_k=2,
                            interview_type=interview_type,
                            style=style,
                        )
                        if scripts:
                            s_lines = [
                                f"- [{s.get('metadata', {}).get('stage', '')}] {(s.get('document', '') or s.get('content', ''))[:200]}"
                                for s in scripts
                            ]
                            rag_parts.append("### 参考话术\n" + "\n".join(s_lines))
                        rag_debug_details = _build_rag_debug_details(
                            query=enriched_query,
                            job_title=job_title,
                            difficulty=difficulty,
                            interview_type=interview_type,
                            style=style,
                            stage="opening",
                            status="matched" if rag_parts else "empty",
                            jobs=jobs,
                            questions=questions,
                            scripts=scripts,
                        )
                        if rag_parts:
                            rag_context = "\n\n".join(rag_parts)
                    except Exception as e:
                        print(f"[WARN] RAG retrieval failed (stream), fallback to no-knowledge-base mode: {e}")
                        rag_debug_details = _build_rag_debug_details(
                            query=enriched_query if 'enriched_query' in locals() else "",
                            job_title=job_title,
                            difficulty=difficulty,
                            interview_type=interview_type,
                            style=style,
                            stage="opening",
                            status="error",
                            error=str(e),
                            jobs=jobs if 'jobs' in locals() else [],
                            questions=questions if 'questions' in locals() else [],
                            scripts=scripts if 'scripts' in locals() else [],
                        )

            # 阶段 3：注入 prompt + 开场白
            if agent:
                if hasattr(agent, 'update_dynamic_prompt'):
                    generated_prompt = ""
                    try:
                        generated_prompt = _try_generate_prompt(job_title, interview_type, difficulty, style, resume_summary)
                        if generated_prompt:
                            prompt_source = "prompt_generator"
                    except Exception:
                        pass
                    agent.update_dynamic_prompt(
                        job_title=job_title, interview_type=interview_type,
                        difficulty=difficulty, style=style,
                        feature_vad=feature_vad, feature_deep=feature_deep,
                        resume_summary=resume_summary, custom_prompt=generated_prompt,
                        rag_context=rag_context
                    )
                else:
                    agent.update_system_prompt(style=style)
                agent.reset_memory()

                yield _sse_event("stage", {"stage": "AI 面试官正在准备开场白..."})
                if has_resume:
                    setup_query = f"我应聘的岗位是【{job_title}】。你刚才已经解析了我的真实简历，现在面试正式开始。请以面试官的身份用一段话向我打招呼，简述对我简历的第一印象，然后**明确要求候选人做 2-3 分钟的自我介绍**。切记：绝对不要自己编造任何经历！"
                    parse_result_text = "[OK] Resume parsed successfully, interviewer has locked real project details. Please introduce yourself first."
                else:
                    setup_query = f"我应聘的岗位是【{job_title}】。我没有提供简历。请以面试官的身份向我打招呼，并要求候选人先做自我介绍。"
                    parse_result_text = "No resume provided"

                # Stream getting opening statement
                response = ""
                if hasattr(agent, 'llm_client') and agent.llm_client:
                    # Need to use agent's run to maintain memory, but we can get full response first
                    response, steps = agent.run(setup_query)
                    all_steps.extend(steps)
                    
                    # [CHECK] Verify: Check if AI's first sentence includes self-introduction request
                    if _has_self_intro_request(response):
                        print(f"[OK] Verification passed (stream): AI requires candidate self-introduction")
                    else:
                        print(f"[FAIL] Verification failed (stream): AI did not require self-introduction")
                        print(f"[AI] AI response: {response[:200]}")
                else:
                    response, steps = agent.run(setup_query)
                    all_steps.extend(steps)
                    
                    # [CHECK] Verify: Check if AI's first sentence includes self-introduction request
                    if _has_self_intro_request(response):
                        print(f"[OK] Verification passed (stream): AI requires candidate self-introduction")
                    else:
                        print(f"[FAIL] Verification failed (stream): AI did not require self-introduction")
                        print(f"[AI] AI response: {response[:200]}")

                if STORAGE_AVAILABLE:
                    data_client.save_message(session_id, "assistant", response)

                debug_info = _build_debug_info(agent, session_id)
                debug_info["intermediate_steps"] = all_steps
                debug_info["prompt_source"] = prompt_source
                debug_info["resume_summary"] = resume_summary[:2000]
                debug_info["ocr_raw_text"] = ocr_raw_text
                debug_info["ocr_status"] = ocr_status
                debug_info["rag_context"] = rag_context[:1000]
                debug_info["rag_details"] = rag_debug_details

                yield _sse_event("done", {
                    "status": "success", "token": token,
                    "system_message": f"[OK] Interview room created (ID: {session_id[:8]})",
                    "parse_result": parse_result_text,
                    "ai_response": response,
                    "ocr_text": ocr_raw_text if ocr_status == "success" else "",
                    "debug_info": debug_info
                })
        except Exception as e:
            traceback.print_exc()
            yield _sse_event("error", {"message": str(e)})

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/end-stream', methods=['POST'])
@require_session
def end_interview_stream(session_id):
    """流式结束面试：通过 SSE 实时输出评估思考过程。"""
    agent = _agents.get(session_id)
    observer = None

    # 创建 SSE 消息队列
    sse_queue = queue.Queue()

    # 设置观察者的 SSE 推送回调
    if observer:
        def push_callback(event):
            """SSE 推送回调：将评估更新推送到前端"""
            try:
                sse_queue.put(event)
            except Exception as e:
                print(f"[app] SSE 推送回调异常：{e}")
        observer.set_push_callback(push_callback)
    observer = _observers.pop(session_id, None)

    # 设置观察者的 SSE 推送回调
    if observer:
        def push_callback(event):
            """SSE 推送回调：将评估更新推送到前端"""
            try:
                # 直接 yield 事件（在 generate 函数内部）
                pass
            except Exception as e:
                print(f"[app] SSE 推送回调异常：{e}")
        observer.set_push_callback(push_callback)

    # 取出观察者草稿，清理 observer
    observer = observer
    draft = observer.shutdown(wait=True, timeout=EVAL_OBSERVER_DRAIN_TIMEOUT_SECONDS) if observer else {}
    
    if False and observer:
        # [NEW] Set SSE push callback
        def push_callback(event):
            yield _sse_event("eval_draft", event)
        
        observer.set_push_callback(push_callback)
        draft = observer.get_draft()
        observer.shutdown(wait=False)

    def generate():
        eval_result = {}
        if agent:
            try:
                yield _sse_event("stage", {"stage": "AI 面试官正在撰写评估报告..."})
                # 流式评估
                if hasattr(agent, 'llm_client') and agent.llm_client:
                    eval_prompt = _build_eval_prompt(agent, draft=draft)
                    if eval_prompt:
                        messages = [{"role": "user", "content": eval_prompt}]
                        raw = ""
                        for chunk in agent.llm_client.generate_stream(messages):
                            raw += chunk
                            yield _sse_event("thinking", {"chunk": chunk})
                        eval_result = _parse_eval_result(raw)
                    else:
                        eval_result = agent.evaluate_interview(draft=draft)
                else:
                    eval_result = agent.evaluate_interview()
            except Exception as e:
                print(f"[end-stream] AI 评估失败: {e}")

        if STORAGE_AVAILABLE:
            data_client.end_session(session_id)
            ai_evals = eval_result.get("evaluations", [])
            if ai_evals:
                for ev in ai_evals:
                    data_client.save_evaluation(session_id, ev.get("dimension", "未知"), ev.get("score", 5), ev.get("comment", ""))
            else:
                existing_stats = data_client.get_session_statistics(session_id)
                if not existing_stats.get("evaluations"):
                    for dim, score, comment in [("技术深度", 7, "待评估"), ("沟通表达", 7, "待评估"), ("逻辑思维", 7, "待评估"), ("项目经验", 7, "待评估")]:
                        data_client.save_evaluation(session_id, dim, score, comment)
            stats = data_client.get_session_statistics(session_id)
            # 持久化评估总结文本
            data_client.save_eval_summary(
                session_id,
                strengths=eval_result.get("strengths", ""),
                weaknesses=eval_result.get("weaknesses", ""),
                summary=eval_result.get("summary", ""),
            )
        else:
            stats = None

        _agents.pop(session_id, None)
        revoke_session(session_id)

        yield _sse_event("done", {
            "status": "success",
            "stats": stats,
            "strengths": eval_result.get("strengths", ""),
            "weaknesses": eval_result.get("weaknesses", ""),
            "summary": eval_result.get("summary", ""),
        })

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def _build_eval_prompt(agent, draft: dict = None) -> str:
    """构建评估 prompt，可注入观察者草稿作为参考"""
    try:
        history = agent.get_chat_history() if hasattr(agent, 'get_chat_history') else []
        if not history:
            return ""
        conversation = "\n".join([f"{'面试官' if m['role'] == 'assistant' else '候选人'}: {m['content']}" for m in history])

        # 构建草稿参考段落
        draft_context = ""
        if draft and (draft.get("strengths") or draft.get("weaknesses")):
            s_lines = "\n".join(
                f"  - 第{x['turn']}轮：{x['text']}" for x in draft.get("strengths", [])
            )
            w_lines = "\n".join(
                f"  - 第{x['turn']}轮：{x['text']}" for x in draft.get("weaknesses", [])
            )
            notes = "\n".join(
                f"  - 第{x['turn']}轮：{x['note']}" for x in draft.get("turn_notes", [])
            )
            draft_context = (
                f"\n\n【过程观察记录（供参考，请结合对话综合判断）】\n"
                f"优势观察：\n{s_lines}\n"
                f"不足观察：\n{w_lines}\n"
                f"关键节点：\n{notes}"
            )

        return f"""你是一位资深面试评估专家。请基于以下面试对话，生成一份专业的面试评估报告。

面试对话记录：
{conversation}{draft_context}

请严格按以下 JSON 格式输出（不要输出任何其他内容）：
{{
  "evaluations": [
    {{"dimension": "技术深度", "score": 1-10, "comment": "评价"}},
    {{"dimension": "沟通表达", "score": 1-10, "comment": "评价"}},
    {{"dimension": "逻辑思维", "score": 1-10, "comment": "评价"}},
    {{"dimension": "项目经验", "score": 1-10, "comment": "评价"}},
    {{"dimension": "学习能力", "score": 1-10, "comment": "评价"}}
  ],
  "strengths": "候选人的主要优势（2-3句话）",
  "weaknesses": "候选人的不足之处（2-3句话）",
  "summary": "总体评价（3-5句话）"
}}"""
    except Exception:
        return ""


def _parse_eval_result(raw: str) -> dict:
    """解析评估 LLM 输出为结构化结果"""
    import re
    try:
        json_match = re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            return json_mod.loads(json_match.group())
    except Exception:
        pass
    return {}


@app.route('/api/chat', methods=['POST'])
@require_session
def chat(session_id):
    """处理对话"""
    data = request.json
    user_message = data.get('message', '')
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    if STORAGE_AVAILABLE:
        data_client.save_message(session_id, "user", user_message)

    _chat_stop_flags[session_id] = False
    agent = _agents.get(session_id)
    debug_info = {}
    if agent:
        try:
            response, steps = agent.run(user_message)
            if STORAGE_AVAILABLE:
                data_client.save_message(session_id, "assistant", response)
            debug_info = _build_debug_info(agent, session_id)
            debug_info["intermediate_steps"] = steps
            # 后台异步触发观察者分析本轮
            observer = _observers.get(session_id)
            if observer:
                observer.observe_async(agent.get_chat_history())
        except Exception as e:
            response = f"抱歉，系统遇到了问题：{str(e)}"
    else:
        import time
        time.sleep(1.5)
        response = f"针对你刚才说的\u201c{user_message[:10]}...\u201d，你能详细谈谈底层的实现原理吗？"
        if STORAGE_AVAILABLE:
            data_client.save_message(session_id, "assistant", response)

    return jsonify({"response": response, "debug_info": debug_info})


@app.route('/api/chat-stop', methods=['POST'])
@require_session
def stop_chat_stream(session_id):
    """Best-effort stop signal for the current streaming reply."""
    _chat_stop_flags[session_id] = True
    return jsonify({"status": "success"})


@app.route('/api/chat-stream', methods=['POST'])
@require_session
def chat_stream(session_id):
    """流式对话：通过 SSE 实时输出 LLM 思维链"""
    data = request.json
    user_message = data.get('message', '')
    if not user_message:
        return jsonify({"error": "消息不能为空"}), 400

    if STORAGE_AVAILABLE:
        data_client.save_message(session_id, "user", user_message)

    agent = _agents.get(session_id)
    observer = _observers.get(session_id)

    # 创建 SSE 消息队列
    sse_queue = queue.Queue()

    # 设置观察者的 SSE 推送回调
    if observer:
        def push_callback(event):
            """SSE 推送回调：将评估更新推送到前端"""
            try:
                sse_queue.put(event)
            except Exception as e:
                print(f"[app] SSE 推送回调异常：{e}")
        observer.set_push_callback(push_callback)

    def generate():
        full_response = ""
        interrupted = False
        if agent and hasattr(agent, 'run_stream'):
            yield _sse_event("stage", {"stage": "面试官正在深度思考..."})
            try:
                in_thinking = False
                for chunk_type, chunk in agent.run_stream(user_message):
                    if _chat_stop_flags.get(session_id):
                        interrupted = True
                        break
                    if chunk_type == "thinking":
                        if not in_thinking:
                            in_thinking = True
                        yield _sse_event("thinking", {"chunk": chunk})
                    elif chunk_type == "content":
                        if in_thinking:
                            # 思维链结束，正式回复开始
                            in_thinking = False
                            yield _sse_event("stage", {"stage": "面试官正在组织回复..."})
                        full_response += chunk
                        yield _sse_event("content", {"chunk": chunk})
                    
                    # 检查是否有评估更新需要推送
                    try:
                        while True:
                            eval_event = sse_queue.get_nowait()
                            yield _sse_event(eval_event["type"], eval_event["data"])
                    except queue.Empty:
                        pass
            except Exception as e:
                full_response = f"抱歉，系统遇到了问题：{str(e)}"
        elif agent:
            # 不支持流式，降级为一次性调用
            yield _sse_event("stage", {"stage": "面试官正在思考..."})
            try:
                full_response, _ = agent.run(user_message)
            except Exception as e:
                full_response = f"抱歉，系统遇到了问题：{str(e)}"
        else:
            import time
            time.sleep(1.5)
            full_response = f"针对你刚才说的\u201c{user_message[:10]}...\u201d，你能详细谈谈底层的实现原理吗？"

        if STORAGE_AVAILABLE and full_response:
            data_client.save_message(session_id, "assistant", full_response)
        if interrupted and agent and full_response and hasattr(agent, '_add_to_history'):
            try:
                agent._add_to_history({"role": "user", "content": user_message})
                agent._add_to_history({"role": "assistant", "content": full_response})
            except Exception:
                pass

        # 后台异步触发观察者分析本轮
        if agent and full_response:
            observer = _observers.get(session_id)
            if observer:
                observer.observe_async(agent.get_chat_history())

        # 推送所有剩余的评估更新
        while True:
            try:
                eval_event = sse_queue.get_nowait()
                yield _sse_event(eval_event["type"], eval_event["data"])
            except queue.Empty:
                break

        debug_info = _build_debug_info(agent, session_id) if agent else {}
        yield _sse_event("done", {
            "response": full_response,
            "interrupted": interrupted,
            "debug_info": debug_info,
        })

        _chat_stop_flags.pop(session_id, None)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


@app.route('/api/end', methods=['POST'])
@require_session
def end_interview(session_id):
    """结束面试"""
    agent = _agents.get(session_id)
    eval_result = {}

    # 取出观察者草稿，清理 observer
    observer = _observers.pop(session_id, None)
    draft = (
        observer.shutdown(wait=True, timeout=EVAL_OBSERVER_DRAIN_TIMEOUT_SECONDS)
        if observer else {}
    )

    # 调用 AI 生成真实评估（注入草稿）
    if agent:
        try:
            eval_result = agent.evaluate_interview(draft=draft)
            print(f"[end] AI 评估完成: {list(eval_result.keys())}")
        except Exception as e:
            print(f"[end] AI 评估失败: {e}")

    if STORAGE_AVAILABLE:
        data_client.end_session(session_id)

        # 保存 AI 评估结果（如果有）
        ai_evals = eval_result.get("evaluations", [])
        if ai_evals:
            for ev in ai_evals:
                data_client.save_evaluation(
                    session_id,
                    ev.get("dimension", "未知"),
                    ev.get("score", 5),
                    ev.get("comment", "")
                )
        else:
            # fallback：占位评分
            existing_stats = data_client.get_session_statistics(session_id)
            if not existing_stats.get("evaluations"):
                placeholder_evals = [
                    ("技术深度", 7, "待 AI 评估模块接入后自动生成"),
                    ("沟通表达", 7, "待 AI 评估模块接入后自动生成"),
                    ("逻辑思维", 7, "待 AI 评估模块接入后自动生成"),
                    ("项目经验", 7, "待 AI 评估模块接入后自动生成"),
                ]
                for dim, score, comment in placeholder_evals:
                    data_client.save_evaluation(session_id, dim, score, comment)

        stats = data_client.get_session_statistics(session_id)
        # 持久化评估总结文本
        data_client.save_eval_summary(
            session_id,
            strengths=eval_result.get("strengths", ""),
            weaknesses=eval_result.get("weaknesses", ""),
            summary=eval_result.get("summary", ""),
        )
        revoke_session(session_id)
        _agents.pop(session_id, None)
        return jsonify({
            "status": "success",
            "stats": stats,
            "strengths": eval_result.get("strengths", ""),
            "weaknesses": eval_result.get("weaknesses", ""),
            "summary": eval_result.get("summary", ""),
        })

    _agents.pop(session_id, None)
    revoke_session(session_id)
    return jsonify({
        "status": "success",
        "message": "会话已结束",
        "strengths": eval_result.get("strengths", ""),
        "weaknesses": eval_result.get("weaknesses", ""),
        "summary": eval_result.get("summary", ""),
    })


def _sse_event(event: str, data: dict) -> str:
    """Format one SSE event payload."""
    return f"event: {event}\ndata: {json_mod.dumps(data, ensure_ascii=False)}\n\n"


def _parse_report_context(raw_value):
    if not raw_value:
        return None
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json_mod.loads(raw_value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _merge_job_title_with_report_context(job_title: str, report_context: dict | None) -> str:
    if not report_context:
        return job_title

    parts = []
    if job_title:
        parts.append(job_title)
    if report_context.get("position"):
        parts.append(report_context["position"])

    summary_bits = []
    if report_context.get("summary"):
        summary_bits.append(f"Interview summary: {report_context['summary']}")
    if report_context.get("strengths"):
        summary_bits.append(f"Strengths: {report_context['strengths']}")
    if report_context.get("weaknesses"):
        summary_bits.append(f"Weaknesses: {report_context['weaknesses']}")

    evaluations = report_context.get("evaluations") or []
    if evaluations:
        eval_text = "; ".join(
            f"{item.get('dimension', 'unknown')} {item.get('score', '')}/10 {item.get('comment', '')}".strip()
            for item in evaluations
        )
        if eval_text:
            summary_bits.append(f"Interview dimensions: {eval_text}")

    merged_job_title = " ".join(part for part in parts if part).strip()
    if not summary_bits:
        return merged_job_title
    if not merged_job_title:
        return "\n".join(summary_bits)
    return f"{merged_job_title}\n" + "\n".join(summary_bits)


@app.route('/api/resume/analyze-stream', methods=['POST'])
def analyze_resume_stream():
    """流式简历分析：通过 SSE 实时输出 LLM 思考过程。
    支持两种模式：
    1. FormData 上传文件 → OCR + 流式分析
    2. JSON body { ocr_text, job_title } → 跳过 OCR，流式分析
    """
    if not ANALYZER_AVAILABLE:
        return jsonify({"status": "error", "message": "简历分析模块不可用"}), 503

    # 解析请求参数
    if request.is_json:
        data = request.json or {}
        ocr_text = data.get('ocr_text', '')
        job_title = data.get('job_title', '')
        report_context = _parse_report_context(data.get('report_context'))
        if not ocr_text:
            return jsonify({"status": "error", "message": "ocr_text 不能为空"}), 400
        ocr_images = {}
    else:
        if not OCR_AVAILABLE:
            return jsonify({"status": "error", "message": "OCR 模块不可用"}), 503
        if 'resume' not in request.files:
            return jsonify({"status": "error", "message": "请上传简历文件"}), 400
        file = request.files['resume']
        if file.filename == '':
            return jsonify({"status": "error", "message": "文件名为空"}), 400
        job_title = request.form.get('job_title', '')
        report_context = _parse_report_context(request.form.get('report_context'))
        raw_name = file.filename
        ext = os.path.splitext(raw_name)[-1].lower()
        if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.webp', '.heic', '.heif'):
            ext = '.pdf'
        filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        # OCR 阶段（同步，非流式）
        try:
            ocr_full = perform_ocr_full(image_path=file_path, use_preprocessing=True)
            ocr_text = ocr_full["text"]
            ocr_images = ocr_full["images"]
            if "错误" in ocr_text and "解析成功" not in ocr_text:
                return jsonify({"status": "error", "message": f"OCR 解析失败: {ocr_text}"}), 500
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 500

    # 获取模型配置
    provider = get_default_provider()
    _is_json = request.is_json  # 在请求上下文内捕获，generator 内不能访问 request

    def generate():
        try:
            yield _sse_event("stage", {"stage": "OCR 完成，开始 AI 分析..."})
            # 把 OCR 原文摘要发给前端，让用户看到输入大模型的文字
            ocr_preview = ocr_text[:800] + ("..." if len(ocr_text) > 800 else "")
            yield _sse_event("thinking", {"chunk": f"[DOC] Resume original text (input to LLM):\n{ocr_preview}\n\n---\n\n"})

            analyzer = ResumeAnalyzer(
                api_key=provider.api_key,
                base_url=provider.base_url,
                model=provider.model,
            )
            analysis_job_title = _merge_job_title_with_report_context(job_title, report_context)
            final_result = None
            for event in analyzer.analyze_stream(ocr_text=ocr_text, job_title=analysis_job_title, report_context=report_context):
                if event["type"] == "stage":
                    yield _sse_event("stage", {"stage": event["stage"]})
                elif event["type"] == "thinking":
                    yield _sse_event("thinking", {"chunk": event["chunk"]})
                elif event["type"] == "done":
                    final_result = event["result"]

            # 创建 session token
            session_id = str(uuid.uuid4())
            token = create_token(session_id)
            _resume_sessions[token] = {
                "ocr_text": ocr_text,
                "sections": final_result.get("sections", []) if final_result else [],
                "suggestions": final_result.get("suggestions", []) if final_result else [],
            }

            yield _sse_event("done", {
                "status": "success",
                "token": token,
                "ocr_text": ocr_text[:3000],
                "sections": final_result.get("sections", []) if final_result else [],
                "suggestions": final_result.get("suggestions", []) if final_result else [],
                "builder_data": final_result.get("builder_data") if final_result else None,
                "images": ocr_images if not _is_json else {},
            })
        except Exception as e:
            traceback.print_exc()
            yield _sse_event("error", {"message": str(e)})

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# ==========================================
# 简历优化模块 API
# ==========================================

# 简历分析会话数据（token -> 分析结果）
_resume_sessions: dict[str, dict] = {}


@app.route('/api/resume/analyze', methods=['POST'])
def analyze_resume():
    """上传简历，执行 OCR + DeepSeek 分析，返回结构化建议。
    支持两种模式：
    1. FormData 上传文件 → OCR + 分析
    2. JSON body { ocr_text, job_title } → 跳过 OCR，直接分析（复用面试 OCR 结果）
    """
    if not ANALYZER_AVAILABLE:
        return jsonify({"status": "error", "message": "简历分析模块不可用"}), 503

    # 模式 2：JSON body 带 ocr_text，跳过文件上传和 OCR
    if request.is_json:
        data = request.json or {}
        ocr_text = data.get('ocr_text', '')
        job_title = data.get('job_title', '')
        report_context = _parse_report_context(data.get('report_context'))
        if not ocr_text:
            return jsonify({"status": "error", "message": "ocr_text 不能为空"}), 400

        try:
            analyzer = ResumeAnalyzer(
                api_key=DEEPSEEK_API_KEY,
                base_url=DEEPSEEK_BASE_URL
            )
            analysis_job_title = _merge_job_title_with_report_context(job_title, report_context)
            result = analyzer.analyze(ocr_text=ocr_text, job_title=analysis_job_title, report_context=report_context)

            session_id = str(uuid.uuid4())
            token = create_token(session_id)
            _resume_sessions[token] = {
                "ocr_text": ocr_text,
                "sections": result.get("sections", []),
                "suggestions": result.get("suggestions", [])
            }

            return jsonify({
                "status": "success",
                "token": token,
                "ocr_text": ocr_text[:3000],
                "sections": result.get("sections", []),
                "suggestions": result.get("suggestions", []),
                "builder_data": result.get("builder_data"),
                "images": {}
            })
        except Exception as e:
            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e)}), 500

    # 模式 1：FormData 上传文件 → OCR + 分析
    if not OCR_AVAILABLE:
        return jsonify({"status": "error", "message": "OCR 模块不可用"}), 503

    # 接收文件
    if 'resume' not in request.files:
        return jsonify({"status": "error", "message": "请上传简历文件"}), 400
    file = request.files['resume']
    if file.filename == '':
        return jsonify({"status": "error", "message": "文件名为空"}), 400

    job_title = request.form.get('job_title', '')
    report_context = _parse_report_context(request.form.get('report_context'))
    raw_name = file.filename
    ext = os.path.splitext(raw_name)[-1].lower()
    if ext not in ('.pdf', '.jpg', '.jpeg', '.png', '.bmp', '.webp', '.heic', '.heif'):
        ext = '.pdf'
    filename = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    try:
        # 1. OCR 解析（含图片提取）
        ocr_full = perform_ocr_full(image_path=file_path, use_preprocessing=True)
        ocr_result = ocr_full["text"]
        ocr_images = ocr_full["images"]  # filename -> data:image/...;base64,...

        if "错误" in ocr_result and "解析成功" not in ocr_result:
            return jsonify({"status": "error", "message": f"OCR 解析失败: {ocr_result}"}), 500

        # 2. DeepSeek 分析
        analyzer = ResumeAnalyzer(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL
        )
        analysis_job_title = _merge_job_title_with_report_context(job_title, report_context)
        result = analyzer.analyze(ocr_text=ocr_result, job_title=analysis_job_title, report_context=report_context)

        # 3. 创建 session 并返回 token
        session_id = str(uuid.uuid4())
        token = create_token(session_id)
        _resume_sessions[token] = {
            "ocr_text": ocr_result,
            "sections": result.get("sections", []),
            "suggestions": result.get("suggestions", [])
        }

        return jsonify({
            "status": "success",
            "token": token,
            "ocr_text": ocr_result[:3000],
            "sections": result.get("sections", []),
            "suggestions": result.get("suggestions", []),
            "builder_data": result.get("builder_data"),
            "images": ocr_images
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/resume/export', methods=['POST'])
@require_session
def export_resume_pdf(session_id):
    """接收最终 sections JSON，用 Playwright 渲染 A4 PDF"""
    print(f"[INFO] Received export request, session_id: {session_id}")
    data = request.json
    sections = data.get('sections', [])
    print(f"[DOC] sections count: {len(sections)}")

    if not sections:
        return jsonify({"status": "error", "message": "sections 不能为空"}), 400

    try:
        print("[...] Importing dependencies...")
        from services.markdown_service import sections_to_html
        from services.pdf_service import render_resume_pdf
        print("[OK] Dependencies imported")

        # sections → structured HTML (properly handling markdown content)
        print("[...] Converting sections to HTML...")
        html_body = sections_to_html(sections)
        print(f"[OK] HTML generated, length: {len(html_body)}")

        # HTML → Playwright → PDF
        print("[...] Rendering PDF...")
        pdf_path = render_resume_pdf(html_body)
        print(f"[OK] PDF generated: {pdf_path}")

        return send_file(pdf_path, mimetype='application/pdf',
                         as_attachment=True, download_name='optimized_resume.pdf')

    except ImportError as ie:
        print(f"[FAIL] Dependency import failed: {ie}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"PDF export dependency not installed: {ie}"}), 503
    except Exception as e:
        print(f"[FAIL] Export failed: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/resume/polish', methods=['POST'])
def polish_resume_builder():
    """
    简历生成器 AI 优化端点
    接收简历文档的模块数据，返回优化建议
    """
    if not ANALYZER_AVAILABLE:
        return jsonify({"status": "error", "message": "简历分析模块不可用"}), 503

    data = request.json
    modules = data.get('modules', [])
    target_jd = data.get('targetJd', '')
    mode = data.get('mode', 'general')

    if not modules:
        return jsonify({"status": "error", "message": "modules 不能为空"}), 400

    try:
        # 初始化分析器
        analyzer = ResumeAnalyzer(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
            model="deepseek-chat"
        )

        # 将模块转换为文本格式供 LLM 分析
        resume_text = _convert_modules_to_text(modules)

        # 构建优化 prompt
        job_context = f"目标岗位：{target_jd}\n\n" if mode == 'targeted' and target_jd else ""

        prompt = f"""{job_context}你是一位资深的简历优化专家。请审查以下简历内容，找出可以优化的地方并给出具体的改写建议。

## 优化原则

1. **量化成果**：添加具体数字、百分比、规模等量化指标
2. **强化动词**：将"负责"、"参与"等弱动词改为"主导"、"优化"、"实现"等强动词
3. **STAR 法则**：确保每条经历包含情境(Situation)、任务(Task)、行动(Action)、结果(Result)
4. **技术关键词**：补充相关技术栈、工具、方法论的关键词
5. **简洁明确**：去除冗余表述，突出核心亮点

## 输出格式

对每个发现的优化点，输出一个 JSON 对象：
- "id": 唯一标识，格式 "sug_001", "sug_002" 等
- "moduleId": 对应模块的 id
- "entryId": 如果是时间线条目，提供 entry 的 id；否则为 null
- "fieldPath": 字段路径，如 "detail"、"content" 等
- "originalText": 原始文本片段（不超过 200 字）
- "suggestedText": 优化后的文本
- "reason": 优化理由（简洁说明，不超过 50 字）
- "status": 固定为 "pending"

请严格输出 JSON 数组，不要输出任何其他内容。不要用 markdown 代码块包裹。
如果某个模块没有明显可优化的地方，就不要为它生成建议。
最多生成 10 条建议，优先选择影响最大的优化点。

简历内容：
{resume_text}"""

        messages = [
            {"role": "system", "content": "你是简历优化专家，只输出合法 JSON 数组。"},
            {"role": "user", "content": prompt}
        ]

        # 调用 LLM
        raw_response = analyzer.client.generate(messages)
        suggestions = analyzer._parse_json_array(raw_response, fallback_id_prefix="sug")

        return jsonify({
            "status": "success",
            "suggestions": suggestions
        })

    except Exception as e:
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }
        print(f"[FAIL] Resume optimization failed: {error_details}")
        traceback.print_exc()
        return jsonify({
            "status": "error",
            "message": str(e),
            "details": error_details
        }), 500


def _convert_modules_to_text(modules: list) -> str:
    """将前端模块数据转换为可读文本格式"""
    lines = []

    for mod in modules:
        if not mod.get('visible', True):
            continue

        lines.append(f"\n## {mod.get('title', '未命名模块')} (ID: {mod.get('id', 'unknown')})")

        # 求职意向
        if mod.get('type') == 'intention' and mod.get('intention'):
            intention = mod['intention']
            parts = [
                intention.get('targetJob'),
                intention.get('targetCity'),
                intention.get('salary'),
                intention.get('availableDate')
            ]
            lines.append(' | '.join(filter(None, parts)))

        # 时间线条目（教育、工作、项目等）
        elif mod.get('entries'):
            for entry in mod['entries']:
                time_range = f"{entry.get('timeStart', '')} - {'至今' if entry.get('isCurrent') else entry.get('timeEnd', '')}"
                lines.append(f"\n### {entry.get('orgName', '')} | {entry.get('role', '')} | {time_range}")
                lines.append(f"(Entry ID: {entry.get('id', 'unknown')})")
                if entry.get('detail'):
                    lines.append(entry['detail'])

        # 技能条
        elif mod.get('skillBars'):
            skills = [f"{sk.get('name', '')} ({sk.get('level', 0)}%)" for sk in mod['skillBars']]
            lines.append(' · '.join(skills))

        # 标签
        elif mod.get('tags'):
            lines.append('、'.join(mod['tags']))

        # 纯文本内容
        elif mod.get('content'):
            lines.append(mod['content'])

    return '\n'.join(lines)


@app.route('/api/export-pdf', methods=['POST'])
def export_markdown_pdf():
    """通用 Markdown → PDF 导出端点"""
    data = request.json
    md_text = data.get('markdown', '')
    if not md_text:
        return jsonify({"status": "error", "message": "markdown 不能为空"}), 400

    try:
        from services.markdown_service import convert_markdown_to_html
        from services.pdf_service import render_resume_pdf

        html_body = convert_markdown_to_html(md_text)
        pdf_path = render_resume_pdf(html_body)
        filename = os.path.basename(pdf_path)

        return jsonify({"status": "success", "pdf_url": f"/download/{filename}"})

    except ImportError as ie:
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"依赖未安装: {ie}"}), 503
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/export-html-pdf', methods=['POST'])
def export_html_pdf():
    """HTML → PDF 导出端点（用于简历生成器）"""
    data = request.json
    html_content = data.get('html', '')
    if not html_content:
        return jsonify({"status": "error", "message": "html 不能为空"}), 400

    try:
        from services.pdf_service import render_html_to_pdf

        # 直接渲染 HTML 为 PDF
        pdf_path = render_html_to_pdf(html_content)

        return send_file(pdf_path, mimetype='application/pdf',
                         as_attachment=True, download_name='resume.pdf')

    except ImportError as ie:
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"依赖未安装: {ie}"}), 503
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/download/<filename>', methods=['GET'])
def download_pdf(filename):
    """下载已生成的 PDF 文件"""
    generated_dir = os.path.join(os.path.dirname(__file__), 'temp', 'generated')
    file_path = os.path.join(generated_dir, filename)
    if not os.path.exists(file_path):
        return jsonify({"status": "error", "message": "文件不存在"}), 404
    return send_file(file_path, mimetype='application/pdf', as_attachment=True)


# ==========================================
# 语音交互模块 API
# ==========================================

@app.route('/api/speech/stt', methods=['POST'])
@require_session
def speech_to_text(session_id):
    """语音识别：接收前端录制的 PCM/WAV 音频，返回识别文本"""
    if not SPEECH_AVAILABLE:
        return jsonify({"status": "error", "message": "语音服务未配置"}), 503

    if 'audio' not in request.files:
        return jsonify({"status": "error", "message": "缺少 audio 文件"}), 400

    audio_file = request.files['audio']
    audio_data = audio_file.read()
    if not audio_data:
        return jsonify({"status": "error", "message": "音频数据为空"}), 400

    # 前端 MediaRecorder 录制的是 webm，需要判断格式
    fmt = request.form.get('format', 'pcm')
    rate = int(request.form.get('rate', '16000'))

    try:
        text = _speech_client.speech_to_text(audio_data, fmt=fmt, rate=rate)
        return jsonify({"status": "success", "text": text})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/speech/polish', methods=['POST'])
@require_session
def polish_speech_text(session_id):
    """语音文本清洗：用 LLM 纠正语音识别中的技术术语错误。
    返回 { text: 纠正后文本, corrections: [{original, corrected, start, end}] }
    """
    data = request.json or {}
    raw_text = data.get('text', '')
    if not raw_text:
        return jsonify({"status": "error", "message": "文本为空"}), 400

    agent = _agents.get(session_id)
    if not agent or not agent.llm_client:
        return jsonify({"status": "success", "text": raw_text, "corrections": []})

    polish_prompt = """你是一个语音识别纠错助手。用户通过语音输入回答技术面试问题，但语音识别对英文技术术语的准确率很低，经常把英文词汇音译成中文。

请纠正以下文本中的技术术语错误，只修正明显的语音误识别，不要改变用户的原意和表达方式。

严格按 JSON 格式输出（不要输出任何其他内容）：
{"text": "纠正后的完整文本", "corrections": [{"original": "错误词", "corrected": "正确词"}]}

如果没有需要纠正的内容，corrections 返回空数组。

常见误识别参考：福莱克斯→Flask, 姜戈→Django, 瑞艾克特→React, 派森→Python, 加瓦→Java, 西加加→C++, 多克→Docker, 瑞迪斯→Redis, 卡夫卡→Kafka, 恩金艾克斯→Nginx, 库伯奈提斯→Kubernetes, 弗拉斯克→Flask, 泰森弗洛→TensorFlow, 派托奇→PyTorch, 麦艾斯克→MySQL, 蒙戈→MongoDB, 诺的→Node, 威优异→Vue, 斯普林→Spring, 盖特→Git, 艾皮艾→API, 杰森→JSON, 艾奇提提皮→HTTP"""

    messages = [
        {"role": "system", "content": polish_prompt},
        {"role": "user", "content": raw_text}
    ]

    try:
        import re
        result = agent.llm_client.generate(messages)
        json_match = re.search(r'\{[\s\S]*\}', result)
        if json_match:
            import json
            parsed = json.loads(json_match.group())
            return jsonify({
                "status": "success",
                "text": parsed.get("text", raw_text),
                "corrections": parsed.get("corrections", [])
            })
    except Exception as e:
        print(f"[polish] 语音纠错失败: {e}")

    return jsonify({"status": "success", "text": raw_text, "corrections": []})

@app.route('/api/speech/tts', methods=['POST'])
@require_session
def text_to_speech(session_id):
    """语音合成：接收文本，返回 PCM 音频二进制"""
    return _do_tts()


@app.route('/api/speech/tts-preview', methods=['POST'])
def tts_preview():
    """语音试听（无需认证，供配置页使用）"""
    return _do_tts()


@app.route('/api/debug/sysprompt', methods=['GET'])
def get_current_sysprompt():
    """获取当前 session 正在使用的 System Prompt（调试用途）"""
    session_id = request.args.get('session_id')
    
    if not session_id:
        return jsonify({
            "status": "error",
            "message": "缺少 session_id 参数"
        }), 400
    
    if session_id not in _agents:
        return jsonify({
            "status": "error",
            "message": "该 session 不存在或已过期"
        }), 404
    
    agent = _agents[session_id]
    
    # 获取 agent 的 current_prompt
    if hasattr(agent, 'prompt'):
        sysprompt = agent.prompt
        current_style = getattr(agent, 'current_style', 'unknown')
        
        return jsonify({
            "status": "success",
            "session_id": session_id,
            "sysprompt": sysprompt,
            "current_style": current_style,
            "prompt_length": len(sysprompt),
            "estimated_tokens": len(sysprompt) // 4
        })
    else:
        return jsonify({
            "status": "error",
            "message": "Agent 未初始化 prompt"
        }), 500


def _do_tts():
    """TTS 公共逻辑"""
    if not SPEECH_AVAILABLE:
        return jsonify({"status": "error", "message": "语音服务未配置"}), 503

    data = request.json or {}
    text = data.get('text', '')
    if not text:
        return jsonify({"status": "error", "message": "文本不能为空"}), 400

    per = data.get('per', 4115)
    spd = data.get('spd', 5)

    try:
        # aue=6 返回 wav（带 header，浏览器可直接播放）
        audio_bytes = _speech_client.text_to_speech(
            text, per=per, spd=spd, vol=8, aue=6
        )
        from flask import Response
        return Response(audio_bytes, mimetype='audio/wav')
    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    print("🚀 ProView API 服务已启动: http://127.0.0.1:5000")
    # 禁用 reloader 避免与 Playwright 冲突
    app.run(debug=True, port=5000, use_reloader=False, threaded=True)

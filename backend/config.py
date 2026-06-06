import os
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv, set_key

from runtime_paths import APP_DATA_ROOT, get_app_data_path, get_env_file_path, get_resource_path

load_dotenv(get_env_file_path())


def _read_env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default

BASE_DIR = str(get_resource_path())
APP_DATA_DIR = str(APP_DATA_ROOT)
UPLOAD_FOLDER = str(get_app_data_path('uploaded_resumes', is_dir=True))
STATIC_FOLDER = str(get_resource_path('static'))
RAG_DB_PATH = str(get_resource_path('data', 'RAG文档库_cleaned.xlsx'))
PDF_OUTPUT_DIR = str(get_app_data_path('temp', 'generated', is_dir=True))
OCR_PROCESSED_DIR = str(get_app_data_path('processed_images', is_dir=True))
OCR_OUTPUT_DIR = str(get_app_data_path('ocr_outputs', is_dir=True))

LOCAL_EMBEDDING_MODEL_DIR = os.getenv('LOCAL_EMBEDDING_MODEL_DIR', os.path.abspath(os.path.join(BASE_DIR, '..', 'start-data-service', 'onnx_models', 'all-MiniLM-L6-v2', 'onnx')))
LOCAL_EMBEDDING_MAX_LENGTH = int(os.getenv('LOCAL_EMBEDDING_MAX_LENGTH', '256'))

def _extract_supabase_project_ref(db_url: str) -> str:
    raw = (db_url or '').strip()
    if not raw:
        return ''
    try:
        parsed = urlparse(raw)
        if parsed.hostname and parsed.hostname.startswith('db.'):
            return parsed.hostname.split('.')[1]
        if parsed.username and '.' in parsed.username:
            prefix, project_ref = parsed.username.split('.', 1)
            if prefix == 'postgres' and project_ref:
                return project_ref
    except Exception:
        return ''
    return ''

RUNTIME_CONFIG_FIELDS = {
    "LOCAL_USER_NAME": {
        "label": "本机用户名",
        "secret": False,
        "default": "本地用户",
        "description": "单机模式下展示在界面中的当前用户名称。",
    },
    "DEEPSEEK_BASE_URL": {
        "label": "DeepSeek API URL",
        "secret": False,
        "default": "https://api.deepseek.com/v1",
        "description": "DeepSeek/OpenAI 兼容网关地址。",
    },
    "DEEPSEEK_API_KEY": {
        "label": "DeepSeek API Key",
        "secret": True,
        "default": "",
        "description": "用于 DeepSeek 模型调用。",
    },
    "ERNIE_BASE_URL": {
        "label": "文心 API URL",
        "secret": False,
        "default": "https://aistudio.baidu.com/llm/lmapi/v3",
        "description": "百度文心模型网关地址。",
    },
    "ERNIE_API_KEY": {
        "label": "文心 API Key",
        "secret": True,
        "default": "",
        "description": "用于文心模型调用。",
    },
    "INTERNAL_ERNIE_BASE_URL": {
        "label": "内测大模型（未开放）API URL",
        "secret": False,
        "default": "",
        "description": "仅限已获得本地内测地址的用户填写；留空时该模型入口不可用。",
    },
    "INTERNAL_ERNIE_MODEL": {
        "label": "内测大模型（未开放）模型名",
        "secret": False,
        "default": "ERNIE-4.5-21B-A3B",
        "description": "内测模型 ID，通常保持默认值。",
    },
    "PADDLEOCR_API_URL": {
        "label": "PaddleOCR API URL",
        "secret": True,
        "default": "",
        "description": "OCR 服务地址，需由用户在本机自行注入。",
    },
    "PADDLE_OCR_TOKEN": {
        "label": "PaddleOCR Token",
        "secret": True,
        "default": "",
        "description": "OCR 服务访问令牌。",
    },
    "BAIDU_APP_KEY": {
        "label": "百度语音 App Key",
        "secret": True,
        "default": "",
        "description": "语音识别/合成 App Key。",
    },
    "BAIDU_SECRET_KEY": {
        "label": "百度语音 Secret Key",
        "secret": True,
        "default": "",
        "description": "语音识别/合成 Secret Key。",
    },
    "PROVIEW_MONITORING_ENABLED": {
        "label": "启用运行追踪",
        "secret": False,
        "default": "1",
        "description": "控制 Langfuse 运行观测与追踪是否启用。",
    },
    "LANGFUSE_BASE_URL": {
        "label": "Langfuse Base URL",
        "secret": False,
        "default": "https://cloud.langfuse.com",
        "description": "Langfuse Cloud 或自托管实例地址。",
    },
    "LANGFUSE_PUBLIC_KEY": {
        "label": "Langfuse Public Key",
        "secret": True,
        "default": "",
        "description": "Langfuse 项目的 Public Key。",
    },
    "LANGFUSE_SECRET_KEY": {
        "label": "Langfuse Secret Key",
        "secret": True,
        "default": "",
        "description": "Langfuse 项目的 Secret Key。",
    },
}


def _build_cors_origins() -> list[str]:
    origins = ['http://localhost:5173', 'http://127.0.0.1:5173']
    if _read_env('PROVIEW_DESKTOP_MODE') == '1':
        origins.append('null')

    extra_cors_origins = _read_env('PROVIEW_EXTRA_CORS_ORIGINS', '')
    for origin in extra_cors_origins.split(','):
        value = origin.strip()
        if value and value not in origins:
            origins.append(value)
    return origins


def _mask_secret(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}{'*' * max(4, len(raw) - 8)}{raw[-4:]}"


def get_runtime_config_snapshot(mask_secrets: bool = True) -> dict:
    fields: dict[str, dict] = {}
    for key, meta in RUNTIME_CONFIG_FIELDS.items():
        raw_value = _read_env(key, meta.get("default", ""))
        secret = bool(meta.get("secret"))
        fields[key] = {
            "label": meta["label"],
            "secret": secret,
            "configured": bool(raw_value),
            "value": "" if mask_secrets and secret else raw_value,
            "display_value": _mask_secret(raw_value) if secret else raw_value,
            "description": meta.get("description", ""),
        }

    return {
        "env_file_path": str(get_env_file_path()),
        "fields": fields,
    }


def persist_runtime_config(updates: dict[str, object]) -> dict:
    env_path = Path(get_env_file_path())
    env_path.parent.mkdir(parents=True, exist_ok=True)
    if not env_path.exists():
        env_path.write_text("", encoding="utf-8")

    applied = False
    for key, value in updates.items():
        if key not in RUNTIME_CONFIG_FIELDS:
            continue
        normalized = "" if value is None else str(value).strip()
        set_key(str(env_path), key, normalized, quote_mode="auto")
        applied = True

    if applied:
        load_dotenv(env_path, override=True)
        reload_runtime_settings()

    return get_runtime_config_snapshot(mask_secrets=True)


BACKEND_DB_URL = ""
SUPABASE_PROJECT_REF = ""
SUPABASE_URL = ""
SUPABASE_SERVICE_ROLE_KEY = ""
SUPABASE_ANON_KEY = ""

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PDF_OUTPUT_DIR, exist_ok=True)
os.makedirs(OCR_PROCESSED_DIR, exist_ok=True)
os.makedirs(OCR_OUTPUT_DIR, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

DEEPSEEK_API_KEY = ""
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
ERNIE_API_KEY = ""
ERNIE_BASE_URL = "https://aistudio.baidu.com/llm/lmapi/v3"
INTERNAL_ERNIE_BASE_URL = ""
INTERNAL_ERNIE_MODEL = "ERNIE-4.5-21B-A3B"
SERPER_API_KEY = ""
SECRET_KEY = "proview-dev-secret"
CORS_ORIGINS = _build_cors_origins()
BAIDU_APP_KEY = ""
BAIDU_SECRET_KEY = ""
PADDLEOCR_API_URL = ""
PADDLE_OCR_TOKEN = ""
LOCAL_USER_NAME = "本地用户"


def reload_runtime_settings() -> dict:
    load_dotenv(get_env_file_path(), override=True)

    global BACKEND_DB_URL, SUPABASE_PROJECT_REF, SUPABASE_URL
    global SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY
    global LOCAL_EMBEDDING_MODEL_DIR, LOCAL_EMBEDDING_MAX_LENGTH
    global LOCAL_USER_NAME
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, ERNIE_API_KEY, ERNIE_BASE_URL
    global INTERNAL_ERNIE_BASE_URL, INTERNAL_ERNIE_MODEL
    global SERPER_API_KEY, SECRET_KEY, CORS_ORIGINS
    global BAIDU_APP_KEY, BAIDU_SECRET_KEY, PADDLEOCR_API_URL, PADDLE_OCR_TOKEN

    BACKEND_DB_URL = (
        _read_env('BACKEND_DB_URL')
        or _read_env('DATABASE_URL')
        or _read_env('SUPABASE_DB_URL')
    )
    SUPABASE_PROJECT_REF = _read_env('SUPABASE_PROJECT_REF') or _extract_supabase_project_ref(BACKEND_DB_URL)
    SUPABASE_URL = _read_env('SUPABASE_URL') or (f"https://{SUPABASE_PROJECT_REF}.supabase.co" if SUPABASE_PROJECT_REF else '')
    SUPABASE_SERVICE_ROLE_KEY = _read_env('SUPABASE_SERVICE_ROLE_KEY')
    SUPABASE_ANON_KEY = _read_env('SUPABASE_ANON_KEY')

    LOCAL_EMBEDDING_MODEL_DIR = _read_env(
        'LOCAL_EMBEDDING_MODEL_DIR',
        os.path.abspath(os.path.join(BASE_DIR, '..', 'start-data-service', 'onnx_models', 'all-MiniLM-L6-v2', 'onnx')),
    )
    LOCAL_EMBEDDING_MAX_LENGTH = int(_read_env('LOCAL_EMBEDDING_MAX_LENGTH', '256'))
    LOCAL_USER_NAME = _read_env('LOCAL_USER_NAME', '本地用户')

    DEEPSEEK_API_KEY = _read_env('DEEPSEEK_API_KEY')
    DEEPSEEK_BASE_URL = _read_env('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')
    ERNIE_API_KEY = _read_env('ERNIE_API_KEY')
    ERNIE_BASE_URL = _read_env('ERNIE_BASE_URL', 'https://aistudio.baidu.com/llm/lmapi/v3')
    INTERNAL_ERNIE_BASE_URL = _read_env('INTERNAL_ERNIE_BASE_URL')
    INTERNAL_ERNIE_MODEL = _read_env('INTERNAL_ERNIE_MODEL', 'ERNIE-4.5-21B-A3B')
    SERPER_API_KEY = _read_env('SERPER_API_KEY')
    SECRET_KEY = _read_env('SECRET_KEY', 'proview-dev-secret')
    CORS_ORIGINS = _build_cors_origins()
    BAIDU_APP_KEY = _read_env('BAIDU_APP_KEY')
    BAIDU_SECRET_KEY = _read_env('BAIDU_SECRET_KEY')
    PADDLEOCR_API_URL = _read_env('PADDLEOCR_API_URL')
    PADDLE_OCR_TOKEN = _read_env('PADDLE_OCR_TOKEN')

    return get_runtime_config_snapshot(mask_secrets=True)


reload_runtime_settings()


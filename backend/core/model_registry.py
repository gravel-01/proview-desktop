"""
File-backed model registry for desktop runtime configuration.

The desktop app stores text-model definitions in `backend-data/models.json`
instead of `.env`. Legacy `DEEPSEEK_* / ERNIE_*` values are only used as a
one-time import source when the models file does not exist yet.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from runtime_paths import get_models_file_path


MODEL_CONFIG_VERSION = 1
MODEL_PROVIDER_TYPE = "openai_compatible"
LEGACY_IMPORT_VERSION = 1
LEGACY_IMPORT_SOURCE = "legacy_env"

_LEGACY_MODEL_BLUEPRINTS = (
    {
        "legacy_id": "deepseek",
        "name": "DeepSeek",
        "model": "deepseek-chat",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "api_key_env": "DEEPSEEK_API_KEY",
        "default_base_url": "https://api.deepseek.com/v1",
    },
    {
        "legacy_id": "ernie",
        "name": "文心一言",
        "model": "ERNIE-4.5-21B-A3B",
        "base_url_env": "ERNIE_BASE_URL",
        "api_key_env": "ERNIE_API_KEY",
        "default_base_url": "https://aistudio.baidu.com/llm/lmapi/v3",
    },
    {
        "legacy_id": "ernie-thinking",
        "name": "文心（深度思考）",
        "model": "ernie-5.0-thinking-preview",
        "base_url_env": "ERNIE_BASE_URL",
        "api_key_env": "ERNIE_API_KEY",
        "default_base_url": "https://aistudio.baidu.com/llm/lmapi/v3",
    },
)


@dataclass
class ModelProvider:
    """Single configured text model."""

    id: str
    name: str
    provider: str
    model: str
    api_key: str
    base_url: str
    enabled: bool
    created_at: str = ""
    updated_at: str = ""

    @property
    def key(self) -> str:
        return self.id

    @property
    def label(self) -> str:
        return self.name

    @property
    def configured(self) -> bool:
        return bool(self.model and self.base_url and self.api_key)

    @property
    def available(self) -> bool:
        return self.enabled and self.configured


@dataclass
class ResolvedModelSelection:
    route: str
    model: Optional[ModelProvider]
    requested_model_id: str = ""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _models_file_path() -> Path:
    path = get_models_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _new_model_id() -> str:
    return f"model_{uuid.uuid4().hex[:12]}"


def _read_env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _mask_secret(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if len(raw) <= 8:
        return "*" * len(raw)
    return f"{raw[:4]}{'*' * max(4, len(raw) - 8)}{raw[-4:]}"


def _normalize_bool(value: object, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _normalize_record(raw: dict, *, existing_id: str = "") -> Optional[dict]:
    if not isinstance(raw, dict):
        return None

    model_id = str(raw.get("id") or existing_id or "").strip() or _new_model_id()
    name = str(raw.get("name") or raw.get("label") or model_id).strip() or model_id
    provider = str(raw.get("provider") or MODEL_PROVIDER_TYPE).strip() or MODEL_PROVIDER_TYPE
    model_name = str(raw.get("model") or "").strip()
    base_url = str(raw.get("base_url") or "").strip()
    api_key = str(raw.get("api_key") or "").strip()
    created_at = str(raw.get("created_at") or "").strip() or _utc_now()
    updated_at = str(raw.get("updated_at") or "").strip() or _utc_now()

    return {
        "id": model_id,
        "name": name,
        "provider": provider,
        "model": model_name,
        "base_url": base_url,
        "api_key": api_key,
        "enabled": _normalize_bool(raw.get("enabled"), default=True),
        "created_at": created_at,
        "updated_at": updated_at,
    }


def _provider_from_record(raw: dict) -> Optional[ModelProvider]:
    normalized = _normalize_record(raw)
    if not normalized:
        return None
    return ModelProvider(**normalized)


def _legacy_env_has_value(blueprint: dict) -> bool:
    return bool(_read_env(blueprint["api_key_env"]) or _read_env(blueprint["base_url_env"]))


def _legacy_import_message(status: str, imported_count: int = 0) -> str:
    if status == "imported":
        return f"已从旧 .env 配置导入 {imported_count} 个模型实例。"
    if status == "imported_incomplete":
        return f"已读取旧 .env 配置并创建 {imported_count} 个模型实例，但还需要补齐 API Key 后才能使用。"
    if status == "not_found":
        return "未发现可导入的旧模型配置。"
    if status == "skipped_existing_models_file":
        return "已存在 models.json，本次未重复从旧 .env 导入。"
    if status == "recreated_after_invalid_file":
        return "原 models.json 无法读取，已重新初始化模型配置。"
    return "模型配置导入状态未知。"


def _normalize_legacy_import_summary(raw: object) -> dict:
    if not isinstance(raw, dict):
        return _build_legacy_import_summary(status="skipped_existing_models_file", existing_models_file=True)

    status = str(raw.get("status") or "unknown").strip() or "unknown"
    imported_ids = [
        str(item).strip()
        for item in (raw.get("imported_model_ids") or [])
        if str(item).strip()
    ]
    imported_count = int(raw.get("imported_count") or len(imported_ids) or 0)
    available_count = int(raw.get("available_count") or 0)
    message = str(raw.get("message") or _legacy_import_message(status, imported_count)).strip()
    checked_at = str(raw.get("checked_at") or raw.get("created_at") or _utc_now()).strip()

    return {
        "version": LEGACY_IMPORT_VERSION,
        "source": LEGACY_IMPORT_SOURCE,
        "status": status,
        "checked_at": checked_at,
        "legacy_config_found": bool(raw.get("legacy_config_found")),
        "existing_models_file": bool(raw.get("existing_models_file")),
        "imported_count": imported_count,
        "available_count": available_count,
        "imported_model_ids": imported_ids,
        "message": message,
    }


def _build_legacy_import_summary(
    *,
    status: str,
    models: Optional[list[dict]] = None,
    existing_models_file: bool = False,
) -> dict:
    model_records = models or []
    imported_ids = [
        str(item.get("id") or "").strip()
        for item in model_records
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    ]
    imported_count = len(imported_ids)
    available_count = sum(
        1
        for item in model_records
        if isinstance(item, dict) and bool(item.get("enabled")) and bool(item.get("api_key"))
    )
    legacy_config_found = any(_legacy_env_has_value(blueprint) for blueprint in _LEGACY_MODEL_BLUEPRINTS)

    return {
        "version": LEGACY_IMPORT_VERSION,
        "source": LEGACY_IMPORT_SOURCE,
        "status": status,
        "checked_at": _utc_now(),
        "legacy_config_found": legacy_config_found,
        "existing_models_file": existing_models_file,
        "imported_count": imported_count,
        "available_count": available_count,
        "imported_model_ids": imported_ids,
        "message": _legacy_import_message(status, imported_count),
    }


def _read_snapshot() -> dict:
    path = _models_file_path()
    if not path.exists():
        snapshot = _build_initial_snapshot_from_legacy_env()
        _write_snapshot(snapshot)
        return snapshot

    try:
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
    except Exception:
        snapshot = _build_initial_snapshot_from_legacy_env()
        snapshot["legacy_import"] = _build_legacy_import_summary(
            status="recreated_after_invalid_file",
            models=snapshot.get("models") or [],
            existing_models_file=True,
        )
        _write_snapshot(snapshot)
        return snapshot

    models = []
    seen_ids: set[str] = set()
    for raw in payload.get("models") or []:
        normalized = _normalize_record(raw)
        if not normalized:
            continue
        if normalized["id"] in seen_ids:
            normalized["id"] = _new_model_id()
        seen_ids.add(normalized["id"])
        models.append(normalized)

    default_model_id = str(payload.get("default_model_id") or "").strip()
    snapshot = {
        "version": MODEL_CONFIG_VERSION,
        "default_model_id": default_model_id,
        "models": models,
        "legacy_import": _normalize_legacy_import_summary(
            payload.get("legacy_import")
            if isinstance(payload.get("legacy_import"), dict)
            else {
                "status": "skipped_existing_models_file",
                "existing_models_file": True,
                "legacy_config_found": any(_legacy_env_has_value(blueprint) for blueprint in _LEGACY_MODEL_BLUEPRINTS),
            }
        ),
    }
    normalized_snapshot = _normalize_snapshot(snapshot)
    if normalized_snapshot != snapshot:
        _write_snapshot(normalized_snapshot)
    return normalized_snapshot


def _normalize_snapshot(snapshot: dict) -> dict:
    models = snapshot.get("models") or []
    providers = [provider for provider in (_provider_from_record(item) for item in models) if provider]
    default_model_id = str(snapshot.get("default_model_id") or "").strip()

    available_ids = [provider.id for provider in providers if provider.available]
    all_ids = [provider.id for provider in providers]
    if default_model_id not in available_ids:
        default_model_id = available_ids[0] if available_ids else ""
    if default_model_id and default_model_id not in all_ids:
        default_model_id = ""

    return {
        "version": MODEL_CONFIG_VERSION,
        "default_model_id": default_model_id,
        "models": [provider.__dict__ for provider in providers],
        "legacy_import": _normalize_legacy_import_summary(snapshot.get("legacy_import")),
    }


def _write_snapshot(snapshot: dict) -> dict:
    normalized = _normalize_snapshot(snapshot)
    path = _models_file_path()
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


def _build_initial_snapshot_from_legacy_env() -> dict:
    models: list[dict] = []
    for blueprint in _LEGACY_MODEL_BLUEPRINTS:
        api_key = _read_env(blueprint["api_key_env"])
        base_url = _read_env(blueprint["base_url_env"], blueprint["default_base_url"])
        if not api_key and base_url == blueprint["default_base_url"] and not _read_env(blueprint["base_url_env"]):
            continue
        models.append(
            {
                "id": blueprint["legacy_id"],
                "name": blueprint["name"],
                "provider": MODEL_PROVIDER_TYPE,
                "model": blueprint["model"],
                "base_url": base_url,
                "api_key": api_key,
                "enabled": bool(api_key),
                "created_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )

    preferred_default = ""
    for legacy_id in ("ernie", "deepseek", "ernie-thinking"):
        provider = next((item for item in models if item["id"] == legacy_id and item["enabled"] and item["api_key"]), None)
        if provider:
            preferred_default = provider["id"]
            break

    if not preferred_default:
        first_available = next((item["id"] for item in models if item["enabled"] and item["api_key"]), "")
        preferred_default = first_available

    status = "not_found"
    if models:
        status = "imported" if any(item["enabled"] and item["api_key"] for item in models) else "imported_incomplete"

    return {
        "version": MODEL_CONFIG_VERSION,
        "default_model_id": preferred_default,
        "models": models,
        "legacy_import": _build_legacy_import_summary(status=status, models=models),
    }


def init_providers(**_kwargs) -> dict:
    """Legacy entrypoint kept for app startup compatibility."""
    return _read_snapshot()


def list_models(mask_secrets: bool = True) -> dict:
    snapshot = _read_snapshot()
    default_model_id = snapshot["default_model_id"]
    models = []
    for raw in snapshot["models"]:
        provider = _provider_from_record(raw)
        if not provider:
            continue
        models.append(
            {
                "id": provider.id,
                "key": provider.id,
                "name": provider.name,
                "label": provider.name,
                "provider": provider.provider,
                "model": provider.model,
                "base_url": provider.base_url,
                "enabled": provider.enabled,
                "available": provider.available,
                "configured": provider.configured,
                "is_default": provider.id == default_model_id,
                "api_key_configured": bool(provider.api_key),
                "api_key_display": _mask_secret(provider.api_key) if mask_secrets else provider.api_key,
                "created_at": provider.created_at,
                "updated_at": provider.updated_at,
            }
        )

    return {
        "version": snapshot["version"],
        "default_model_id": default_model_id,
        "file_path": str(_models_file_path()),
        "legacy_import": snapshot["legacy_import"],
        "models": models,
    }


def list_available_providers() -> list[dict]:
    return list_models(mask_secrets=True)["models"]


def get_provider(key: str) -> Optional[ModelProvider]:
    model_id = str(key or "").strip()
    if not model_id:
        return None
    snapshot = _read_snapshot()
    for raw in snapshot["models"]:
        provider = _provider_from_record(raw)
        if provider and provider.id == model_id:
            return provider
    return None


def get_default_provider() -> Optional[ModelProvider]:
    snapshot = _read_snapshot()
    default_model_id = snapshot["default_model_id"]
    provider = get_provider(default_model_id) if default_model_id else None
    if provider and provider.available:
        return provider
    for raw in snapshot["models"]:
        candidate = _provider_from_record(raw)
        if candidate and candidate.available:
            return candidate
    return None


def resolve_model_selection(requested_model_id: str = "") -> ResolvedModelSelection:
    requested = str(requested_model_id or "").strip()
    if requested:
        provider = get_provider(requested)
        if provider and provider.available:
            return ResolvedModelSelection(
                route="session_selected",
                model=provider,
                requested_model_id=requested,
            )

    default_provider = get_default_provider()
    return ResolvedModelSelection(
        route="global_default",
        model=default_provider,
        requested_model_id=requested,
    )


def create_provider(payload: dict) -> dict:
    snapshot = _read_snapshot()
    record = _normalize_record(payload)
    if not record:
        raise ValueError("模型配置无效")

    record["id"] = record["id"] if record["id"] not in {item["id"] for item in snapshot["models"]} else _new_model_id()
    record["created_at"] = record["created_at"] or _utc_now()
    record["updated_at"] = _utc_now()
    snapshot["models"].append(record)

    if not snapshot["default_model_id"]:
        provider = _provider_from_record(record)
        if provider and provider.available:
            snapshot["default_model_id"] = provider.id

    _write_snapshot(snapshot)
    return list_models(mask_secrets=True)


def update_provider(model_id: str, payload: dict) -> dict:
    target_id = str(model_id or "").strip()
    if not target_id:
        raise ValueError("模型 ID 不能为空")

    snapshot = _read_snapshot()
    for index, raw in enumerate(snapshot["models"]):
        if str(raw.get("id") or "").strip() != target_id:
            continue
        updated = dict(raw)
        for key in ("name", "provider", "model", "base_url", "enabled"):
            if key in payload:
                updated[key] = payload.get(key)
        if "api_key" in payload:
            updated["api_key"] = payload.get("api_key")
        updated["updated_at"] = _utc_now()
        normalized = _normalize_record(updated, existing_id=target_id)
        if not normalized:
            raise ValueError("模型配置无效")
        snapshot["models"][index] = normalized
        _write_snapshot(snapshot)
        return list_models(mask_secrets=True)

    raise KeyError(target_id)


def delete_provider(model_id: str) -> dict:
    target_id = str(model_id or "").strip()
    snapshot = _read_snapshot()
    before_count = len(snapshot["models"])
    snapshot["models"] = [
        raw for raw in snapshot["models"] if str(raw.get("id") or "").strip() != target_id
    ]
    if len(snapshot["models"]) == before_count:
        raise KeyError(target_id)
    if snapshot["default_model_id"] == target_id:
        snapshot["default_model_id"] = ""
    _write_snapshot(snapshot)
    return list_models(mask_secrets=True)


def set_default_provider(model_id: str) -> dict:
    target_id = str(model_id or "").strip()
    provider = get_provider(target_id)
    if not provider:
        raise KeyError(target_id)
    if not provider.available:
        raise ValueError("默认模型必须是已启用且字段完整的模型")
    snapshot = _read_snapshot()
    snapshot["default_model_id"] = target_id
    _write_snapshot(snapshot)
    return list_models(mask_secrets=True)


def _redact_probe_message(message: object, provider: ModelProvider) -> str:
    text = str(message or "").strip()
    if not text:
        return ""

    if provider.api_key:
        text = text.replace(provider.api_key, _mask_secret(provider.api_key))

    text = re.sub(r"sk-[A-Za-z0-9_-]{8,}", "sk-***", text)
    text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._-]{8,}", r"\1***", text)
    text = re.sub(r"(?i)(api[_-]?key=)[^\s&]+", r"\1***", text)
    text = re.sub(r"(?i)(authorization:\s*)[^\s]+", r"\1***", text)
    return text[:320]


def _build_probe_client(provider: ModelProvider, timeout_seconds: float):
    from openai import OpenAI

    return OpenAI(
        api_key=provider.api_key,
        base_url=provider.base_url,
        timeout=timeout_seconds,
    )


def probe_model_connection(
    provider: ModelProvider,
    *,
    timeout_seconds: float = 10.0,
    client_factory: Optional[Callable[[ModelProvider, float], Any]] = None,
) -> dict:
    missing_fields = []
    if not provider.enabled:
        missing_fields.append("enabled")
    if not provider.model:
        missing_fields.append("model")
    if not provider.base_url:
        missing_fields.append("base_url")
    if not provider.api_key:
        missing_fields.append("api_key")

    if missing_fields:
        return {
            "ok": False,
            "code": "model_not_configured",
            "message": "模型配置不完整，请先补齐启用状态、模型 ID、基础 URL 和 API Key。",
            "missing_fields": missing_fields,
        }

    started_at = time.perf_counter()
    try:
        factory = client_factory or _build_probe_client
        client = factory(provider, timeout_seconds)
        client.chat.completions.create(
            model=provider.model,
            messages=[
                {
                    "role": "user",
                    "content": "Reply with the single word: ok",
                }
            ],
            max_tokens=8,
            temperature=0,
            stream=False,
        )
        return {
            "ok": True,
            "code": "ok",
            "message": "连接成功，模型接口已响应。",
            "latency_ms": int((time.perf_counter() - started_at) * 1000),
        }
    except Exception as exc:
        return {
            "ok": False,
            "code": "connection_failed",
            "message": _redact_probe_message(exc, provider) or "连接测试失败，请检查模型 ID、Base URL、API Key 或网络状态。",
            "latency_ms": int((time.perf_counter() - started_at) * 1000),
        }

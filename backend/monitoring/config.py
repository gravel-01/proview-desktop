"""Monitoring configuration helpers."""
import os
from dataclasses import dataclass


def _read_env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _read_bool(key: str, default: bool) -> bool:
    raw = _read_env(key, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


def _read_int(key: str, default: int) -> int:
    raw = _read_env(key, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class MonitoringConfig:
    enabled: bool
    langfuse_secret_key: str
    langfuse_public_key: str
    langfuse_base_url: str
    default_hours: int
    timeout_seconds: int
    preview_chars: int
    allow_full_trace: bool

    @property
    def configured(self) -> bool:
        return bool(
            self.langfuse_secret_key
            and self.langfuse_public_key
            and self.langfuse_base_url
        )


def get_monitoring_config() -> MonitoringConfig:
    return MonitoringConfig(
        enabled=_read_bool("PROVIEW_MONITORING_ENABLED", True),
        langfuse_secret_key=_read_env("LANGFUSE_SECRET_KEY"),
        langfuse_public_key=_read_env("LANGFUSE_PUBLIC_KEY"),
        langfuse_base_url=_read_env("LANGFUSE_BASE_URL"),
        default_hours=_read_int("PROVIEW_MONITORING_DEFAULT_HOURS", 24),
        timeout_seconds=_read_int("PROVIEW_MONITORING_TIMEOUT_SECONDS", 10),
        preview_chars=_read_int("PROVIEW_MONITORING_PREVIEW_CHARS", 200),
        allow_full_trace=_read_bool("PROVIEW_MONITORING_ALLOW_FULL_TRACE", False),
    )


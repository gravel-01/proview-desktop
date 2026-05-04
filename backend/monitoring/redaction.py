"""Redaction helpers for monitoring responses."""
from __future__ import annotations

import re
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "resume",
    "phone",
    "mobile",
    "email",
    "身份证",
    "手机号",
    "邮箱",
    "简历",
}

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)")


def redact_text(value: Any, preview_chars: int = 200) -> str:
    text = "" if value is None else str(value)
    text = EMAIL_RE.sub("[redacted-email]", text)
    text = PHONE_RE.sub("[redacted-phone]", text)
    if preview_chars > 0 and len(text) > preview_chars:
        return f"{text[:preview_chars]}..."
    return text


def redact_mapping(value: Any, preview_chars: int = 200) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(sensitive in key_text for sensitive in SENSITIVE_KEYS):
                redacted[key] = "[redacted]"
            else:
                redacted[key] = redact_mapping(item, preview_chars=preview_chars)
        return redacted
    if isinstance(value, list):
        return [redact_mapping(item, preview_chars=preview_chars) for item in value]
    if isinstance(value, str):
        return redact_text(value, preview_chars=preview_chars)
    return value


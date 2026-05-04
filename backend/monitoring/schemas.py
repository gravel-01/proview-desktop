"""Response schema builders for monitoring APIs."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass(frozen=True)
class TimeRange:
    start: str
    end: str


@dataclass(frozen=True)
class MonitoringEnvelope:
    configured: bool
    available: bool
    source: str
    range: Optional[TimeRange]
    data: Any
    message: str = ""

    def to_dict(self) -> dict:
        payload = asdict(self)
        if self.range is not None:
            payload["range"] = asdict(self.range)
        return payload


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def monitoring_response(
    *,
    configured: bool,
    available: bool,
    data: Any,
    time_range: Optional[TimeRange] = None,
    message: str = "",
    source: str = "langfuse",
) -> dict:
    return MonitoringEnvelope(
        configured=configured,
        available=available,
        source=source,
        range=time_range,
        data=data,
        message=message,
    ).to_dict()

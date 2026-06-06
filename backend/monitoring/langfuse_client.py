"""Langfuse API client boundary for ProView monitoring."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from .config import MonitoringConfig, get_monitoring_config
from .redaction import redact_mapping, redact_text

OBSERVATION_FIELDS = ",".join(
    [
        "id",
        "traceId",
        "type",
        "name",
        "startTime",
        "endTime",
        "model",
        "usage",
        "usageDetails",
        "inputUsage",
        "outputUsage",
        "totalUsage",
        "promptTokens",
        "completionTokens",
        "totalTokens",
        "totalCost",
        "calculatedTotalCost",
        "latency",
        "parentObservationId",
        "level",
        "statusMessage",
        "input",
        "output",
    ]
)


@dataclass(frozen=True)
class LangfuseClientStatus:
    configured: bool
    available: bool
    message: str


class LangfuseMonitoringClient:
    def __init__(self, config: Optional[MonitoringConfig] = None):
        self.config = config or get_monitoring_config()
        self._client = None

    def status(self) -> LangfuseClientStatus:
        if not self.config.enabled:
            return LangfuseClientStatus(False, False, "Monitoring is disabled")
        if not self.config.configured:
            return LangfuseClientStatus(
                False,
                False,
                "LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, or LANGFUSE_BASE_URL is missing",
            )
        return LangfuseClientStatus(True, True, "Langfuse monitoring is configured")

    def fetch_recent_traces(self, *, hours: int, limit: int) -> list[dict[str, Any]]:
        client = self._get_client()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=max(1, hours))
        response = client.api.trace.list(
            limit=max(1, min(limit, 100)),
            from_timestamp=start_time,
            to_timestamp=end_time,
            order_by="timestamp.desc",
        )
        payload = _dump_model(response)
        traces = payload.get("data", []) if isinstance(payload, dict) else []
        return [self._summarize_trace(trace) for trace in traces]

    def fetch_recent_observations(self, *, hours: int, limit: int = 100) -> list[dict[str, Any]]:
        client = self._get_client()
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=max(1, hours))
        response = client.api.observations.get_many(
            limit=max(1, min(limit, 100)),
            from_start_time=start_time,
            to_start_time=end_time,
            fields=OBSERVATION_FIELDS,
        )
        payload = _dump_model(response)
        observations = payload.get("data", []) if isinstance(payload, dict) else []
        summarized = [self._summarize_observation(observation) for observation in observations]
        return self._backfill_observation_usage_from_trace_details(client, summarized)

    def fetch_trace_detail(self, trace_id: str) -> dict[str, Any]:
        client = self._get_client()
        trace_payload = _dump_model(client.api.trace.get(trace_id))
        observations = trace_payload.get("observations") or []
        if not observations:
            observations_payload = _dump_model(
                client.api.observations.get_many(
                    trace_id=trace_id,
                    limit=100,
                    fields=OBSERVATION_FIELDS,
                )
            )
            if isinstance(observations_payload, dict):
                observations = observations_payload.get("data", []) or []

        detail = self._redact_trace_detail(trace_payload)
        detail["observations"] = _enrich_tool_observation_names(
            [self._summarize_observation(observation) for observation in observations],
            detail.get("tool_names") or [],
        )
        return detail

    def _get_client(self):
        status = self.status()
        if not status.available:
            raise RuntimeError(status.message)
        if self._client is not None:
            return self._client

        try:
            from langfuse import Langfuse
        except Exception as exc:
            raise RuntimeError("langfuse package is not installed") from exc

        try:
            self._client = Langfuse(
                public_key=self.config.langfuse_public_key,
                secret_key=self.config.langfuse_secret_key,
                base_url=self.config.langfuse_base_url,
            )
        except TypeError:
            self._client = Langfuse(
                public_key=self.config.langfuse_public_key,
                secret_key=self.config.langfuse_secret_key,
                host=self.config.langfuse_base_url,
            )
        return self._client

    def _summarize_trace(self, trace: dict[str, Any]) -> dict[str, Any]:
        metadata = trace.get("metadata") or {}
        return {
            "trace_id": trace.get("id"),
            "timestamp": _stringify_datetime(trace.get("timestamp")),
            "session_id": trace.get("session_id") or trace.get("sessionId"),
            "name": trace.get("name"),
            "status": _infer_trace_status(trace),
            "duration_ms": _seconds_to_ms(trace.get("latency")),
            "input_preview": redact_text(trace.get("input"), self.config.preview_chars),
            "output_preview": redact_text(trace.get("output"), self.config.preview_chars),
            "total_cost": trace.get("total_cost") or trace.get("totalCost"),
            "tags": trace.get("tags") or [],
            "tool_names": _extract_tool_names(trace.get("output")),
            "business_context": _extract_business_context(metadata),
        }

    def _redact_trace_detail(self, trace: dict[str, Any]) -> dict[str, Any]:
        summary = self._summarize_trace(trace)
        summary.update(
            {
                "user_id": trace.get("user_id") or trace.get("userId"),
                "release": trace.get("release"),
                "version": trace.get("version"),
                "environment": trace.get("environment"),
                "metadata": redact_mapping(
                    trace.get("metadata") or {},
                    preview_chars=self.config.preview_chars,
                ),
                "scores": redact_mapping(
                    trace.get("scores") or [],
                    preview_chars=self.config.preview_chars,
                ),
            }
        )
        if self.config.allow_full_trace:
            summary["input"] = redact_mapping(trace.get("input"), self.config.preview_chars)
            summary["output"] = redact_mapping(trace.get("output"), self.config.preview_chars)
        return summary

    def _summarize_observation(self, observation: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": observation.get("id"),
            "trace_id": observation.get("trace_id") or observation.get("traceId"),
            "parent_observation_id": (
                observation.get("parent_observation_id")
                or observation.get("parentObservationId")
            ),
            "name": observation.get("name"),
            "type": observation.get("type"),
            "level": observation.get("level"),
            "status_message": observation.get("status_message")
            or observation.get("statusMessage"),
            "start_time": _stringify_datetime(
                observation.get("start_time") or observation.get("startTime")
            ),
            "end_time": _stringify_datetime(
                observation.get("end_time") or observation.get("endTime")
            ),
            "duration_ms": _observation_duration_ms(observation),
            "model": _non_empty(
                observation.get("model")
                or observation.get("model_id")
                or observation.get("modelId")
                or observation.get("internalModelId")
            ),
            "input_preview": redact_text(
                observation.get("input"),
                self.config.preview_chars,
            ),
            "output_preview": redact_text(
                observation.get("output"),
                self.config.preview_chars,
            ),
            "usage": _extract_observation_usage(observation),
            "cost": observation.get("calculated_total_cost")
            or observation.get("calculatedTotalCost")
            or observation.get("total_cost")
            or observation.get("totalCost"),
        }

    def _backfill_observation_usage_from_trace_details(
        self,
        client,
        observations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        missing_usage_trace_ids = []
        for observation in observations:
            if str(observation.get("type") or "").lower() not in {"generation", "llm"}:
                continue
            if observation.get("usage"):
                continue
            trace_id = observation.get("trace_id")
            if trace_id and trace_id not in missing_usage_trace_ids:
                missing_usage_trace_ids.append(trace_id)

        if not missing_usage_trace_ids:
            return observations

        usage_by_observation_id: dict[str, dict[str, Any]] = {}
        cost_by_observation_id: dict[str, Any] = {}
        for trace_id in missing_usage_trace_ids[:25]:
            try:
                trace_payload = _dump_model(client.api.trace.get(trace_id))
            except Exception:
                continue
            for raw_observation in trace_payload.get("observations") or []:
                if not isinstance(raw_observation, dict):
                    continue
                observation_id = raw_observation.get("id")
                if not observation_id:
                    continue
                usage = _extract_observation_usage(raw_observation)
                if usage:
                    usage_by_observation_id[str(observation_id)] = usage
                cost = (
                    raw_observation.get("calculated_total_cost")
                    or raw_observation.get("calculatedTotalCost")
                    or raw_observation.get("total_cost")
                    or raw_observation.get("totalCost")
                )
                if cost is not None:
                    cost_by_observation_id[str(observation_id)] = cost

        if not usage_by_observation_id and not cost_by_observation_id:
            return observations

        for observation in observations:
            observation_id = str(observation.get("id") or "")
            if observation_id in usage_by_observation_id and not observation.get("usage"):
                observation["usage"] = usage_by_observation_id[observation_id]
            if observation_id in cost_by_observation_id and observation.get("cost") in (None, ""):
                observation["cost"] = cost_by_observation_id[observation_id]
        return observations


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", by_alias=False)
    if hasattr(value, "dict"):
        return value.dict()
    return value


def _stringify_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _seconds_to_ms(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(float(value) * 1000)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _observation_duration_ms(observation: dict[str, Any]) -> Optional[int]:
    latency_ms = _seconds_to_ms(observation.get("latency"))
    if latency_ms is not None:
        return latency_ms
    start = _parse_datetime(observation.get("start_time") or observation.get("startTime"))
    end = _parse_datetime(observation.get("end_time") or observation.get("endTime"))
    if not start or not end:
        return None
    return int((end - start).total_seconds() * 1000)


def _infer_trace_status(trace: dict[str, Any]) -> str:
    observations = trace.get("observations") or []
    if any(str(obs.get("level", "")).upper() == "ERROR" for obs in observations if isinstance(obs, dict)):
        return "error"
    return "success"


def _non_empty(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_observation_usage(observation: dict[str, Any]) -> dict[str, Any]:
    usage = observation.get("usage") or observation.get("usage_details") or observation.get("usageDetails")
    if isinstance(usage, dict) and usage:
        result = _normalize_usage_mapping(usage)
        if result:
            return result

    input_tokens = (
        observation.get("inputUsage")
        or observation.get("input_usage")
        or observation.get("promptTokens")
        or observation.get("prompt_tokens")
        or observation.get("prompt_tokens")
    )
    output_tokens = (
        observation.get("outputUsage")
        or observation.get("output_usage")
        or observation.get("completionTokens")
        or observation.get("completion_tokens")
        or observation.get("completion_tokens")
    )
    total_tokens = (
        observation.get("totalUsage")
        or observation.get("total_usage")
        or observation.get("totalTokens")
        or observation.get("total_tokens")
        or observation.get("total_tokens")
    )
    result = {}
    if input_tokens is not None:
        result["input"] = input_tokens
    if output_tokens is not None:
        result["output"] = output_tokens
    if total_tokens is not None:
        result["total"] = total_tokens
    return result


def _normalize_usage_mapping(usage: dict[str, Any]) -> dict[str, Any]:
    usage = _dump_model(usage)
    if not isinstance(usage, dict):
        return {}

    aliases = {
        "input": ("input", "input_tokens", "inputTokens", "prompt_tokens", "promptTokens"),
        "output": ("output", "output_tokens", "outputTokens", "completion_tokens", "completionTokens"),
        "total": ("total", "total_tokens", "totalTokens"),
    }
    result: dict[str, Any] = {}
    for target, candidates in aliases.items():
        for key in candidates:
            value = _extract_usage_value(usage.get(key))
            if value is not None:
                result[target] = value
                break
    if result:
        return result
    return usage


def _extract_usage_value(value: Any) -> Any:
    value = _dump_model(value)
    if isinstance(value, dict):
        for key in ("tokens", "total", "value", "count"):
            if value.get(key) is not None:
                return value.get(key)
        return None
    return value


def _extract_tool_names(output: Any) -> list[str]:
    steps = []
    if isinstance(output, dict):
        steps = output.get("intermediate_steps") or []
    names = []
    for step in steps:
        action = None
        if isinstance(step, (list, tuple)) and step:
            action = step[0]
        elif isinstance(step, dict):
            action = step
        tool_name = _extract_tool_name_from_action(action)
        if tool_name:
            names.append(tool_name)
    return names


def _extract_tool_name_from_action(action: Any) -> Optional[str]:
    if not isinstance(action, dict):
        return None
    if action.get("tool"):
        return str(action.get("tool"))
    kwargs = action.get("kwargs")
    if isinstance(kwargs, dict) and kwargs.get("tool"):
        return str(kwargs.get("tool"))
    return None


def _extract_business_context(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    keys = [
        "proview_schema_version",
        "proview_session_id",
        "interaction_type",
        "agent_role",
        "model_provider",
        "model_name",
        "model_label",
        "job_title",
        "interview_type",
        "difficulty",
        "interview_style",
        "has_resume",
        "feature_vad",
        "feature_deep",
        "context_version",
        "turn_id",
        "turn_no",
        "question_id",
        "agent_event_type",
    ]
    context = {}
    for key in keys:
        value = metadata.get(key)
        if value not in (None, ""):
            context[key] = value
    return context


def _enrich_tool_observation_names(
    observations: list[dict[str, Any]],
    tool_names: list[str],
) -> list[dict[str, Any]]:
    tool_index = 0
    for observation in observations:
        if str(observation.get("type") or "").upper() != "TOOL":
            continue
        if not observation.get("name") and tool_index < len(tool_names):
            observation["name"] = tool_names[tool_index]
        tool_index += 1
    return observations

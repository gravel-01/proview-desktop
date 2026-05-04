"""Metric aggregation boundary for Langfuse-backed monitoring."""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional


def build_overview_metrics(raw_data: dict[str, Any]) -> dict[str, Any]:
    traces = raw_data.get("traces") or []
    observations = raw_data.get("observations") or []

    llm_calls = [obs for obs in observations if _is_llm_observation(obs)]
    tool_calls = [obs for obs in observations if _is_tool_observation(obs)]
    error_observations = [obs for obs in observations if _is_error_observation(obs)]
    error_traces = [trace for trace in traces if trace.get("status") == "error"]
    trace_count = len(traces)
    success_count = max(0, trace_count - len(error_traces))

    total_cost = _sum_number(trace.get("total_cost") for trace in traces)
    avg_trace_latency_ms = _avg_number(trace.get("duration_ms") for trace in traces)
    p95_trace_latency_ms = _percentile(
        [trace.get("duration_ms") for trace in traces],
        95,
    )

    return {
        "trace_count": trace_count,
        "observation_count": len(observations),
        "llm_call_count": len(llm_calls),
        "tool_call_count": len(tool_calls),
        "error_count": len(error_traces) + len(error_observations),
        "success_rate": round(success_count / trace_count, 4) if trace_count else None,
        "total_cost": total_cost,
        "avg_trace_latency_ms": avg_trace_latency_ms,
        "p95_trace_latency_ms": p95_trace_latency_ms,
        "slowest_traces": sorted(
            traces,
            key=lambda item: item.get("duration_ms") or 0,
            reverse=True,
        )[:5],
    }


def build_tool_metrics(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Aggregate Langfuse observations into tool usage and failure metrics."""
    observations = _with_inferred_tool_names(raw_data)
    tool_observations = [obs for obs in observations if _is_tool_observation(obs)]
    by_name: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "tool_name": "",
            "call_count": 0,
            "error_count": 0,
            "avg_latency_ms": None,
            "p95_latency_ms": None,
            "_latencies": [],
        }
    )

    for observation in tool_observations:
        name = observation.get("name") or "unknown"
        bucket = by_name[name]
        bucket["tool_name"] = name
        bucket["call_count"] += 1
        if _is_error_observation(observation):
            bucket["error_count"] += 1
        latency = observation.get("duration_ms")
        if isinstance(latency, (int, float)):
            bucket["_latencies"].append(latency)

    tools = []
    for bucket in by_name.values():
        latencies = bucket.pop("_latencies")
        bucket["avg_latency_ms"] = _avg_number(latencies)
        bucket["p95_latency_ms"] = _percentile(latencies, 95)
        tools.append(bucket)

    tools.sort(key=lambda item: item["call_count"], reverse=True)

    return {
        "tool_call_count": len(tool_observations),
        "tool_error_count": sum(1 for obs in tool_observations if _is_error_observation(obs)),
        "tools": tools,
        "recent_tool_calls": tool_observations[:20],
    }


def build_model_metrics(raw_data: dict[str, Any]) -> dict[str, Any]:
    """Aggregate Langfuse generations into model token, cost, and latency metrics."""
    observations = raw_data.get("observations") or []
    llm_observations = [obs for obs in observations if _is_llm_observation(obs)]
    by_model: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "model": "",
            "call_count": 0,
            "error_count": 0,
            "avg_latency_ms": None,
            "p95_latency_ms": None,
            "total_cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "usage_details": {},
            "_latencies": [],
        }
    )

    for observation in llm_observations:
        model = observation.get("model") or "unknown"
        bucket = by_model[model]
        bucket["model"] = model
        bucket["call_count"] += 1
        if _is_error_observation(observation):
            bucket["error_count"] += 1
        latency = observation.get("duration_ms")
        if isinstance(latency, (int, float)):
            bucket["_latencies"].append(latency)
        bucket["total_cost"] += _coerce_float(observation.get("cost"))
        usage = observation.get("usage") or {}
        input_tokens = _extract_usage_number(usage, "input")
        output_tokens = _extract_usage_number(usage, "output")
        total_tokens = _extract_usage_number(usage, "total")
        bucket["input_tokens"] += input_tokens
        bucket["output_tokens"] += output_tokens
        bucket["total_tokens"] += total_tokens or input_tokens + output_tokens
        _merge_usage_details(bucket["usage_details"], usage)

    models = []
    for bucket in by_model.values():
        latencies = bucket.pop("_latencies")
        bucket["avg_latency_ms"] = _avg_number(latencies)
        bucket["p95_latency_ms"] = _percentile(latencies, 95)
        bucket["total_cost"] = round(bucket["total_cost"], 8)
        models.append(bucket)

    models.sort(key=lambda item: item["call_count"], reverse=True)
    return {
        "llm_call_count": len(llm_observations),
        "llm_error_count": sum(1 for obs in llm_observations if _is_error_observation(obs)),
        "models": models,
    }


def build_latency_metrics(raw_data: dict[str, Any]) -> dict[str, Any]:
    traces = raw_data.get("traces") or []
    observations = raw_data.get("observations") or []
    llm_observations = [obs for obs in observations if _is_llm_observation(obs)]
    tool_observations = [
        obs for obs in _with_inferred_tool_names(raw_data) if _is_tool_observation(obs)
    ]

    return {
        "avg_trace_latency_ms": _avg_number(trace.get("duration_ms") for trace in traces),
        "p95_trace_latency_ms": _percentile([trace.get("duration_ms") for trace in traces], 95),
        "avg_llm_latency_ms": _avg_number(obs.get("duration_ms") for obs in llm_observations),
        "p95_llm_latency_ms": _percentile([obs.get("duration_ms") for obs in llm_observations], 95),
        "avg_tool_latency_ms": _avg_number(obs.get("duration_ms") for obs in tool_observations),
        "p95_tool_latency_ms": _percentile([obs.get("duration_ms") for obs in tool_observations], 95),
        "slowest_traces": sorted(
            traces,
            key=lambda item: item.get("duration_ms") or 0,
            reverse=True,
        )[:5],
        "slowest_observations": sorted(
            observations,
            key=lambda item: item.get("duration_ms") or 0,
            reverse=True,
        )[:10],
    }


def build_cost_metrics(raw_data: dict[str, Any]) -> dict[str, Any]:
    traces = raw_data.get("traces") or []
    model_metrics = build_model_metrics(raw_data)
    total_cost = _sum_number(trace.get("total_cost") for trace in traces)
    total_tokens = sum(model.get("total_tokens") or 0 for model in model_metrics["models"])
    input_tokens = sum(model.get("input_tokens") or 0 for model in model_metrics["models"])
    output_tokens = sum(model.get("output_tokens") or 0 for model in model_metrics["models"])
    trace_count = len(traces)

    return {
        "total_cost": total_cost,
        "avg_cost_per_trace": round(total_cost / trace_count, 8) if trace_count else None,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "avg_tokens_per_trace": round(total_tokens / trace_count, 2) if trace_count else None,
        "models": model_metrics["models"],
        "cost_note": (
            "Cost may be 0 when Langfuse has no pricing metadata for the configured model."
            if total_cost == 0
            else ""
        ),
    }


def _is_llm_observation(observation: dict[str, Any]) -> bool:
    obs_type = str(observation.get("type") or "").lower()
    return obs_type in {"generation", "llm"}


def _is_tool_observation(observation: dict[str, Any]) -> bool:
    return str(observation.get("type") or "").lower() == "tool"


def _is_error_observation(observation: dict[str, Any]) -> bool:
    return str(observation.get("level") or "").upper() == "ERROR"


def _sum_number(values) -> float:
    total = 0.0
    for value in values:
        try:
            if value is not None:
                total += float(value)
        except (TypeError, ValueError):
            continue
    return round(total, 8)


def _coerce_float(value) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _avg_number(values):
    numbers = []
    for value in values:
        try:
            if value is not None:
                numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return None
    return round(sum(numbers) / len(numbers), 2)


def _percentile(values, percentile: int):
    numbers = []
    for value in values:
        try:
            if value is not None:
                numbers.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numbers:
        return None
    numbers.sort()
    index = round((len(numbers) - 1) * percentile / 100)
    return round(numbers[index], 2)


def _extract_usage_number(usage: dict[str, Any], kind: str) -> int:
    if not isinstance(usage, dict):
        return 0
    candidates = {
        "input": ("input", "input_tokens", "inputTokens", "prompt_tokens", "promptTokens"),
        "output": ("output", "output_tokens", "outputTokens", "completion_tokens", "completionTokens"),
        "total": ("total", "total_tokens", "totalTokens"),
    }[kind]
    for key in candidates:
        value = usage.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _merge_usage_details(target: dict[str, int], usage: dict[str, Any]) -> None:
    if not isinstance(usage, dict):
        return

    for key, value in usage.items():
        number = _coerce_int(value)
        if number is None:
            continue
        normalized_key = _normalize_usage_detail_key(key)
        target[normalized_key] = target.get(normalized_key, 0) + number


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_usage_detail_key(key: Any) -> str:
    text = str(key or "").strip()
    aliases = {
        "prompt_cache_hit_tokens": "cache_hit_tokens",
        "cache_read_input_tokens": "cache_hit_tokens",
        "cached_tokens": "cache_hit_tokens",
        "input_cached_tokens": "cache_hit_tokens",
        "prompt_cache_miss_tokens": "cache_miss_tokens",
        "cache_creation_input_tokens": "cache_miss_tokens",
        "input_tokens": "input_tokens",
        "input": "input_tokens",
        "prompt_tokens": "input_tokens",
        "output_tokens": "output_tokens",
        "output": "output_tokens",
        "completion_tokens": "output_tokens",
        "total_tokens": "total_tokens",
        "total": "total_tokens",
    }
    return aliases.get(text, text)


def _with_inferred_tool_names(raw_data: dict[str, Any]) -> list[dict[str, Any]]:
    observations = [dict(obs) for obs in (raw_data.get("observations") or [])]
    traces = raw_data.get("traces") or []
    tool_names_by_trace = {
        trace.get("trace_id"): list(trace.get("tool_names") or [])
        for trace in traces
        if trace.get("trace_id")
    }
    used_by_trace: dict[str, int] = defaultdict(int)

    for observation in observations:
        if not _is_tool_observation(observation):
            continue
        if observation.get("name"):
            continue
        trace_id = observation.get("trace_id")
        names = tool_names_by_trace.get(trace_id) or []
        index = used_by_trace[trace_id]
        observation["name"] = names[index] if index < len(names) else "unknown"
        used_by_trace[trace_id] += 1
    return observations

"""Flask routes for ProView monitoring dashboards.

Phase 1 provides route factory placeholders only. These routes are not wired
into app.py yet, so adding the module has no runtime impact.
"""
from __future__ import annotations

import inspect
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from .langfuse_client import LangfuseMonitoringClient
from .langfuse_metrics import (
    build_cost_metrics,
    build_latency_metrics,
    build_model_metrics,
    build_overview_metrics,
    build_tool_metrics,
)
from .schemas import TimeRange, monitoring_response

monitoring_bp = Blueprint("monitoring", __name__, url_prefix="/api/monitoring")
_data_client_provider = None

MONITORING_DIAGNOSTIC_LLM_ENABLED_ENV = "PROVIEW_MONITORING_DIAGNOSTIC_LLM_ENABLED"
MONITORING_DIAGNOSTIC_LLM_TIMEOUT_ENV = "PROVIEW_MONITORING_DIAGNOSTIC_LLM_TIMEOUT_SECONDS"
MONITORING_DIAGNOSTIC_LLM_MODEL_ENV = "PROVIEW_MONITORING_DIAGNOSTIC_LLM_MODEL"
MONITORING_DIAGNOSTIC_LLM_API_KEY_ENV = "PROVIEW_MONITORING_DIAGNOSTIC_LLM_API_KEY"
MONITORING_DIAGNOSTIC_LLM_BASE_URL_ENV = "PROVIEW_MONITORING_DIAGNOSTIC_LLM_BASE_URL"
MONITORING_DIAGNOSTIC_DEFAULT_TIMEOUT_SECONDS = 2.0
MONITORING_DIAGNOSTIC_MAX_PROMPT_CHARS = 6000

_DIAGNOSTIC_AREAS = {
    "evaluation",
    "rag",
    "report_generation",
    "context_compaction",
    "tracing",
}
_DIAGNOSTIC_SEVERITIES = {"info", "warning", "critical"}


def set_data_client_provider(provider) -> None:
    global _data_client_provider
    _data_client_provider = provider


@monitoring_bp.get("/status")
def monitoring_status():
    client = LangfuseMonitoringClient()
    status = client.status()
    return jsonify(
        monitoring_response(
            configured=status.configured,
            available=status.available,
            data={"enabled": client.config.enabled},
            message=status.message,
        )
    )


@monitoring_bp.get("/traces/recent")
def monitoring_recent_traces():
    client = LangfuseMonitoringClient()
    hours = _get_int_arg("hours", client.config.default_hours)
    limit = _get_int_arg("limit", 50)
    status = client.status()
    if not status.available:
        return jsonify(
            monitoring_response(
                configured=status.configured,
                available=False,
                data=[],
                time_range=_build_time_range(hours),
                message=status.message,
            )
        )

    try:
        traces = client.fetch_recent_traces(hours=hours, limit=limit)
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data={"traces": traces},
                time_range=_build_time_range(hours),
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data={"traces": []},
                time_range=_build_time_range(hours),
                message=str(exc),
            )
        ), 502


@monitoring_bp.get("/overview")
def monitoring_overview():
    client = LangfuseMonitoringClient()
    hours = _get_int_arg("hours", client.config.default_hours)
    limit = _get_int_arg("limit", 100)
    status = client.status()
    if not status.available:
        return jsonify(
            monitoring_response(
                configured=status.configured,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=status.message,
            )
        )

    try:
        raw_data = _fetch_recent_monitoring_data(client, hours=hours, limit=limit)
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=build_overview_metrics(raw_data),
                time_range=_build_time_range(hours),
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
            )
        ), 502


@monitoring_bp.get("/tools")
def monitoring_tools():
    client = LangfuseMonitoringClient()
    hours = _get_int_arg("hours", client.config.default_hours)
    limit = _get_int_arg("limit", 100)
    status = client.status()
    if not status.available:
        return jsonify(
            monitoring_response(
                configured=status.configured,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=status.message,
            )
        )

    try:
        raw_data = _fetch_recent_monitoring_data(client, hours=hours, limit=limit)
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=build_tool_metrics(raw_data),
                time_range=_build_time_range(hours),
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
            )
        ), 502


@monitoring_bp.get("/models")
def monitoring_models():
    return _monitoring_metric_response(build_model_metrics)


@monitoring_bp.get("/latency")
def monitoring_latency():
    return _monitoring_metric_response(build_latency_metrics)


@monitoring_bp.get("/costs")
def monitoring_costs():
    return _monitoring_metric_response(build_cost_metrics)


@monitoring_bp.get("/health-summary")
def monitoring_health_summary():
    hours = _get_int_arg("hours", 24)
    limit = _get_int_arg("limit", 100)
    time_range = _build_time_range(hours)
    data, configured, available, message = _collect_health_summary(hours=hours, limit=limit)
    return jsonify(
        monitoring_response(
            configured=configured,
            available=available,
            data=data,
            time_range=time_range,
            message=message,
            source="monitoring_health",
        )
    )


@monitoring_bp.get("/diagnostic-summary")
def monitoring_diagnostic_summary():
    hours = _get_int_arg("hours", 24)
    limit = _get_int_arg("limit", 100)
    time_range = _build_time_range(hours)
    health_summary, _, health_available, health_message = _collect_health_summary(
        hours=hours,
        limit=limit,
    )
    data, diagnostic_configured, diagnostic_message = _build_monitoring_diagnostic_summary(
        health_summary,
    )
    message = diagnostic_message or health_message
    return jsonify(
        monitoring_response(
            configured=diagnostic_configured,
            available=health_available,
            data=data,
            time_range=time_range,
            message=message,
            source="monitoring_diagnostic",
        )
    )


@monitoring_bp.get("/evaluation-coverage")
def monitoring_evaluation_coverage():
    client = _get_data_client()
    hours = _get_int_arg("hours", 24)
    limit = _get_int_arg("limit", 100)
    if not client or not hasattr(client, "get_evaluation_coverage_metrics"):
        return jsonify(
            monitoring_response(
                configured=False,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message="Structured evaluation coverage metrics are unavailable",
                source="database",
            )
        )

    try:
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=client.get_evaluation_coverage_metrics(hours=hours, limit=limit),
                time_range=_build_time_range(hours),
                source="database",
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
                source="database",
            )
        ), 502


@monitoring_bp.get("/context-compaction")
def monitoring_context_compaction():
    client = _get_data_client()
    hours = _get_int_arg("hours", 24)
    limit = _get_int_arg("limit", 100)
    if not client or not hasattr(client, "get_context_compaction_metrics"):
        return jsonify(
            monitoring_response(
                configured=False,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message="Context compaction metrics are unavailable",
                source="database",
            )
        )

    try:
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=client.get_context_compaction_metrics(hours=hours, limit=limit),
                time_range=_build_time_range(hours),
                source="database",
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
                source="database",
            )
        ), 502


@monitoring_bp.get("/agent-events/rollup")
def monitoring_agent_event_rollup():
    client = _get_data_client()
    hours = _get_int_arg("hours", 24)
    limit = _get_int_arg("limit", 100)
    if not client or not hasattr(client, "get_agent_event_rollup_metrics"):
        return jsonify(
            monitoring_response(
                configured=False,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message="Agent event rollup metrics are unavailable",
                source="database",
            )
        )

    try:
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=client.get_agent_event_rollup_metrics(hours=hours, limit=limit),
                time_range=_build_time_range(hours),
                source="database",
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
                source="database",
            )
        ), 502


@monitoring_bp.get("/report-generation")
def monitoring_report_generation():
    client = _get_data_client()
    hours = _get_int_arg("hours", 24)
    limit = _get_int_arg("limit", 100)
    if not client or not hasattr(client, "get_report_generation_metrics"):
        return jsonify(
            monitoring_response(
                configured=False,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message="Report generation metrics are unavailable",
                source="database",
            )
        )

    try:
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=client.get_report_generation_metrics(hours=hours, limit=limit),
                time_range=_build_time_range(hours),
                source="database",
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
                source="database",
            )
        ), 502


@monitoring_bp.get("/rag-retrieval")
def monitoring_rag_retrieval():
    client = _get_data_client()
    hours = _get_int_arg("hours", 24)
    limit = _get_int_arg("limit", 100)
    if not client or not hasattr(client, "get_rag_retrieval_metrics"):
        return jsonify(
            monitoring_response(
                configured=False,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message="RAG retrieval metrics are unavailable",
                source="database",
            )
        )

    try:
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=client.get_rag_retrieval_metrics(hours=hours, limit=limit),
                time_range=_build_time_range(hours),
                source="database",
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
                source="database",
            )
        ), 502


@monitoring_bp.get("/traces/<trace_id>")
def monitoring_trace_detail(trace_id: str):
    client = LangfuseMonitoringClient()
    status = client.status()
    if not status.available:
        return jsonify(
            monitoring_response(
                configured=status.configured,
                available=False,
                data=None,
                message=status.message,
            )
        )

    try:
        detail = client.fetch_trace_detail(trace_id)
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=detail,
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                message=str(exc),
            )
        ), 502


def _get_int_arg(name: str, default: int) -> int:
    raw = request.args.get(name, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _build_time_range(hours: int) -> TimeRange:
    end_time = datetime.now(timezone.utc).replace(microsecond=0)
    start_time = end_time - timedelta(hours=max(1, hours))
    return TimeRange(start=start_time.isoformat(), end=end_time.isoformat())


def _get_data_client():
    if not _data_client_provider:
        return None
    try:
        return _data_client_provider()
    except Exception:
        return None


def _fetch_recent_monitoring_data(
    client: LangfuseMonitoringClient,
    *,
    hours: int,
    limit: int,
) -> dict:
    return {
        "traces": client.fetch_recent_traces(hours=hours, limit=limit),
        "observations": client.fetch_recent_observations(hours=hours, limit=limit),
    }


def _collect_health_summary(*, hours: int, limit: int) -> tuple[dict, bool, bool, str]:
    langfuse_status = LangfuseMonitoringClient().status()
    data_client = _get_data_client()

    if (
        not data_client
        or not hasattr(data_client, "get_evaluation_coverage_metrics")
        or not hasattr(data_client, "get_context_compaction_metrics")
    ):
        data = _build_health_summary(
            langfuse_status=langfuse_status,
            evaluation_metrics=None,
            context_metrics=None,
            agent_event_metrics=None,
            report_metrics=None,
            rag_metrics=None,
            database_available=False,
        )
        return data, False, False, "Structured monitoring metrics are unavailable"

    metric_errors = []
    evaluation_metrics = None
    context_metrics = None
    agent_event_metrics = None
    report_metrics = None
    rag_metrics = None
    try:
        evaluation_metrics = data_client.get_evaluation_coverage_metrics(
            hours=hours,
            limit=limit,
        )
    except Exception as exc:
        metric_errors.append(("evaluation_metrics_unavailable", str(exc)))

    try:
        context_metrics = data_client.get_context_compaction_metrics(
            hours=hours,
            limit=limit,
        )
    except Exception as exc:
        metric_errors.append(("context_compaction_metrics_unavailable", str(exc)))

    if hasattr(data_client, "get_agent_event_rollup_metrics"):
        try:
            agent_event_metrics = data_client.get_agent_event_rollup_metrics(
                hours=hours,
                limit=limit,
            )
        except Exception as exc:
            metric_errors.append(("agent_event_rollup_metrics_unavailable", str(exc)))

    if hasattr(data_client, "get_report_generation_metrics"):
        try:
            report_metrics = data_client.get_report_generation_metrics(
                hours=hours,
                limit=limit,
            )
        except Exception as exc:
            metric_errors.append(("report_generation_metrics_unavailable", str(exc)))

    if hasattr(data_client, "get_rag_retrieval_metrics"):
        try:
            rag_metrics = data_client.get_rag_retrieval_metrics(
                hours=hours,
                limit=limit,
            )
        except Exception as exc:
            metric_errors.append(("rag_retrieval_metrics_unavailable", str(exc)))

    data = _build_health_summary(
        langfuse_status=langfuse_status,
        evaluation_metrics=evaluation_metrics,
        context_metrics=context_metrics,
        agent_event_metrics=agent_event_metrics,
        report_metrics=report_metrics,
        rag_metrics=rag_metrics,
        database_available=True,
        metric_errors=metric_errors,
    )
    return data, True, not metric_errors, "; ".join(message for _, message in metric_errors)


def _build_health_summary(
    *,
    langfuse_status,
    evaluation_metrics,
    context_metrics,
    agent_event_metrics,
    report_metrics,
    rag_metrics,
    database_available: bool,
    metric_errors=None,
) -> dict:
    metric_errors = metric_errors or []
    alerts = []

    if not database_available:
        alerts.append(
            _health_alert(
                "error",
                "database_metrics_unavailable",
                "Structured monitoring metrics are unavailable",
            )
        )

    for code, message in metric_errors:
        alerts.append(_health_alert("warning", code, message or "Monitoring metrics are unavailable"))

    if langfuse_status.configured and not langfuse_status.available:
        alerts.append(
            _health_alert(
                "warning",
                "langfuse_unavailable",
                "Langfuse is configured but unavailable",
            )
        )

    evaluation_summary = (evaluation_metrics or {}).get("summary") or {}
    evaluation = _summarize_evaluation_health(evaluation_summary)
    answered_turn_count = _safe_int(evaluation_summary.get("answered_turn_count"), default=0)
    if evaluation["failure_rate"] is not None and evaluation["failure_rate"] >= 0.2:
        alerts.append(
            _health_alert(
                "warning",
                "evaluation_failure_rate_high",
                "Evaluation failure rate is above threshold",
            )
        )
    if (
        answered_turn_count > 0
        and evaluation["coverage_rate"] is not None
        and evaluation["coverage_rate"] < 0.7
    ):
        alerts.append(
            _health_alert(
                "warning",
                "evaluation_coverage_rate_low",
                "Evaluation coverage rate is below threshold",
            )
        )

    context_summary = (context_metrics or {}).get("summary") or {}
    context_compaction = _summarize_context_compaction_health(context_summary)
    if (
        context_compaction["context_summary_failure_event_count"]
        > context_compaction["context_compacted_event_count"]
    ):
        alerts.append(
            _health_alert(
                "warning",
                "context_summary_failures_high",
                "Context summary failures exceed context compaction events",
            )
        )

    agent_events = _summarize_agent_event_health(agent_event_metrics or {})
    if agent_events["failure_event_count"] > 0:
        alerts.append(
            _health_alert(
                "warning",
                "agent_event_failures_present",
                "Agent failure events were recorded in the selected window",
            )
        )

    report_generation = _summarize_report_generation_health(report_metrics or {})
    if (
        report_generation["failure_count"] > 0
        and report_generation["failure_count"] > report_generation["success_count"]
    ):
        alerts.append(
            _health_alert(
                "warning",
                "report_generation_failures_high",
                "Report generation failures exceed successful reports",
            )
        )

    rag_retrieval = _summarize_rag_retrieval_health(rag_metrics or {})
    rag_attempt_count = rag_retrieval["success_count"] + rag_retrieval["miss_count"] + rag_retrieval["failure_count"]
    if (
        rag_retrieval["failure_count"] > 0
        and rag_retrieval["failure_count"] > rag_retrieval["success_count"]
    ):
        alerts.append(
            _health_alert(
                "warning",
                "rag_retrieval_failures_high",
                "RAG retrieval failures exceed successful retrievals",
            )
        )
    if (
        rag_attempt_count > 0
        and rag_retrieval["miss_count"] > rag_retrieval["success_count"]
    ):
        alerts.append(
            _health_alert(
                "warning",
                "rag_retrieval_misses_high",
                "RAG retrieval misses exceed successful retrievals",
            )
        )

    if not database_available:
        status = "unavailable"
    elif alerts:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "langfuse": {
            "configured": bool(langfuse_status.configured),
            "available": bool(langfuse_status.available),
            "message": langfuse_status.message or "",
        },
        "evaluation": evaluation,
        "context_compaction": context_compaction,
        "agent_events": agent_events,
        "report_generation": report_generation,
        "rag_retrieval": rag_retrieval,
        "alerts": alerts,
    }


def _build_monitoring_diagnostic_summary(health_summary: dict) -> tuple[dict, bool, str]:
    fallback = _build_deterministic_diagnostic_summary(health_summary)
    if not _is_truthy_env(os.getenv(MONITORING_DIAGNOSTIC_LLM_ENABLED_ENV)):
        return fallback, False, "Monitoring diagnostic LLM is disabled; deterministic fallback returned"

    llm_client, config_message = _build_monitoring_diagnostic_llm_client()
    if not llm_client:
        return fallback, False, config_message

    try:
        messages = _build_monitoring_diagnostic_messages(health_summary)
        raw = _generate_monitoring_diagnostic_with_timeout(
            llm_client,
            messages,
            _monitoring_diagnostic_timeout_seconds(),
        )
        normalized = _normalize_monitoring_llm_diagnostic(raw, health_summary)
        if normalized:
            return normalized, True, ""
    except TimeoutError:
        return fallback, True, "Monitoring diagnostic LLM timed out; deterministic fallback returned"
    except Exception as exc:
        return fallback, True, f"Monitoring diagnostic LLM failed: {str(exc)[:160]}"
    return fallback, True, "Monitoring diagnostic LLM returned invalid JSON; deterministic fallback returned"


def _build_monitoring_diagnostic_llm_client():
    model = _read_env(MONITORING_DIAGNOSTIC_LLM_MODEL_ENV)
    api_key = _read_env(MONITORING_DIAGNOSTIC_LLM_API_KEY_ENV) or _read_env("DEEPSEEK_API_KEY")
    base_url = _read_env(MONITORING_DIAGNOSTIC_LLM_BASE_URL_ENV) or _read_env(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com/v1",
    )
    if not model:
        return None, "Monitoring diagnostic LLM model is missing; deterministic fallback returned"
    if not api_key or not base_url:
        return None, "Monitoring diagnostic LLM API config is missing; deterministic fallback returned"
    try:
        from core.llm_client import OpenAICompatibleClient
    except Exception as exc:
        return None, f"Monitoring diagnostic LLM client is unavailable: {str(exc)[:160]}"
    return OpenAICompatibleClient(model=model, api_key=api_key, base_url=base_url), ""


def _build_monitoring_diagnostic_messages(health_summary: dict) -> list:
    source_json = json.dumps(health_summary or {}, ensure_ascii=False, separators=(",", ":"))
    if len(source_json) > MONITORING_DIAGNOSTIC_MAX_PROMPT_CHARS:
        source_json = source_json[:MONITORING_DIAGNOSTIC_MAX_PROMPT_CHARS]
    return [
        {
            "role": "system",
            "content": (
                "You are the read-only ProView Monitoring Diagnostic Agent. "
                "Use only aggregate monitoring metrics from the user message. "
                "Do not infer or request candidate answers, report text, evidence, suggestions, "
                "rubrics, hidden memory, checkpoint payloads, RAG queries, resumes, JD text, "
                "question text, or HR scripts. Do not propose automatic changes. "
                "Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create a concise diagnostic summary for a human operator. "
                "Return exactly this JSON shape: "
                '{"status":"ok|degraded|unavailable","diagnosis":[{"area":"evaluation|rag|report_generation|context_compaction|tracing","severity":"info|warning|critical","summary":"short diagnosis","suggested_next_step":"manual next step"}]}. '
                f"Aggregate health summary:\n{source_json}"
            ),
        },
    ]


def _generate_monitoring_diagnostic_with_timeout(llm_client, messages: list, timeout_seconds: float) -> str:
    result_box = {"value": "", "error": None}

    def _target() -> None:
        try:
            result_box["value"] = _call_monitoring_diagnostic_llm(
                llm_client,
                messages,
                timeout_seconds,
            )
        except Exception as exc:
            result_box["error"] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=max(0.01, timeout_seconds))
    if worker.is_alive():
        raise TimeoutError("monitoring diagnostic LLM timed out")
    if result_box["error"]:
        raise result_box["error"]
    return str(result_box["value"] or "")


def _call_monitoring_diagnostic_llm(llm_client, messages: list, timeout_seconds: float) -> str:
    generate = getattr(llm_client, "generate")
    try:
        signature = inspect.signature(generate)
        parameters = signature.parameters.values()
        accepts_timeout = any(
            parameter.name == "timeout" or parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )
    except Exception:
        accepts_timeout = False
    if accepts_timeout:
        return generate(messages, timeout=timeout_seconds)
    return generate(messages)


def _normalize_monitoring_llm_diagnostic(raw, health_summary: dict) -> dict:
    parsed = _parse_json_object(raw)
    if not parsed:
        return {}
    status = str(parsed.get("status") or health_summary.get("status") or "unavailable").strip().lower()
    if status not in {"ok", "degraded", "unavailable"}:
        status = str(health_summary.get("status") or "unavailable")

    diagnosis_rows = parsed.get("diagnosis")
    if not isinstance(diagnosis_rows, list):
        diagnosis_rows = parsed.get("diagnoses")
    if not isinstance(diagnosis_rows, list):
        return {}

    diagnosis = []
    for row in diagnosis_rows:
        item = _normalize_diagnostic_item(row)
        if item:
            diagnosis.append(item)
        if len(diagnosis) >= 8:
            break
    if not diagnosis:
        return {}
    return {
        "status": status,
        "diagnosis": diagnosis,
        "fallback_used": False,
    }


def _normalize_diagnostic_item(row) -> dict:
    if not isinstance(row, dict):
        return {}
    area = str(row.get("area") or "").strip().lower()
    if area not in _DIAGNOSTIC_AREAS:
        area = _diagnostic_area_for_code(str(row.get("code") or row.get("summary") or ""))
    severity = str(row.get("severity") or "").strip().lower()
    if severity not in _DIAGNOSTIC_SEVERITIES:
        severity = "warning"
    summary = _diagnostic_text(row.get("summary"), limit=220)
    suggested_next_step = _diagnostic_text(
        row.get("suggested_next_step") or row.get("next_step") or row.get("recommendation"),
        limit=260,
    )
    if not summary or not suggested_next_step:
        return {}
    return {
        "area": area,
        "severity": severity,
        "summary": summary,
        "suggested_next_step": suggested_next_step,
    }


def _build_deterministic_diagnostic_summary(health_summary: dict) -> dict:
    alerts = health_summary.get("alerts") if isinstance(health_summary, dict) else []
    diagnosis = []
    for alert in alerts or []:
        if not isinstance(alert, dict):
            continue
        code = str(alert.get("code") or "").strip()
        level = str(alert.get("level") or "").strip().lower()
        severity = "critical" if level == "error" else "warning"
        diagnosis.append(
            {
                "area": _diagnostic_area_for_code(code),
                "severity": severity,
                "summary": _diagnostic_text(alert.get("message") or code, limit=220),
                "suggested_next_step": _diagnostic_next_step_for_code(code),
            }
        )
        if len(diagnosis) >= 8:
            break

    if not diagnosis:
        diagnosis.append(
            {
                "area": "tracing",
                "severity": "info",
                "summary": "Aggregate monitoring metrics are healthy for the selected window",
                "suggested_next_step": "Continue watching health-summary, evaluation coverage, report-generation, context-compaction, and RAG retrieval counters during real sessions.",
            }
        )

    return {
        "status": str((health_summary or {}).get("status") or "unavailable"),
        "diagnosis": diagnosis,
        "fallback_used": True,
    }


def _diagnostic_area_for_code(code: str) -> str:
    text = str(code or "").lower()
    if "evaluation" in text or "turn_evaluation" in text:
        return "evaluation"
    if "rag" in text:
        return "rag"
    if "report" in text:
        return "report_generation"
    if "context" in text or "summary" in text or "compact" in text:
        return "context_compaction"
    return "tracing"


def _diagnostic_next_step_for_code(code: str) -> str:
    text = str(code or "").lower()
    if text == "evaluation_failure_rate_high":
        return "Inspect evaluator model availability, JSON parsing, and recent turn_evaluation_failed event categories."
    if text == "evaluation_coverage_rate_low":
        return "Check whether EvalObserver tasks are starting, draining, and writing turn_evaluations for answered turns."
    if text == "context_summary_failures_high":
        return "Review Summary Agent timeout/model settings; keep deterministic checkpoint fallback enabled."
    if text == "langfuse_unavailable":
        return "Verify Langfuse keys, base URL, package availability, and network access without blocking interviews."
    if text == "agent_event_failures_present":
        return "Open the agent event rollup and group failures by event_type and agent_role before inspecting raw application logs."
    if text == "report_generation_failures_high":
        return "Check final-report LLM errors and confirm structured fallback reports are still succeeding."
    if text == "rag_retrieval_failures_high":
        return "Inspect RAG service health and error_type rollups before changing knowledge-base content."
    if text == "rag_retrieval_misses_high":
        return "Review offline knowledge coverage, title aliases, and question-bank tags using privacy-safe aggregate miss signals."
    if text == "database_metrics_unavailable":
        return "Verify the structured data client and Direct SQLite monitoring helpers are available."
    if text.endswith("_metrics_unavailable"):
        return "Check the named monitoring metric helper and keep the endpoint on deterministic fallback until it recovers."
    return "Review the related aggregate monitoring endpoint and application logs; do not trigger automatic repair from diagnostics."


def _parse_json_object(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    raw_text = str(raw or "").strip()
    if not raw_text:
        return {}
    raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.IGNORECASE).strip()
    raw_text = re.sub(r"\s*```$", "", raw_text).strip()
    try:
        value = json.loads(raw_text)
        return value if isinstance(value, dict) else {}
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", raw_text)
    if not match:
        return {}
    try:
        value = json.loads(match.group())
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _diagnostic_text(value, *, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    return text[:limit]


def _monitoring_diagnostic_timeout_seconds() -> float:
    raw_value = os.getenv(MONITORING_DIAGNOSTIC_LLM_TIMEOUT_ENV, "").strip()
    if not raw_value:
        return MONITORING_DIAGNOSTIC_DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except Exception:
        return MONITORING_DIAGNOSTIC_DEFAULT_TIMEOUT_SECONDS
    if value <= 0:
        return MONITORING_DIAGNOSTIC_DEFAULT_TIMEOUT_SECONDS
    return min(value, 5.0)


def _read_env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _is_truthy_env(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _summarize_evaluation_health(summary: dict) -> dict:
    return {
        "coverage_rate": _safe_rate(summary.get("coverage_rate")),
        "failure_rate": _safe_rate(summary.get("failure_rate")),
        "evaluation_failure_event_count": _safe_int(
            summary.get("evaluation_failure_event_count"),
            default=0,
        ),
    }


def _summarize_context_compaction_health(summary: dict) -> dict:
    return {
        "context_compacted_event_count": _safe_int(
            summary.get("context_compacted_event_count"),
            default=0,
        ),
        "context_summary_failure_event_count": _safe_int(
            summary.get("context_summary_failure_event_count"),
            default=0,
        ),
        "latest_context_version": _safe_int(
            summary.get("latest_context_version"),
            default=None,
        ),
    }


def _summarize_agent_event_health(metrics: dict) -> dict:
    summary = (metrics or {}).get("summary") or {}
    failure_types = []
    for item in (metrics or {}).get("failure_event_types") or []:
        if not isinstance(item, dict):
            continue
        event_type = str(item.get("event_type") or "").strip()
        if not event_type:
            continue
        failure_types.append(
            {
                "event_type": event_type[:128],
                "count": _safe_int(item.get("count"), default=0),
                "latest_created_at": str(item.get("latest_created_at") or ""),
            }
        )
        if len(failure_types) >= 5:
            break

    return {
        "total_event_count": _safe_int(summary.get("total_event_count"), default=0),
        "failure_event_count": _safe_int(summary.get("failure_event_count"), default=0),
        "top_failure_event_types": failure_types,
    }


def _summarize_report_generation_health(metrics: dict) -> dict:
    summary = (metrics or {}).get("summary") or {}
    failure_reasons = []
    for item in (metrics or {}).get("failure_reasons") or []:
        if not isinstance(item, dict):
            continue
        reason = str(item.get("reason") or "").strip()
        if not reason:
            continue
        failure_reasons.append(
            {
                "reason": reason[:120],
                "count": _safe_int(item.get("count"), default=0),
                "latest_created_at": str(item.get("latest_created_at") or ""),
            }
        )
        if len(failure_reasons) >= 5:
            break

    return {
        "success_count": _safe_int(summary.get("success_count"), default=0),
        "failure_count": _safe_int(summary.get("failure_count"), default=0),
        "fallback_success_count": _safe_int(
            summary.get("fallback_success_count"),
            default=0,
        ),
        "success_rate": _safe_rate(summary.get("success_rate")),
        "top_failure_reasons": failure_reasons,
    }


def _summarize_rag_retrieval_health(metrics: dict) -> dict:
    summary = (metrics or {}).get("summary") or {}
    error_types = []
    for item in (metrics or {}).get("error_types") or []:
        if not isinstance(item, dict):
            continue
        error_type = str(item.get("error_type") or "").strip()
        if not error_type:
            continue
        error_types.append(
            {
                "error_type": error_type[:80],
                "count": _safe_int(item.get("count"), default=0),
                "latest_created_at": str(item.get("latest_created_at") or ""),
            }
        )
        if len(error_types) >= 5:
            break

    return {
        "success_count": _safe_int(summary.get("success_count"), default=0),
        "miss_count": _safe_int(summary.get("miss_count"), default=0),
        "failure_count": _safe_int(summary.get("failure_count"), default=0),
        "hit_rate": _safe_rate(summary.get("hit_rate")),
        "miss_rate": _safe_rate(summary.get("miss_rate")),
        "failure_rate": _safe_rate(summary.get("failure_rate")),
        "questions_count": _safe_int(summary.get("questions_count"), default=0),
        "jobs_count": _safe_int(summary.get("jobs_count"), default=0),
        "scripts_count": _safe_int(summary.get("scripts_count"), default=0),
        "top_error_types": error_types,
    }


def _health_alert(level: str, code: str, message: str) -> dict:
    return {
        "level": level,
        "code": code,
        "message": message,
    }


def _safe_rate(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value, *, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _monitoring_metric_response(builder):
    client = LangfuseMonitoringClient()
    hours = _get_int_arg("hours", client.config.default_hours)
    limit = _get_int_arg("limit", 100)
    status = client.status()
    if not status.available:
        return jsonify(
            monitoring_response(
                configured=status.configured,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=status.message,
            )
        )

    try:
        raw_data = _fetch_recent_monitoring_data(client, hours=hours, limit=limit)
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=builder(raw_data),
                time_range=_build_time_range(hours),
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=_build_time_range(hours),
                message=str(exc),
            )
        ), 502

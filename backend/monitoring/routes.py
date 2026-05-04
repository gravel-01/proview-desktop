"""Flask routes for ProView monitoring dashboards.

Phase 1 provides route factory placeholders only. These routes are not wired
into app.py yet, so adding the module has no runtime impact.
"""
from __future__ import annotations

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

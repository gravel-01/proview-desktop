"""Read-only learning signal routes for offline operator review."""
from __future__ import annotations

import inspect
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request

from monitoring.schemas import TimeRange, monitoring_response

learning_bp = Blueprint("learning", __name__, url_prefix="/api/learning")
_data_client_provider = None

LEARNING_LLM_ENABLED_ENV = "PROVIEW_LEARNING_LLM_ENABLED"
LEARNING_LLM_TIMEOUT_ENV = "PROVIEW_LEARNING_LLM_TIMEOUT_SECONDS"
LEARNING_LLM_MODEL_ENV = "PROVIEW_LEARNING_LLM_MODEL"
LEARNING_LLM_API_KEY_ENV = "PROVIEW_LEARNING_LLM_API_KEY"
LEARNING_LLM_BASE_URL_ENV = "PROVIEW_LEARNING_LLM_BASE_URL"
LEARNING_LLM_DEFAULT_TIMEOUT_SECONDS = 3.0
LEARNING_LLM_MAX_PROMPT_CHARS = 7000

_LEARNING_AREAS = {
    "question_quality",
    "rag_coverage",
    "rubric",
    "evaluator",
    "report_generation",
}
_LEARNING_SEVERITIES = {"info", "warning", "critical"}


def set_data_client_provider(provider) -> None:
    global _data_client_provider
    _data_client_provider = provider


@learning_bp.get("/signal-summary")
def learning_signal_summary():
    client = _get_data_client()
    hours = _get_int_arg("hours", 168)
    limit = _get_int_arg("limit", 200)
    time_range = _build_time_range(hours)
    if not client or not hasattr(client, "get_learning_signal_summary_metrics"):
        return jsonify(
            monitoring_response(
                configured=False,
                available=False,
                data=None,
                time_range=time_range,
                message="Learning signal summary metrics are unavailable",
                source="learning_signals",
            )
        )

    try:
        return jsonify(
            monitoring_response(
                configured=True,
                available=True,
                data=client.get_learning_signal_summary_metrics(hours=hours, limit=limit),
                time_range=time_range,
                source="learning_signals",
            )
        )
    except Exception as exc:
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=None,
                time_range=time_range,
                message=str(exc),
                source="learning_signals",
            )
        ), 502


@learning_bp.get("/suggestions")
def learning_suggestions():
    client = _get_data_client()
    hours = _get_int_arg("hours", 168)
    limit = _get_int_arg("limit", 200)
    time_range = _build_time_range(hours)
    if not client or not hasattr(client, "get_learning_signal_summary_metrics"):
        unavailable = _build_deterministic_learning_suggestions(None)
        return jsonify(
            monitoring_response(
                configured=False,
                available=False,
                data=unavailable,
                time_range=time_range,
                message="Learning signal summary metrics are unavailable",
                source="learning_suggestions",
            )
        )

    try:
        signal_summary = client.get_learning_signal_summary_metrics(hours=hours, limit=limit)
    except Exception as exc:
        unavailable = _build_deterministic_learning_suggestions(None)
        return jsonify(
            monitoring_response(
                configured=True,
                available=False,
                data=unavailable,
                time_range=time_range,
                message=str(exc),
                source="learning_suggestions",
            )
        ), 502

    data, llm_configured, message = _build_learning_suggestions(signal_summary)
    return jsonify(
        monitoring_response(
            configured=llm_configured,
            available=True,
            data=data,
            time_range=time_range,
            message=message,
            source="learning_suggestions",
        )
    )


def _build_learning_suggestions(signal_summary: dict) -> tuple[dict, bool, str]:
    fallback = _build_deterministic_learning_suggestions(signal_summary)
    if not _is_truthy_env(os.getenv(LEARNING_LLM_ENABLED_ENV)):
        return fallback, False, "Learning LLM is disabled; deterministic fallback returned"

    llm_client, config_message = _build_learning_llm_client()
    if not llm_client:
        return fallback, False, config_message

    try:
        messages = _build_learning_llm_messages(signal_summary)
        raw = _generate_learning_suggestions_with_timeout(
            llm_client,
            messages,
            _learning_llm_timeout_seconds(),
        )
        normalized = _normalize_learning_llm_suggestions(raw, signal_summary)
        if normalized:
            return normalized, True, ""
    except TimeoutError:
        return fallback, True, "Learning LLM timed out; deterministic fallback returned"
    except Exception as exc:
        return fallback, True, f"Learning LLM failed: {str(exc)[:160]}"
    return fallback, True, "Learning LLM returned invalid JSON; deterministic fallback returned"


def _build_learning_llm_client():
    model = _read_env(LEARNING_LLM_MODEL_ENV)
    api_key = _read_env(LEARNING_LLM_API_KEY_ENV) or _read_env("DEEPSEEK_API_KEY")
    base_url = _read_env(LEARNING_LLM_BASE_URL_ENV) or _read_env(
        "DEEPSEEK_BASE_URL",
        "https://api.deepseek.com/v1",
    )
    if not model:
        return None, "Learning LLM model is missing; deterministic fallback returned"
    if not api_key or not base_url:
        return None, "Learning LLM API config is missing; deterministic fallback returned"
    try:
        from core.llm_client import OpenAICompatibleClient
    except Exception as exc:
        return None, f"Learning LLM client is unavailable: {str(exc)[:160]}"
    return OpenAICompatibleClient(model=model, api_key=api_key, base_url=base_url), ""


def _build_learning_llm_messages(signal_summary: dict) -> list:
    prompt_summary = _safe_learning_signal_for_prompt(signal_summary)
    source_json = json.dumps(prompt_summary, ensure_ascii=False, separators=(",", ":"))
    if len(source_json) > LEARNING_LLM_MAX_PROMPT_CHARS:
        source_json = source_json[:LEARNING_LLM_MAX_PROMPT_CHARS]
    return [
        {
            "role": "system",
            "content": (
                "You are the read-only ProView Learning Agent. "
                "Use only the aggregate learning signal summary from the user message. "
                "Do not request, infer, or output candidate answers, question text, report text, "
                "evidence text, evaluator suggestions, rubrics, hidden memory, checkpoint payloads, "
                "RAG queries, RAG documents, resumes, JD text, or HR scripts. "
                "Do not modify prompts, rubrics, RAG, question banks, HR scripts, or storage. "
                "Every suggestion is only a candidate improvement that requires human review. "
                "Return JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create concise offline learning suggestions for a human operator. "
                "Return exactly this JSON shape: "
                '{"status":"ok|degraded|unavailable","suggestions":[{"area":"question_quality|rag_coverage|rubric|evaluator|report_generation","severity":"info|warning|critical","summary":"short learning finding","candidate_improvement":"candidate improvement to review","requires_human_review":true}],"fallback_used":false}. '
                "Use only counts, rates, categories, and alerts from this aggregate summary:\n"
                f"{source_json}"
            ),
        },
    ]


def _generate_learning_suggestions_with_timeout(llm_client, messages: list, timeout_seconds: float) -> str:
    result_box = {"value": "", "error": None}

    def _target() -> None:
        try:
            result_box["value"] = _call_learning_llm(llm_client, messages, timeout_seconds)
        except Exception as exc:
            result_box["error"] = exc

    worker = threading.Thread(target=_target, daemon=True)
    worker.start()
    worker.join(timeout=max(0.01, timeout_seconds))
    if worker.is_alive():
        raise TimeoutError("learning LLM timed out")
    if result_box["error"]:
        raise result_box["error"]
    return str(result_box["value"] or "")


def _call_learning_llm(llm_client, messages: list, timeout_seconds: float) -> str:
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


def _normalize_learning_llm_suggestions(raw, signal_summary: dict) -> dict:
    parsed = _parse_json_object(raw)
    if not parsed:
        return {}
    status = str(parsed.get("status") or (signal_summary or {}).get("status") or "unavailable").strip().lower()
    if status not in {"ok", "degraded", "unavailable"}:
        status = str((signal_summary or {}).get("status") or "unavailable")

    suggestion_rows = parsed.get("suggestions")
    if not isinstance(suggestion_rows, list):
        suggestion_rows = parsed.get("recommendations")
    if not isinstance(suggestion_rows, list):
        return {}

    suggestions = []
    for row in suggestion_rows:
        item = _normalize_learning_suggestion_item(row)
        if item:
            suggestions.append(item)
        if len(suggestions) >= 8:
            break
    if not suggestions:
        return {}
    return {
        "status": status,
        "suggestions": suggestions,
        "fallback_used": False,
    }


def _normalize_learning_suggestion_item(row) -> dict:
    if not isinstance(row, dict):
        return {}
    area = str(row.get("area") or "").strip().lower()
    if area not in _LEARNING_AREAS:
        area = _learning_area_for_code(str(row.get("code") or row.get("summary") or ""))
    severity = str(row.get("severity") or "").strip().lower()
    if severity not in _LEARNING_SEVERITIES:
        severity = "warning"
    summary = _learning_text(row.get("summary"), limit=220)
    candidate_improvement = _learning_text(
        row.get("candidate_improvement")
        or row.get("improvement")
        or row.get("recommendation")
        or row.get("suggested_next_step"),
        limit=280,
    )
    if not summary or not candidate_improvement:
        return {}
    return {
        "area": area,
        "severity": severity,
        "summary": summary,
        "candidate_improvement": candidate_improvement,
        "requires_human_review": True,
    }


def _build_deterministic_learning_suggestions(signal_summary: dict | None) -> dict:
    if not isinstance(signal_summary, dict):
        return {
            "status": "unavailable",
            "suggestions": [],
            "fallback_used": True,
        }

    suggestions = []
    for alert in signal_summary.get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        code = str(alert.get("code") or "").strip()
        suggestion = _deterministic_learning_suggestion_for_code(code, signal_summary, alert)
        if suggestion:
            suggestions.append(suggestion)
        if len(suggestions) >= 8:
            break

    if not suggestions:
        suggestions.append(
            {
                "area": "question_quality",
                "severity": "info",
                "summary": "Aggregate learning signals are healthy for the selected window.",
                "candidate_improvement": "Continue reviewing signal-summary trends after real sessions before changing prompts, rubrics, RAG content, or question banks.",
                "requires_human_review": True,
            }
        )

    return {
        "status": str(signal_summary.get("status") or "unavailable"),
        "suggestions": suggestions,
        "fallback_used": True,
    }


def _deterministic_learning_suggestion_for_code(code: str, signal_summary: dict, alert: dict) -> dict:
    severity = _learning_severity(alert.get("severity"))
    area = _learning_area_for_code(code)
    summary = _deterministic_learning_summary_for_code(code, signal_summary, alert)
    candidate_improvement = _deterministic_learning_improvement_for_code(code, signal_summary)
    if not summary or not candidate_improvement:
        return {}
    return {
        "area": area,
        "severity": severity,
        "summary": summary,
        "candidate_improvement": candidate_improvement,
        "requires_human_review": True,
    }


def _deterministic_learning_summary_for_code(code: str, signal_summary: dict, alert: dict) -> str:
    summary = signal_summary.get("summary") or {}
    if code == "learning_low_score_rate_high":
        rate = _format_rate(summary.get("low_score_rate"))
        top_dimension = _top_category(signal_summary.get("dimensions"), "low_score_count", "dimension")
        top_question_type = _top_category(signal_summary.get("question_types"), "low_score_count", "question_type")
        details = _join_nonempty([f"low-score rate {rate}", top_dimension, top_question_type])
        return f"Low-score evaluations are common in the selected window ({details})."
    if code == "learning_evidence_gap_rate_high":
        rate = _format_rate(summary.get("evidence_missing_or_short_rate"))
        top_dimension = _top_category(
            signal_summary.get("dimensions"),
            "evidence_missing_or_short_count",
            "dimension",
        )
        details = _join_nonempty([f"evidence gap rate {rate}", top_dimension])
        return f"Many evaluations have missing or short evidence ({details})."
    if code == "learning_rag_failures_present":
        failure_count = _safe_int(summary.get("rag_failure_count"))
        top_error = _top_category(
            ((signal_summary.get("rag_retrieval") or {}).get("error_types") or []),
            "count",
            "error_type",
        )
        details = _join_nonempty([f"{failure_count} failures", top_error])
        return f"RAG retrieval failures are present in aggregate counters ({details})."
    if code == "learning_rag_misses_exceed_hits":
        miss_count = _safe_int(summary.get("rag_miss_count"))
        success_count = _safe_int(summary.get("rag_success_count"))
        return f"RAG misses exceed successful retrievals ({miss_count} misses vs {success_count} hits)."
    if code == "learning_report_failures_present":
        failure_count = _safe_int(summary.get("report_failure_count"))
        top_reason = _top_category(
            ((signal_summary.get("report_generation") or {}).get("failure_reasons") or []),
            "count",
            "reason",
        )
        details = _join_nonempty([f"{failure_count} report failures", top_reason])
        return f"Final report generation failures are present ({details})."
    if code == "learning_report_fallbacks_present":
        fallback_count = _safe_int(summary.get("report_fallback_success_count"))
        return f"Fallback final reports were used {fallback_count} time(s) in the selected window."
    if code == "learning_agent_failures_present":
        failure_count = _safe_int(summary.get("agent_failure_event_count"))
        top_event = _top_category(
            ((signal_summary.get("agent_failures") or {}).get("failure_event_types") or []),
            "count",
            "event_type",
        )
        details = _join_nonempty([f"{failure_count} agent failures", top_event])
        return f"Agent failure events are present in aggregate counters ({details})."
    if code == "learning_no_structured_evaluations":
        session_count = _safe_int(summary.get("session_count"))
        return f"{session_count} session(s) are present, but no structured evaluations were found."
    return _learning_text(alert.get("message") or code, limit=220)


def _deterministic_learning_improvement_for_code(code: str, signal_summary: dict) -> str:
    if code == "learning_low_score_rate_high":
        return "Review top low-score dimensions and question-type rollups offline; prepare question-pattern or rubric candidates only after human validation."
    if code == "learning_evidence_gap_rate_high":
        return "Review evaluator evidence requirements and rubric clarity using aggregate gap rates; do not expose or reuse raw evidence text."
    if code in {"learning_rag_failures_present", "learning_rag_misses_exceed_hits"}:
        return "Review RAG service health, title aliases, safe coverage counts, and question-bank tags offline; do not copy private queries or retrieved content."
    if code in {"learning_report_failures_present", "learning_report_fallbacks_present"}:
        return "Review report-generation prompts, parser behavior, and fallback report quality with a human reviewer before changing production output."
    if code == "learning_agent_failures_present":
        return "Group failure event types by agent role and inspect application logs manually; learning suggestions must not trigger retries or automatic repair."
    if code == "learning_no_structured_evaluations":
        return "Verify EvalObserver writes turn_evaluations for answered turns before using learning signals to tune questions or rubrics."
    return "Review this aggregate learning alert manually before changing prompts, rubrics, RAG content, question banks, HR scripts, or storage."


def _learning_area_for_code(code: str) -> str:
    text = str(code or "").lower()
    if "rag" in text:
        return "rag_coverage"
    if "report" in text:
        return "report_generation"
    if "evidence" in text or "evaluation" in text or "evaluator" in text:
        return "evaluator"
    if "rubric" in text:
        return "rubric"
    if "agent" in text or "failure" in text:
        return "evaluator"
    return "question_quality"


def _safe_learning_signal_for_prompt(signal_summary: dict) -> dict:
    if not isinstance(signal_summary, dict):
        return {}
    rag = signal_summary.get("rag_retrieval") or {}
    report = signal_summary.get("report_generation") or {}
    failures = signal_summary.get("agent_failures") or {}
    return {
        "status": _learning_text(signal_summary.get("status"), limit=32),
        "summary": _project_dict(
            signal_summary.get("summary"),
            [
                "session_count",
                "turn_count",
                "question_metadata_count",
                "evaluation_count",
                "low_score_count",
                "low_score_rate",
                "evidence_missing_or_short_count",
                "evidence_missing_or_short_rate",
                "suggestion_present_count",
                "suggestion_present_rate",
                "pass_level_count",
                "question_type_count",
                "question_source_count",
                "intended_dimension_count",
                "rag_success_count",
                "rag_miss_count",
                "rag_failure_count",
                "report_success_count",
                "report_failure_count",
                "report_fallback_success_count",
                "agent_failure_event_count",
                "low_score_threshold",
                "evidence_short_threshold_chars",
            ],
        ),
        "dimensions": _project_rows(
            signal_summary.get("dimensions"),
            [
                "dimension",
                "evaluation_count",
                "average_score",
                "low_score_count",
                "low_score_rate",
                "evidence_missing_or_short_count",
                "suggestion_present_count",
            ],
        ),
        "pass_levels": _project_rows(
            signal_summary.get("pass_levels"),
            ["pass_level", "count", "latest_created_at"],
        ),
        "question_types": _project_rows(
            signal_summary.get("question_types"),
            [
                "question_type",
                "question_count",
                "evaluation_count",
                "average_score",
                "low_score_count",
                "low_score_rate",
                "evidence_missing_or_short_count",
                "suggestion_present_count",
            ],
        ),
        "question_sources": _project_rows(
            signal_summary.get("question_sources"),
            [
                "source",
                "question_count",
                "evaluation_count",
                "average_score",
                "low_score_count",
                "low_score_rate",
                "evidence_missing_or_short_count",
                "suggestion_present_count",
            ],
        ),
        "intended_dimensions": _project_rows(
            signal_summary.get("intended_dimensions"),
            ["dimension", "count", "latest_created_at"],
        ),
        "rag_retrieval": {
            "summary": _project_dict(
                rag.get("summary"),
                [
                    "total_event_count",
                    "success_count",
                    "miss_count",
                    "failure_count",
                    "hit_rate",
                    "miss_rate",
                    "failure_rate",
                    "latest_retrieval_at",
                    "jobs_count",
                    "questions_count",
                    "scripts_count",
                ],
            ),
            "stages": _project_rows(rag.get("stages"), ["stage", "count", "latest_created_at"]),
            "statuses": _project_rows(rag.get("statuses"), ["status", "count", "latest_created_at"]),
            "error_types": _project_rows(rag.get("error_types"), ["error_type", "count", "latest_created_at"]),
        },
        "report_generation": {
            "summary": _project_dict(
                report.get("summary"),
                [
                    "total_event_count",
                    "success_count",
                    "failure_count",
                    "fallback_success_count",
                    "success_rate",
                    "latest_report_event_at",
                ],
            ),
            "sources": _project_rows(report.get("sources"), ["source", "count", "latest_created_at"]),
            "failure_reasons": _project_rows(
                report.get("failure_reasons"),
                ["reason", "count", "latest_created_at"],
            ),
            "routes": _project_rows(report.get("routes"), ["route", "count", "latest_created_at"]),
        },
        "agent_failures": {
            "summary": _project_dict(
                failures.get("summary"),
                [
                    "total_event_count",
                    "failure_event_count",
                    "distinct_session_count",
                    "event_type_count",
                    "agent_role_count",
                    "latest_event_at",
                ],
            ),
            "failure_event_types": _project_rows(
                failures.get("failure_event_types"),
                ["event_type", "count", "latest_created_at"],
            ),
            "event_type_agent_role_rollups": _project_rows(
                failures.get("event_type_agent_role_rollups"),
                ["event_type", "agent_role", "count", "latest_created_at"],
            ),
        },
        "alerts": _project_rows(signal_summary.get("alerts"), ["code", "severity", "message"]),
    }


def _get_data_client():
    if not _data_client_provider:
        return None
    return _data_client_provider()


def _get_int_arg(name: str, default: int) -> int:
    value = request.args.get(name, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _build_time_range(hours: int) -> TimeRange:
    end = datetime.now(timezone.utc).replace(microsecond=0)
    start = end - timedelta(hours=hours)
    return TimeRange(start=start.isoformat(), end=end.isoformat())


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


def _learning_text(value, *, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return ""
    return text[:limit]


def _read_env(key: str, default: str = "") -> str:
    value = os.getenv(key)
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _is_truthy_env(value) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _learning_llm_timeout_seconds() -> float:
    raw_value = os.getenv(LEARNING_LLM_TIMEOUT_ENV, "").strip()
    if not raw_value:
        return LEARNING_LLM_DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except Exception:
        return LEARNING_LLM_DEFAULT_TIMEOUT_SECONDS
    if value <= 0:
        return LEARNING_LLM_DEFAULT_TIMEOUT_SECONDS
    return min(value, 5.0)


def _learning_severity(value) -> str:
    severity = str(value or "").strip().lower()
    return severity if severity in _LEARNING_SEVERITIES else "warning"


def _format_rate(value) -> str:
    try:
        if value is None:
            return "unknown"
        return f"{float(value) * 100:.1f}%"
    except Exception:
        return "unknown"


def _safe_int(value) -> int:
    try:
        return max(0, int(value or 0))
    except Exception:
        return 0


def _top_category(rows, count_key: str, label_key: str) -> str:
    best = None
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if best is None or _safe_int(row.get(count_key)) > _safe_int(best.get(count_key)):
            best = row
    if not best or _safe_int(best.get(count_key)) <= 0:
        return ""
    label = _learning_text(best.get(label_key), limit=96)
    if not label:
        return ""
    return f"top {label_key} {label} ({_safe_int(best.get(count_key))})"


def _join_nonempty(parts: list[str]) -> str:
    values = [str(part).strip() for part in parts if str(part or "").strip()]
    return ", ".join(values) if values else "no aggregate detail"


def _project_dict(source, keys: list[str]) -> dict:
    if not isinstance(source, dict):
        return {}
    projected = {}
    for key in keys:
        if key not in source:
            continue
        value = source.get(key)
        if isinstance(value, str):
            projected[key] = _learning_text(value, limit=160)
        else:
            projected[key] = value
    return projected


def _project_rows(rows, keys: list[str]) -> list[dict]:
    projected_rows = []
    for row in rows or []:
        projected = _project_dict(row, keys)
        if projected:
            projected_rows.append(projected)
        if len(projected_rows) >= 40:
            break
    return projected_rows

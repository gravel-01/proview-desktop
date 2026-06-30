"""Career planning context aggregator (phase 2).

The aggregator pulls the user's recent interview activity and latest
resume through ``data_client`` and returns a single, typed
``CareerContext`` object. The context is the long-term/short-term
memory snapshot that downstream steps use to derive profile, build
plan rows, and rank task priorities.

Design rules
------------

1. **Fail-soft per session**: if one data_client call raises, the
   session is skipped but other sessions are still processed. The
   aggregator only raises when no data_client is supplied at all.
2. **Bounded work**: ``session_limit`` and the per-session limits keep
   the aggregate cost predictable. Older / larger sessions are
   truncated.
3. **Pure dataclasses**: every nested value is a frozen dataclass. The
   aggregator is a function, not a stateful service.
4. **Source-of-truth friendly**: every list returned preserves the
   ``session_id`` / ``turn_id`` so the caller can map back to the
   original database rows.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from services.career_planning_skills import (
    DimensionStat,
    compute_dimension_stats,
    extract_resume_gap_signals,
    select_top_evidence,
    select_top_suggestions,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResumeSummary:
    has_resume: bool
    file_name: str = ""
    resume_id: int = 0
    upload_time: str = ""
    ocr_length: int = 0
    ocr_preview: str = ""
    gap_signals: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TurnEvaluationLite:
    evaluation_id: str
    session_id: str
    turn_id: str
    turn_no: int
    dimension: str
    score: int
    pass_level: str
    evidence: str
    suggestion: str
    evaluator_version: str = ""


@dataclass(frozen=True)
class QuestionMetaLite:
    question_id: str
    session_id: str
    turn_id: str
    turn_no: int
    dimensions: List[str]
    difficulty: str
    question_type: str
    source: str


@dataclass(frozen=True)
class SessionContext:
    session_id: str
    position: str
    status: str
    interview_style: str
    start_time: str
    end_time: str
    turn_count: int
    answered_turn_count: int
    evaluation_count: int
    question_metadata_count: int
    avg_score: float
    eval_strengths: str
    eval_weaknesses: str
    eval_summary: str
    top_dimensions: List[str]
    evaluations: List[TurnEvaluationLite]
    question_metadata: List[QuestionMetaLite]
    capabilities: Dict[str, bool]


@dataclass(frozen=True)
class ContextSummary:
    session_count: int
    completed_session_count: int
    turn_count: int
    answered_turn_count: int
    evaluation_count: int
    low_score_evaluation_count: int
    question_metadata_count: int
    avg_score: float
    has_resume: bool
    has_any_evidence: bool
    has_question_metadata: bool
    resume_gap_signal_count: int


@dataclass(frozen=True)
class DataFreshness:
    latest_session_id: str
    latest_session_at: str
    earliest_session_at: str


@dataclass(frozen=True)
class BuildMeta:
    built_at: str
    session_limit: int
    evaluation_limit_per_session: int
    question_meta_limit_per_session: int
    truncated_sessions: int
    data_client_kind: str
    has_turn_evaluation_capability: bool
    has_question_metadata_capability: bool
    has_turn_capability: bool


@dataclass(frozen=True)
class CareerContext:
    target_role: str
    horizon_months: int
    resume_summary: ResumeSummary
    sessions: List[SessionContext]
    summary: ContextSummary
    dimension_stats: List[DimensionStat]
    evidence_samples: List[Dict[str, Any]]
    suggestion_samples: List[Dict[str, Any]]
    data_freshness: DataFreshness
    build_meta: BuildMeta

    def is_empty(self) -> bool:
        """True when no real user data is available (no resume, no session)."""
        return not self.summary.has_resume and self.summary.completed_session_count == 0

    def has_real_evidence(self) -> bool:
        return self.summary.has_any_evidence and self.summary.evaluation_count > 0

    def to_dict(self) -> Dict[str, Any]:
        return _to_jsonable(self)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_career_context(
    data_client: Any,
    user_id: int,
    *,
    target_role: str,
    horizon_months: int = 6,
    session_limit: int = 6,
    evaluation_limit_per_session: int = 8,
    question_meta_limit_per_session: int = 12,
) -> CareerContext:
    """Build a :class:`CareerContext` for ``user_id``.

    Parameters
    ----------
    data_client
        Storage abstraction (typically :class:`DataServiceClient`). May
        be ``None`` to indicate a cold-start scenario with no data.
    user_id
        Numeric local user id. ``0`` is acceptable and treated as
        "no user data" for tests.
    target_role
        Target job position; used to refine resume gap detection.
    horizon_months
        Plan horizon; preserved on the returned context so downstream
        services can pick a reasonable task volume.
    session_limit
        Maximum number of recent sessions to inspect.
    evaluation_limit_per_session
        Maximum number of turn evaluations kept per session.
    question_meta_limit_per_session
        Maximum number of question metadata records per session.

    Returns
    -------
    CareerContext
        Always non-None. When the data client is missing or all
        downstream calls fail, the returned context reports
        ``is_empty() == True``.
    """
    if data_client is None:
        return _empty_context(
            target_role=target_role,
            horizon_months=horizon_months,
            session_limit=session_limit,
            evaluation_limit_per_session=evaluation_limit_per_session,
            question_meta_limit_per_session=question_meta_limit_per_session,
            data_client_kind="missing",
            has_turn_evaluation_capability=False,
            has_question_metadata_capability=False,
            has_turn_capability=False,
        )

    data_client_kind = _detect_data_client_kind(data_client)
    capabilities = _safe_storage_capabilities(data_client)
    has_turn = bool(capabilities.get("structured_turns", True))
    has_turn_eval = bool(capabilities.get("turn_evaluations", True))
    has_qmeta = bool(capabilities.get("question_metadata", True))

    resume_summary = _collect_resume_summary(data_client, user_id, target_role)
    sessions, truncated = _collect_sessions(
        data_client,
        user_id=user_id,
        session_limit=session_limit,
        evaluation_limit_per_session=evaluation_limit_per_session,
        question_meta_limit_per_session=question_meta_limit_per_session,
        has_turn=has_turn,
        has_turn_eval=has_turn_eval,
        has_qmeta=has_qmeta,
    )

    all_evaluations: List[Dict[str, Any]] = []
    for session in sessions:
        for evaluation in session.evaluations:
            all_evaluations.append(_evaluation_to_payload(evaluation))

    dimension_stats = compute_dimension_stats(all_evaluations)
    evidence_samples = [asdict(e) for e in select_top_evidence(all_evaluations)]
    suggestion_samples = [asdict(s) for s in select_top_suggestions(all_evaluations)]

    summary = _build_summary(sessions, resume_summary)
    freshness = _build_freshness(sessions)

    build_meta = BuildMeta(
        built_at=_utc_now(),
        session_limit=session_limit,
        evaluation_limit_per_session=evaluation_limit_per_session,
        question_meta_limit_per_session=question_meta_limit_per_session,
        truncated_sessions=truncated,
        data_client_kind=data_client_kind,
        has_turn_evaluation_capability=has_turn_eval,
        has_question_metadata_capability=has_qmeta,
        has_turn_capability=has_turn,
    )

    return CareerContext(
        target_role=target_role or "",
        horizon_months=int(horizon_months or 6),
        resume_summary=resume_summary,
        sessions=sessions,
        summary=summary,
        dimension_stats=dimension_stats,
        evidence_samples=evidence_samples,
        suggestion_samples=suggestion_samples,
        data_freshness=freshness,
        build_meta=build_meta,
    )


# ---------------------------------------------------------------------------
# Collectors
# ---------------------------------------------------------------------------

def _collect_resume_summary(data_client: Any, user_id: int, target_role: str) -> ResumeSummary:
    if not hasattr(data_client, "get_latest_resume"):
        return ResumeSummary(has_resume=False)
    try:
        resume = data_client.get_latest_resume(user_id=user_id) or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[career_context] get_latest_resume failed: %s", exc)
        return ResumeSummary(has_resume=False)

    if not resume:
        return ResumeSummary(has_resume=False)

    ocr_text = str(resume.get("ocr_result") or "")
    gap_signals = extract_resume_gap_signals(ocr_text, target_role)
    return ResumeSummary(
        has_resume=True,
        file_name=str(resume.get("file_name") or ""),
        resume_id=int(resume.get("id") or 0),
        upload_time=str(resume.get("upload_time") or ""),
        ocr_length=len(ocr_text),
        ocr_preview=_truncate(ocr_text, 400),
        gap_signals=gap_signals,
    )


def _collect_sessions(
    data_client: Any,
    *,
    user_id: int,
    session_limit: int,
    evaluation_limit_per_session: int,
    question_meta_limit_per_session: int,
    has_turn: bool,
    has_turn_eval: bool,
    has_qmeta: bool,
) -> tuple[List[SessionContext], int]:
    list_sessions = getattr(data_client, "list_sessions", None)
    if not callable(list_sessions):
        return [], 0
    try:
        raw_sessions = list_sessions(limit=session_limit, user_id=user_id) or []
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[career_context] list_sessions failed: %s", exc)
        return [], 0

    truncated = 0
    if session_limit and len(raw_sessions) > session_limit:
        truncated = len(raw_sessions) - session_limit
        raw_sessions = raw_sessions[:session_limit]

    sessions: List[SessionContext] = []
    for raw in raw_sessions:
        session_id = str(raw.get("session_id") or "").strip()
        if not session_id:
            continue
        try:
            context = _build_session_context(
                data_client,
                raw=raw,
                evaluation_limit=evaluation_limit_per_session,
                question_meta_limit=question_meta_limit_per_session,
                has_turn=has_turn,
                has_turn_eval=has_turn_eval,
                has_qmeta=has_qmeta,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[career_context] session %s skipped: %s", session_id, exc)
            continue
        if context is not None:
            sessions.append(context)

    return sessions, truncated


def _build_session_context(
    data_client: Any,
    *,
    raw: Dict[str, Any],
    evaluation_limit: int,
    question_meta_limit: int,
    has_turn: bool,
    has_turn_eval: bool,
    has_qmeta: bool,
) -> Optional[SessionContext]:
    session_id = str(raw.get("session_id") or "").strip()
    if not session_id:
        return None

    info = _safe_get_session_info(data_client, session_id) or raw
    stats = _safe_get_session_statistics(data_client, session_id) or {}

    evaluations: List[TurnEvaluationLite] = []
    if has_turn_eval and hasattr(data_client, "list_turn_evaluations"):
        raw_evaluations = _safe_list(data_client.list_turn_evaluations, session_id)
        for item in raw_evaluations[:evaluation_limit]:
            evaluations.append(
                TurnEvaluationLite(
                    evaluation_id=str(item.get("evaluation_id") or ""),
                    session_id=str(item.get("session_id") or session_id),
                    turn_id=str(item.get("turn_id") or ""),
                    turn_no=int(item.get("turn_no") or 0),
                    dimension=str(item.get("dimension") or ""),
                    score=int(item.get("score") or 0),
                    pass_level=str(item.get("pass_level") or ""),
                    evidence=_truncate(str(item.get("evidence") or ""), 240),
                    suggestion=_truncate(str(item.get("suggestion") or ""), 240),
                    evaluator_version=str(item.get("evaluator_version") or ""),
                )
            )

    question_metadata: List[QuestionMetaLite] = []
    if has_qmeta and hasattr(data_client, "list_question_metadata"):
        raw_qmeta = _safe_list(data_client.list_question_metadata, session_id)
        for item in raw_qmeta[:question_meta_limit]:
            dimensions = _extract_dimension_names(item.get("dimensions"))
            question_metadata.append(
                QuestionMetaLite(
                    question_id=str(item.get("question_id") or ""),
                    session_id=str(item.get("session_id") or session_id),
                    turn_id=str(item.get("turn_id") or ""),
                    turn_no=int(item.get("turn_no") or 0),
                    dimensions=dimensions,
                    difficulty=str(item.get("difficulty") or ""),
                    question_type=str(item.get("question_type") or ""),
                    source=str(item.get("source") or ""),
                )
            )

    turns = []
    if has_turn and hasattr(data_client, "list_interview_turns"):
        turns = _safe_list(data_client.list_interview_turns, session_id)

    answered_turn_count = sum(
        1 for turn in turns if str(turn.get("status") or "") == "answered"
    )

    avg_score = float(stats.get("avg_score") or 0)
    # Augment avg_score with structured turn evaluations if stats are stale.
    if evaluations and not avg_score:
        avg_score = sum(e.score for e in evaluations) / len(evaluations)

    return SessionContext(
        session_id=session_id,
        position=str(info.get("position") or raw.get("position") or ""),
        status=str(info.get("status") or raw.get("status") or ""),
        interview_style=str(info.get("interview_style") or raw.get("interview_style") or ""),
        start_time=str(info.get("start_time") or raw.get("start_time") or ""),
        end_time=str(info.get("end_time") or raw.get("end_time") or ""),
        turn_count=int(stats.get("turn_count") or len(turns) or 0),
        answered_turn_count=answered_turn_count,
        evaluation_count=int(stats.get("evaluation_count") or len(evaluations) or 0),
        question_metadata_count=len(question_metadata),
        avg_score=round(avg_score, 2),
        eval_strengths=str(info.get("eval_strengths") or raw.get("eval_strengths") or ""),
        eval_weaknesses=str(info.get("eval_weaknesses") or raw.get("eval_weaknesses") or ""),
        eval_summary=str(info.get("eval_summary") or raw.get("eval_summary") or ""),
        top_dimensions=_collect_top_dimensions(question_metadata),
        evaluations=evaluations,
        question_metadata=question_metadata,
        capabilities={
            "structured_turns": has_turn,
            "turn_evaluations": has_turn_eval,
            "question_metadata": has_qmeta,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_get_session_info(data_client: Any, session_id: str) -> Optional[Dict[str, Any]]:
    getter = getattr(data_client, "get_session_info", None)
    if not callable(getter):
        return None
    try:
        return getter(session_id) or None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[career_context] get_session_info(%s) failed: %s", session_id, exc)
        return None


def _safe_get_session_statistics(data_client: Any, session_id: str) -> Optional[Dict[str, Any]]:
    getter = getattr(data_client, "get_session_statistics", None)
    if not callable(getter):
        return None
    try:
        return getter(session_id) or None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "[career_context] get_session_statistics(%s) failed: %s", session_id, exc
        )
        return None


def _safe_list(fn, *args) -> List[Dict[str, Any]]:
    try:
        return list(fn(*args) or [])
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[career_context] %s failed: %s", getattr(fn, "__name__", "list"), exc)
        return []


def _extract_dimension_names(raw_dimensions: Any) -> List[str]:
    names: List[str] = []
    if not raw_dimensions:
        return names
    for item in raw_dimensions:
        if isinstance(item, dict):
            name = str(item.get("name") or "").strip()
        else:
            name = str(item or "").strip()
        if name and name not in names:
            names.append(name)
    return names


def _collect_top_dimensions(question_metadata: Sequence[QuestionMetaLite]) -> List[str]:
    counter: Dict[str, int] = {}
    for qmeta in question_metadata:
        for name in qmeta.dimensions:
            counter[name] = counter.get(name, 0) + 1
    ranked = sorted(counter.items(), key=lambda kv: kv[1], reverse=True)
    return [name for name, _ in ranked[:5]]


def _evaluation_to_payload(evaluation: TurnEvaluationLite) -> Dict[str, Any]:
    return {
        "evaluation_id": evaluation.evaluation_id,
        "session_id": evaluation.session_id,
        "turn_id": evaluation.turn_id,
        "turn_no": evaluation.turn_no,
        "dimension": evaluation.dimension,
        "score": evaluation.score,
        "pass_level": evaluation.pass_level,
        "evidence": evaluation.evidence,
        "suggestion": evaluation.suggestion,
        "evaluator_version": evaluation.evaluator_version,
    }


def _build_summary(sessions: Sequence[SessionContext], resume: ResumeSummary) -> ContextSummary:
    turn_count = sum(s.turn_count for s in sessions)
    answered = sum(s.answered_turn_count for s in sessions)
    evaluation_count = sum(s.evaluation_count for s in sessions)
    qmeta_count = sum(s.question_metadata_count for s in sessions)
    completed = sum(1 for s in sessions if s.status == "completed")

    all_scores = [
        evaluation.score
        for s in sessions
        for evaluation in s.evaluations
    ]
    low_score_count = sum(1 for score in all_scores if score < 7)
    avg_score = sum(all_scores) / len(all_scores) if all_scores else 0.0

    return ContextSummary(
        session_count=len(sessions),
        completed_session_count=completed,
        turn_count=turn_count,
        answered_turn_count=answered,
        evaluation_count=evaluation_count,
        low_score_evaluation_count=low_score_count,
        question_metadata_count=qmeta_count,
        avg_score=round(avg_score, 2),
        has_resume=resume.has_resume,
        has_any_evidence=evaluation_count > 0,
        has_question_metadata=qmeta_count > 0,
        resume_gap_signal_count=len(resume.gap_signals),
    )


def _build_freshness(sessions: Sequence[SessionContext]) -> DataFreshness:
    if not sessions:
        return DataFreshness(latest_session_id="", latest_session_at="", earliest_session_at="")
    sorted_by_time = sorted(
        sessions,
        key=lambda s: s.start_time or "",
        reverse=True,
    )
    return DataFreshness(
        latest_session_id=sorted_by_time[0].session_id,
        latest_session_at=sorted_by_time[0].start_time,
        earliest_session_at=sorted_by_time[-1].start_time,
    )


def _detect_data_client_kind(data_client: Any) -> str:
    mode = getattr(data_client, "mode", "") or ""
    if mode:
        return str(mode)
    cls = type(data_client).__name__
    if "Supabase" in cls:
        return "supabase_http"
    if "Direct" in cls:
        return "direct"
    return "unknown"


def _safe_storage_capabilities(data_client: Any) -> Dict[str, bool]:
    getter = getattr(data_client, "storage_capabilities", None)
    if not callable(getter):
        return {}
    try:
        return dict(getter() or {})
    except Exception:  # pragma: no cover - defensive
        return {}


def _empty_context(
    *,
    target_role: str,
    horizon_months: int,
    session_limit: int,
    evaluation_limit_per_session: int,
    question_meta_limit_per_session: int,
    data_client_kind: str,
    has_turn_evaluation_capability: bool,
    has_question_metadata_capability: bool,
    has_turn_capability: bool,
) -> CareerContext:
    now = _utc_now()
    empty_summary = ContextSummary(
        session_count=0,
        completed_session_count=0,
        turn_count=0,
        answered_turn_count=0,
        evaluation_count=0,
        low_score_evaluation_count=0,
        question_metadata_count=0,
        avg_score=0.0,
        has_resume=False,
        has_any_evidence=False,
        has_question_metadata=False,
        resume_gap_signal_count=0,
    )
    empty_freshness = DataFreshness(
        latest_session_id="", latest_session_at="", earliest_session_at=""
    )
    empty_meta = BuildMeta(
        built_at=now,
        session_limit=session_limit,
        evaluation_limit_per_session=evaluation_limit_per_session,
        question_meta_limit_per_session=question_meta_limit_per_session,
        truncated_sessions=0,
        data_client_kind=data_client_kind,
        has_turn_evaluation_capability=has_turn_evaluation_capability,
        has_question_metadata_capability=has_question_metadata_capability,
        has_turn_capability=has_turn_capability,
    )
    return CareerContext(
        target_role=target_role or "",
        horizon_months=int(horizon_months or 6),
        resume_summary=ResumeSummary(has_resume=False),
        sessions=[],
        summary=empty_summary,
        dimension_stats=[],
        evidence_samples=[],
        suggestion_samples=[],
        data_freshness=empty_freshness,
        build_meta=empty_meta,
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truncate(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _to_jsonable(value: Any) -> Any:
    """Best-effort dataclass -> dict serialiser for the API layer."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_jsonable(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def dumps_context(context: CareerContext) -> str:
    """JSON serialise a :class:`CareerContext` (helper for tests/storage)."""
    return json.dumps(_to_jsonable(context), ensure_ascii=False)

"""Career planning structured output schema (phase 3).

This module defines the JSON schema and Python dataclasses that the LLM
must conform to when generating a career plan. The schema is intentionally
strict so that bad outputs are caught early and trigger an automatic
fallback to the deterministic evidence-aware templates (phase 2).

Design rules
------------

1. **Dataclass-first**: every typed value is a frozen dataclass; JSON
   serialisation is derived via :func:`career_plan_structured_to_dict`.
2. **Schema-first validation**: ``CAREER_PLAN_STRUCTURED_SCHEMA`` mirrors
   the dataclass shape so we can validate LLM output before the
   downstream service touches it.
3. **Reference consistency**: :func:`validate_references` cross-checks
   ``gap_key`` / ``session_id`` / ``dimension`` against the
   :class:`CareerContext` provided by the aggregator. This enforces the
   "no fabricated evidence" anti-hallucination guardrail.
4. **Truncate/pad, do not crash**: helpers like
   :func:`normalise_milestones` clamp the LLM output to the expected
   milestone count so the rest of the pipeline always sees a valid plan.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.career_planning_skills import DIMENSION_LIBRARY


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

VALID_SEVERITY: Tuple[str, ...] = ("high", "medium", "low", "none")
VALID_TASK_TYPE: Tuple[str, ...] = ("skill_practice", "interview_prep", "project", "course")
VALID_GENERATION_MODE: Tuple[str, ...] = (
    "llm",
    "llm_fallback",
    "evidence_aware",
    "fallback",
    "empty",
)


@dataclass(frozen=True)
class ProfileDraft:
    """LLM-generated profile summary (subset of :class:`CareerProfile`)."""

    current_stage: str
    overall_score: float
    strength_tags: List[str] = field(default_factory=list)
    gap_tags: List[str] = field(default_factory=list)
    summary: str = ""
    generation_mode: str = "llm"


@dataclass(frozen=True)
class GapDraft:
    """Structured gap description."""

    key: str
    label: str
    severity: str
    dimension: str
    evidence_session_ids: List[str] = field(default_factory=list)
    evidence_quotes: List[str] = field(default_factory=list)
    recommended_action: str = ""


@dataclass(frozen=True)
class MilestoneDraft:
    """Milestone description produced by the LLM."""

    sort_order: int
    title: str
    month: int
    description: str
    success_criteria: str
    focus_gaps: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class TaskDraft:
    """Task description produced by the LLM."""

    title: str
    description: str
    task_type: str
    priority: int
    gap_key: str
    estimated_effort: str
    success_criteria: str
    source_evidence: List[Dict[str, Any]] = field(default_factory=list)
    resource_refs: List[Dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RecommendationDraft:
    """Resource / action recommendation."""

    type: str
    title: str
    reason: str
    url: str = ""


@dataclass(frozen=True)
class CareerPlanStructured:
    """Aggregate output of the LLM generator."""

    profile: ProfileDraft
    gaps: List[GapDraft]
    milestones: List[MilestoneDraft]
    tasks: List[TaskDraft]
    recommendations: List[RecommendationDraft]
    raw_model_output: str = ""
    generation_mode: str = "llm"
    model_id: str = ""
    prompt_hash: str = ""
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(frozen=True)
class GenerationOutcome:
    """Result of one :class:`CareerPlanLLMGenerator` call."""

    success: bool
    plan: Optional[CareerPlanStructured] = None
    error: str = ""
    fallback_reason: str = ""
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model_id: str = ""
    prompt_hash: str = ""
    raw_output: str = ""


# ---------------------------------------------------------------------------
# JSON Schema
# ---------------------------------------------------------------------------

CAREER_PLAN_STRUCTURED_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["profile", "gaps", "milestones", "tasks", "recommendations"],
    "properties": {
        "profile": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "current_stage",
                "overall_score",
                "gap_tags",
                "summary",
                "generation_mode",
            ],
            "properties": {
                "current_stage": {"type": "string", "maxLength": 32},
                "overall_score": {"type": "number", "minimum": 0, "maximum": 10},
                "strength_tags": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 32},
                    "maxItems": 10,
                },
                "gap_tags": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 64},
                    "maxItems": 10,
                },
                "summary": {"type": "string", "maxLength": 240},
                "generation_mode": {"enum": list(VALID_GENERATION_MODE)},
            },
        },
        "gaps": {
            "type": "array",
            "maxItems": 5,
            "items": {"$ref": "#/definitions/gap"},
        },
        "milestones": {
            "type": "array",
            "maxItems": 6,
            "items": {"$ref": "#/definitions/milestone"},
        },
        "tasks": {
            "type": "array",
            "maxItems": 24,
            "items": {"$ref": "#/definitions/task"},
        },
        "recommendations": {
            "type": "array",
            "maxItems": 3,
            "items": {"$ref": "#/definitions/recommendation"},
        },
    },
    "definitions": {
        "gap": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "key",
                "label",
                "severity",
                "dimension",
                "evidence_quotes",
                "recommended_action",
            ],
            "properties": {
                "key": {"type": "string", "maxLength": 32},
                "label": {"type": "string", "maxLength": 32},
                "severity": {"enum": list(VALID_SEVERITY)},
                "dimension": {"type": "string", "maxLength": 32},
                "evidence_session_ids": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 64},
                },
                "evidence_quotes": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {"type": "string", "maxLength": 120},
                },
                "recommended_action": {"type": "string", "maxLength": 160},
            },
        },
        "milestone": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "sort_order",
                "title",
                "month",
                "description",
                "success_criteria",
                "focus_gaps",
            ],
            "properties": {
                "sort_order": {"type": "integer", "minimum": 1, "maximum": 6},
                "title": {"type": "string", "maxLength": 32},
                "month": {"type": "integer", "minimum": 1, "maximum": 12},
                "description": {"type": "string", "maxLength": 240},
                "success_criteria": {"type": "string", "maxLength": 160},
                "focus_gaps": {
                    "type": "array",
                    "items": {"type": "string", "maxLength": 32},
                    "maxItems": 6,
                },
            },
        },
        "task": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "title",
                "description",
                "task_type",
                "priority",
                "gap_key",
                "estimated_effort",
                "success_criteria",
                "source_evidence",
            ],
            "properties": {
                "title": {"type": "string", "maxLength": 32},
                "description": {"type": "string", "maxLength": 240},
                "task_type": {"enum": list(VALID_TASK_TYPE)},
                "priority": {"type": "integer", "minimum": 1, "maximum": 5},
                "gap_key": {"type": "string", "maxLength": 32},
                "estimated_effort": {"type": "string", "maxLength": 16},
                "success_criteria": {"type": "string", "maxLength": 160},
                "source_evidence": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["session_id", "quote"],
                        "properties": {
                            "session_id": {"type": "string", "maxLength": 64},
                            "turn_no": {"type": "integer", "minimum": 0},
                            "score": {"type": "integer", "minimum": 0, "maximum": 10},
                            "quote": {"type": "string", "maxLength": 200},
                        },
                    },
                },
                "resource_refs": {
                    "type": "array",
                    "items": {"type": "object"},
                },
            },
        },
        "recommendation": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "title", "reason"],
            "properties": {
                "type": {"type": "string", "maxLength": 32},
                "title": {"type": "string", "maxLength": 64},
                "reason": {"type": "string", "maxLength": 240},
                "url": {"type": "string"},
            },
        },
    },
}


# ---------------------------------------------------------------------------
# JSON extraction (tolerant)
# ---------------------------------------------------------------------------

_FENCED_JSON = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


def extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """Pull a JSON object out of ``raw`` with progressive fallback."""
    if not raw:
        return None
    text = raw.strip()
    # 1) direct parse
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    # 2) fenced ```json ... ```
    match = _FENCED_JSON.search(text)
    if match:
        try:
            parsed = json.loads(match.group(1))
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    # 3) first '{' to last '}'
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------

def _try_import_jsonschema():
    try:
        import jsonschema  # type: ignore

        return jsonschema
    except Exception:  # pragma: no cover - defensive
        return None


def validate_with_schema(data: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate ``data`` against :data:`CAREER_PLAN_STRUCTURED_SCHEMA`.

    Returns ``(ok, reason)``. ``reason`` is empty on success and a
    human-readable message on failure.
    """
    jsonschema_mod = _try_import_jsonschema()
    if jsonschema_mod is not None:
        try:
            jsonschema_mod.validate(
                instance=data, schema=CAREER_PLAN_STRUCTURED_SCHEMA
            )
            return True, ""
        except jsonschema_mod.ValidationError as exc:  # type: ignore[attr-defined]
            return False, f"schema_invalid:{exc.message}"
        except Exception as exc:  # pragma: no cover - defensive
            return False, f"schema_error:{exc}"

    # Manual fallback: keep the contract small enough to validate by hand.
    if not isinstance(data, dict):
        return False, "schema_invalid:root_not_object"
    for key in ("profile", "gaps", "milestones", "tasks", "recommendations"):
        if key not in data:
            return False, f"schema_invalid:missing_{key}"
    profile = data.get("profile") or {}
    if not isinstance(profile, dict):
        return False, "schema_invalid:profile_not_object"
    for key in (
        "current_stage",
        "overall_score",
        "gap_tags",
        "summary",
        "generation_mode",
    ):
        if key not in profile:
            return False, f"schema_invalid:profile_missing_{key}"
    if not isinstance(profile.get("overall_score"), (int, float)):
        return False, "schema_invalid:profile_overall_score_not_number"
    if not (0 <= float(profile.get("overall_score", -1)) <= 10):
        return False, "schema_invalid:profile_overall_score_out_of_range"
    if not isinstance(profile.get("gap_tags"), list):
        return False, "schema_invalid:profile_gap_tags_not_list"
    for gap in data.get("gaps", []) or []:
        if not isinstance(gap, dict):
            return False, "schema_invalid:gap_not_object"
        if gap.get("severity") not in VALID_SEVERITY:
            return False, f"schema_invalid:gap_severity:{gap.get('severity')}"
        if not gap.get("evidence_quotes"):
            return False, "schema_invalid:gap_no_evidence"
    for task in data.get("tasks", []) or []:
        if not isinstance(task, dict):
            return False, "schema_invalid:task_not_object"
        if task.get("task_type") not in VALID_TASK_TYPE:
            return False, f"schema_invalid:task_type:{task.get('task_type')}"
        if not task.get("source_evidence"):
            return False, "schema_invalid:task_no_evidence"
    return True, ""


# ---------------------------------------------------------------------------
# Reference validation
# ---------------------------------------------------------------------------

def validate_references(plan: CareerPlanStructured, context: Any) -> Tuple[bool, str]:
    """Cross-check gap keys / session ids / dimensions against the context.

    ``context`` is duck-typed (typically :class:`CareerContext`) so this
    helper does not require importing the aggregator module.
    """
    valid_session_ids = set()
    valid_dimensions = set(DIMENSION_LIBRARY)
    try:
        for session in getattr(context, "sessions", []) or []:
            sid = str(getattr(session, "session_id", "") or "").strip()
            if sid:
                valid_session_ids.add(sid)
    except Exception:
        pass

    valid_gap_keys: set[str] = set()
    for gap in plan.gaps:
        if gap.dimension and gap.dimension not in valid_dimensions:
            return False, f"reference_invalid:dimension_unknown:{gap.dimension}"
        valid_gap_keys.add(gap.key)
        for sid in gap.evidence_session_ids or []:
            if valid_session_ids and sid not in valid_session_ids:
                return False, f"reference_invalid:session_id_unknown:{sid}"

    for milestone in plan.milestones:
        for key in milestone.focus_gaps or []:
            if key not in valid_gap_keys and key not in valid_dimensions:
                return False, f"reference_invalid:milestone_focus_gap:{key}"

    for task in plan.tasks:
        if task.gap_key and task.gap_key not in valid_gap_keys and task.gap_key not in valid_dimensions:
            return False, f"reference_invalid:task_gap_key:{task.gap_key}"
        for evidence in task.source_evidence or []:
            sid = str(evidence.get("session_id") or "").strip()
            if valid_session_ids and sid and sid not in valid_session_ids:
                return False, f"reference_invalid:task_evidence_session:{sid}"

    return True, ""


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def _truncate(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _coerce_int(value: Any, default: int, *, minimum: int = 0, maximum: int = 100) -> int:
    try:
        result = int(value)
    except Exception:
        return default
    return max(minimum, min(maximum, result))


def _coerce_float(value: Any, default: float, *, minimum: float = 0, maximum: float = 10) -> float:
    try:
        result = float(value)
    except Exception:
        return default
    return max(minimum, min(maximum, result))


def data_to_career_plan_structured(data: Dict[str, Any]) -> CareerPlanStructured:
    """Convert a (validated) dict into a :class:`CareerPlanStructured`."""
    profile_raw = data.get("profile") or {}
    profile = ProfileDraft(
        current_stage=_truncate(str(profile_raw.get("current_stage") or ""), 32),
        overall_score=_coerce_float(profile_raw.get("overall_score"), 0.0, minimum=0, maximum=10),
        strength_tags=[str(item) for item in (profile_raw.get("strength_tags") or [])][:10],
        gap_tags=[str(item) for item in (profile_raw.get("gap_tags") or [])][:10],
        summary=_truncate(str(profile_raw.get("summary") or ""), 240),
        generation_mode=str(profile_raw.get("generation_mode") or "llm"),
    )

    gaps: List[GapDraft] = []
    for item in data.get("gaps") or []:
        if not isinstance(item, dict):
            continue
        gaps.append(
            GapDraft(
                key=_truncate(str(item.get("key") or ""), 32),
                label=_truncate(str(item.get("label") or ""), 32),
                severity=str(item.get("severity") or "low"),
                dimension=_truncate(str(item.get("dimension") or ""), 32),
                evidence_session_ids=[str(s) for s in (item.get("evidence_session_ids") or [])][:5],
                evidence_quotes=[_truncate(str(q), 120) for q in (item.get("evidence_quotes") or [])][:3],
                recommended_action=_truncate(str(item.get("recommended_action") or ""), 160),
            )
        )

    milestones: List[MilestoneDraft] = []
    for item in data.get("milestones") or []:
        if not isinstance(item, dict):
            continue
        milestones.append(
            MilestoneDraft(
                sort_order=_coerce_int(item.get("sort_order"), 1, minimum=1, maximum=6),
                title=_truncate(str(item.get("title") or ""), 32),
                month=_coerce_int(item.get("month"), 1, minimum=1, maximum=12),
                description=_truncate(str(item.get("description") or ""), 240),
                success_criteria=_truncate(str(item.get("success_criteria") or ""), 160),
                focus_gaps=[str(g) for g in (item.get("focus_gaps") or [])][:6],
            )
        )

    tasks: List[TaskDraft] = []
    for item in data.get("tasks") or []:
        if not isinstance(item, dict):
            continue
        evidence_list: List[Dict[str, Any]] = []
        for evidence in item.get("source_evidence") or []:
            if not isinstance(evidence, dict):
                continue
            evidence_list.append(
                {
                    "session_id": str(evidence.get("session_id") or ""),
                    "turn_no": int(evidence.get("turn_no") or 0),
                    "score": int(evidence.get("score") or 0),
                    "quote": _truncate(str(evidence.get("quote") or ""), 200),
                }
            )
        tasks.append(
            TaskDraft(
                title=_truncate(str(item.get("title") or ""), 32),
                description=_truncate(str(item.get("description") or ""), 240),
                task_type=str(item.get("task_type") or "skill_practice"),
                priority=_coerce_int(item.get("priority"), 3, minimum=1, maximum=5),
                gap_key=_truncate(str(item.get("gap_key") or ""), 32),
                estimated_effort=_truncate(str(item.get("estimated_effort") or ""), 16),
                success_criteria=_truncate(str(item.get("success_criteria") or ""), 160),
                source_evidence=evidence_list[:5],
                resource_refs=[dict(r) for r in (item.get("resource_refs") or []) if isinstance(r, dict)][:5],
            )
        )

    recommendations: List[RecommendationDraft] = []
    for item in data.get("recommendations") or []:
        if not isinstance(item, dict):
            continue
        recommendations.append(
            RecommendationDraft(
                type=_truncate(str(item.get("type") or "evidence_practice"), 32),
                title=_truncate(str(item.get("title") or ""), 64),
                reason=_truncate(str(item.get("reason") or ""), 240),
                url=str(item.get("url") or ""),
            )
        )

    return CareerPlanStructured(
        profile=profile,
        gaps=gaps,
        milestones=milestones,
        tasks=tasks,
        recommendations=recommendations,
    )


def parse_career_plan_structured(raw: str) -> Optional[CareerPlanStructured]:
    """Extract + validate + convert raw LLM output. ``None`` on failure."""
    data = extract_json_object(raw)
    if data is None:
        return None
    ok, reason = validate_with_schema(data)
    if not ok:
        return None
    return data_to_career_plan_structured(data)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalise_milestones(
    plan: CareerPlanStructured,
    *,
    expected_count: int,
    blueprint_milestones: Sequence[Dict[str, Any]],
) -> List[MilestoneDraft]:
    """Pad or truncate milestones so the count matches ``expected_count``.

    When the LLM produces fewer milestones than expected, we backfill from
    the legacy blueprint so the UI always sees the same number of
    stages. When the LLM overproduces, we keep the first ``expected``.
    """
    if expected_count <= 0:
        return []
    existing = list(plan.milestones)[:expected_count]
    for index in range(len(existing), expected_count):
        seed = blueprint_milestones[index] if index < len(blueprint_milestones) else {
            "title": f"阶段 {index + 1}",
            "description": "围绕目标岗位继续推进。",
            "month": index + 1,
        }
        existing.append(
            MilestoneDraft(
                sort_order=index + 1,
                title=_truncate(str(seed.get("title") or f"阶段 {index + 1}"), 32),
                month=int(seed.get("month") or (index + 1)),
                description=_truncate(str(seed.get("description") or ""), 240),
                success_criteria="完成本阶段目标并产出可验证成果。",
                focus_gaps=[],
            )
        )
    return existing


def career_plan_structured_to_dict(plan: CareerPlanStructured) -> Dict[str, Any]:
    """Serialise a plan to a JSON-compatible dict."""
    return _to_jsonable(plan)


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return {key: _to_jsonable(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def compute_prompt_hash(system_prompt: str, user_prompt: str) -> str:
    """Stable 16-char SHA-256 of the prompt pair for audit logging."""
    payload = (system_prompt or "") + "\u241F" + (user_prompt or "")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "VALID_SEVERITY",
    "VALID_TASK_TYPE",
    "VALID_GENERATION_MODE",
    "ProfileDraft",
    "GapDraft",
    "MilestoneDraft",
    "TaskDraft",
    "RecommendationDraft",
    "CareerPlanStructured",
    "GenerationOutcome",
    "CAREER_PLAN_STRUCTURED_SCHEMA",
    "extract_json_object",
    "validate_with_schema",
    "validate_references",
    "data_to_career_plan_structured",
    "parse_career_plan_structured",
    "normalise_milestones",
    "career_plan_structured_to_dict",
    "compute_prompt_hash",
]

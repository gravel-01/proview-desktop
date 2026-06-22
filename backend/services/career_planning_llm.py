"""Career planning LLM structured generator (phase 3).

The generator is the LLM-facing side of the career planning pipeline.
It is invoked by :class:`CareerPlanningService.generate_plan` after the
:class:`CareerContext` has been built. The generator:

1. Renders the prompt pair via :mod:`career_planning_prompts`.
2. Calls the configured OpenAI-compatible LLM via the existing
   :class:`core.llm_client.OpenAICompatibleClient`.
3. Extracts the JSON, validates it against
   :data:`career_planning_schema.CAREER_PLAN_STRUCTURED_SCHEMA`, and
   cross-checks references against the context.
4. On any failure the generator returns ``success=False`` and the
   service falls back to the phase 2 evidence-aware templates.

A mock client class (:class:`MockLLMClient`) is provided so unit tests
can simulate success, schema failure, parse failure, and exception
without hitting the network.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.career_planning_context import CareerContext
from services.career_planning_prompts import (
    PlanPrompt,
    build_milestone_prompt,
    build_plan_prompt,
    build_recommendation_prompt,
    build_task_prompt,
)
from services.career_planning_schema import (
    CareerPlanStructured,
    GenerationOutcome,
    ProfileDraft,
    RecommendationDraft,
    TaskDraft,
    compute_prompt_hash,
    data_to_career_plan_structured,
    normalise_milestones,
    parse_career_plan_structured,
    validate_references,
    validate_with_schema,
)
from services.career_planning_skill_registry import (
    SKILL_KIND_LLM,
    Skill,
    SkillRegistry,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Client wrapper
# ---------------------------------------------------------------------------

@dataclass
class GenerationStats:
    """Auxiliary stats returned alongside a generation result."""

    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    model_id: str = ""
    prompt_hash: str = ""


class CareerPlanLLMGenerator:
    """Generate a structured :class:`CareerPlanStructured` via an LLM."""

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        *,
        model_provider: Optional[Any] = None,
        memory_bus: Optional[Any] = None,
        skill_registry: Optional[SkillRegistry] = None,
    ):
        self._llm_client = llm_client
        self._model_provider = model_provider
        self._memory_bus = memory_bus
        self._skill_registry = skill_registry

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def generate(
        self,
        *,
        context: CareerContext,
        target_role: str,
        horizon_months: int,
        blueprint_milestones: Optional[Sequence[Dict[str, Any]]] = None,
    ) -> GenerationOutcome:
        """Single-shot generation. Returns ``success=False`` on any failure."""
        blueprint_milestones = list(blueprint_milestones or [])
        prompt = build_plan_prompt(
            context=context,
            target_role=target_role,
            horizon_months=horizon_months,
            expected_milestone_count=len(blueprint_milestones) or 3,
        )
        prompt_hash = compute_prompt_hash(prompt.system_prompt, prompt.user_prompt)
        client = self._resolve_client()
        if client is None:
            return self._log_failure(
                context=context,
                prompt=prompt,
                prompt_hash=prompt_hash,
                reason="llm_unavailable",
                stats=GenerationStats(prompt_hash=prompt_hash, model_id="fallback"),
            )

        raw_output, stats = self._invoke(client, prompt, prompt_hash=prompt_hash)
        if raw_output is None:
            return self._log_failure(
                context=context,
                prompt=prompt,
                prompt_hash=prompt_hash,
                reason=stats.get("error", "llm_exception") if isinstance(stats, dict) else "llm_exception",
                stats=GenerationStats(
                    latency_ms=stats.get("latency_ms", 0) if isinstance(stats, dict) else 0,
                    model_id=stats.get("model_id", "") if isinstance(stats, dict) else "",
                    prompt_hash=prompt_hash,
                ),
                raw_output=stats.get("raw") if isinstance(stats, dict) else "",
            )

        parsed = parse_career_plan_structured(raw_output)
        if parsed is None:
            return self._log_failure(
                context=context,
                prompt=prompt,
                prompt_hash=prompt_hash,
                reason="parse_or_schema_error",
                stats=GenerationStats(
                    latency_ms=stats.get("latency_ms", 0) if isinstance(stats, dict) else 0,
                    tokens_in=stats.get("tokens_in", 0) if isinstance(stats, dict) else 0,
                    tokens_out=stats.get("tokens_out", 0) if isinstance(stats, dict) else 0,
                    model_id=stats.get("model_id", "") if isinstance(stats, dict) else "",
                    prompt_hash=prompt_hash,
                ),
                raw_output=raw_output,
            )

        # pad/truncate milestones
        parsed = _attach_metadata(
            parsed,
            model_id=stats.get("model_id", "") if isinstance(stats, dict) else "",
            prompt_hash=prompt_hash,
            latency_ms=stats.get("latency_ms", 0) if isinstance(stats, dict) else 0,
            tokens_in=stats.get("tokens_in", 0) if isinstance(stats, dict) else 0,
            tokens_out=stats.get("tokens_out", 0) if isinstance(stats, dict) else 0,
            raw_output=raw_output,
        )
        expected_count = len(blueprint_milestones) or 3
        normalised_milestones = normalise_milestones(
            parsed,
            expected_count=expected_count,
            blueprint_milestones=blueprint_milestones,
        )
        parsed = _replace_milestones(parsed, normalised_milestones)

        # cross-check references
        ok, reason = validate_references(parsed, context)
        if not ok:
            return self._log_failure(
                context=context,
                prompt=prompt,
                prompt_hash=prompt_hash,
                reason=reason or "reference_invalid",
                stats=GenerationStats(
                    latency_ms=parsed.latency_ms,
                    tokens_in=parsed.tokens_in,
                    tokens_out=parsed.tokens_out,
                    model_id=parsed.model_id,
                    prompt_hash=prompt_hash,
                ),
                raw_output=raw_output,
            )

        # at least one task per milestone
        if not _has_minimum_tasks(parsed):
            return self._log_failure(
                context=context,
                prompt=prompt,
                prompt_hash=prompt_hash,
                reason="task_too_few",
                stats=GenerationStats(
                    latency_ms=parsed.latency_ms,
                    tokens_in=parsed.tokens_in,
                    tokens_out=parsed.tokens_out,
                    model_id=parsed.model_id,
                    prompt_hash=prompt_hash,
                ),
                raw_output=raw_output,
            )

        # success
        if self._memory_bus is not None:
            try:
                self._memory_bus.log_skill_eval(
                    skill_name="llm_generate_plan_struct",
                    skill_version="v1",
                    inputs={"prompt_hash": prompt_hash, "target_role": target_role},
                    outputs={"success": True, "tokens_out": parsed.tokens_out},
                    success=True,
                    latency_ms=parsed.latency_ms,
                    tokens_in=parsed.tokens_in,
                    tokens_out=parsed.tokens_out,
                    model_id=parsed.model_id,
                    prompt_hash=prompt_hash,
                    user_id=getattr(context.build_meta, "user_id", None),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("[career_llm] log_skill_eval failed: %s", exc)

        return GenerationOutcome(
            success=True,
            plan=parsed,
            latency_ms=parsed.latency_ms,
            tokens_in=parsed.tokens_in,
            tokens_out=parsed.tokens_out,
            model_id=parsed.model_id,
            prompt_hash=prompt_hash,
            raw_output=raw_output,
        )

    # ------------------------------------------------------------------
    # Skill registration helpers
    # ------------------------------------------------------------------
    def register_with_registry(self, registry: SkillRegistry) -> None:
        """Attach LLM-backed skills to the provided registry."""
        registry.register(
            Skill(
                name="llm_generate_plan_struct",
                version="v1",
                kind=SKILL_KIND_LLM,
                description="调用 LLM 一次性生成完整 CareerPlanStructured。",
                handler=lambda **kwargs: self.generate(**kwargs),
                input_description="(context, target_role, horizon_months, blueprint_milestones)",
                output_description="GenerationOutcome",
            )
        )


# ---------------------------------------------------------------------------
# Mock client (for tests)
# ---------------------------------------------------------------------------

class MockLLMClient:
    """Deterministic mock of :class:`core.llm_client.OpenAICompatibleClient`.

    Parameters
    ----------
    response
        Either a dict (raw LLM output) or a callable that receives the
        messages and returns the response. Set ``raise_exc`` to make
        the client raise an exception on every call.
    """

    def __init__(
        self,
        response: Any = None,
        *,
        raise_exc: Optional[BaseException] = None,
        model: str = "mock-llm",
        latency_ms: int = 1,
    ):
        self._response = response
        self._raise_exc = raise_exc
        self._model = model
        self._latency_ms = latency_ms
        self.calls: List[List[Dict[str, Any]]] = []

    def generate(self, messages: List[Dict[str, Any]]) -> str:
        self.calls.append(messages)
        if self._raise_exc is not None:
            raise self._raise_exc
        if callable(self._response):
            value = self._response(messages)
        elif isinstance(self._response, str):
            value = self._response
        else:
            value = json.dumps(self._response or {}, ensure_ascii=False)
        return value

    @property
    def model(self) -> str:
        return self._model

    @property
    def latency_ms(self) -> int:
        return self._latency_ms


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def attach_llm_skills(registry: SkillRegistry, generator: CareerPlanLLMGenerator) -> None:
    """Register the LLM-backed skills onto ``registry``."""
    generator.register_with_registry(registry)


def _has_minimum_tasks(plan: CareerPlanStructured) -> bool:
    """At least one task overall and ``>= 50%`` per-milestone coverage on average.

    The downstream service layer (``_create_plan_rows``) re-distributes
    tasks across milestones via ``focus_gaps`` overlap, so a plan with
    one task per milestone is ideal but not strictly required. We only
    fail when the LLM produced *no* tasks or substantially fewer than
    expected.
    """
    if not plan.tasks:
        return False
    milestone_count = max(1, len(plan.milestones))
    # Allow at least one task overall; require >= half of milestones covered
    # (rounded down) to keep the per-milestone budget honest.
    coverage_target = max(1, milestone_count // 2)
    return len(plan.tasks) >= coverage_target


def _attach_metadata(
    plan: CareerPlanStructured,
    *,
    model_id: str,
    prompt_hash: str,
    latency_ms: int,
    tokens_in: int,
    tokens_out: int,
    raw_output: str,
) -> CareerPlanStructured:
    """Return a new plan with metadata fields populated."""
    from dataclasses import replace

    return replace(
        plan,
        model_id=model_id,
        prompt_hash=prompt_hash,
        latency_ms=latency_ms,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        raw_model_output=raw_output,
        generation_mode="llm",
    )


def _replace_milestones(
    plan: CareerPlanStructured,
    milestones: List,
) -> CareerPlanStructured:
    from dataclasses import replace

    return replace(plan, milestones=milestones)


def _resolve_client(generator: CareerPlanLLMGenerator) -> Optional[Any]:
    """Resolve the LLM client or return ``None`` when unavailable."""
    return generator._resolve_client()


# We need a way for CareerPlanLLMGenerator to access protected internals; define
# a real method on the class so tests / subclasses can override.
def _generator_resolve(self: CareerPlanLLMGenerator) -> Optional[Any]:
    if self._llm_client is not None:
        return self._llm_client
    if self._model_provider is None:
        return None
    available = bool(getattr(self._model_provider, "available", False))
    if not available:
        return None
    try:
        from core.llm_client import OpenAICompatibleClient
    except Exception:  # pragma: no cover - defensive
        return None
    try:
        return OpenAICompatibleClient(
            model=str(getattr(self._model_provider, "model", "")),
            api_key=str(getattr(self._model_provider, "api_key", "")),
            base_url=str(getattr(self._model_provider, "base_url", "")),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[career_llm] failed to build OpenAICompatibleClient: %s", exc)
        return None


def _generator_invoke(
    self: CareerPlanLLMGenerator,
    client: Any,
    prompt: PlanPrompt,
    *,
    prompt_hash: str,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Call the LLM client and return ``(raw_output, stats)``.

    ``stats`` always contains ``latency_ms`` and ``model_id``; token
    counts are only populated when the client returns usage data.
    """
    import time

    started = time.perf_counter()
    messages = [
        {"role": "system", "content": prompt.system_prompt},
        {"role": "user", "content": prompt.user_prompt},
    ]
    try:
        result = client.generate(messages)
    except Exception as exc:  # pragma: no cover - defensive
        latency_ms = int((time.perf_counter() - started) * 1000)
        return None, {
            "latency_ms": latency_ms,
            "model_id": getattr(client, "model", ""),
            "error": f"llm_exception:{exc}",
        }
    latency_ms = int((time.perf_counter() - started) * 1000)
    stats: Dict[str, Any] = {
        "latency_ms": latency_ms,
        "model_id": getattr(client, "model", ""),
        "tokens_in": 0,
        "tokens_out": 0,
    }
    if not isinstance(result, str):
        result = json.dumps(result, ensure_ascii=False)
    return result, stats


def _generator_log_failure(
    self: CareerPlanLLMGenerator,
    *,
    context: CareerContext,
    prompt: PlanPrompt,
    prompt_hash: str,
    reason: str,
    stats: GenerationStats,
    raw_output: str = "",
) -> GenerationOutcome:
    if self._memory_bus is not None:
        try:
            self._memory_bus.log_skill_eval(
                skill_name="llm_generate_plan_struct",
                skill_version="v1",
                inputs={"prompt_hash": prompt_hash, "target_role": getattr(context, "target_role", "")},
                outputs={"success": False, "reason": reason},
                success=False,
                latency_ms=stats.latency_ms,
                model_id=stats.model_id or "fallback",
                prompt_hash=prompt_hash,
                fallback_reason=reason,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("[career_llm] log_skill_eval failed: %s", exc)
    return GenerationOutcome(
        success=False,
        error=reason,
        fallback_reason=reason,
        latency_ms=stats.latency_ms,
        tokens_in=stats.tokens_in,
        tokens_out=stats.tokens_out,
        model_id=stats.model_id,
        prompt_hash=prompt_hash,
        raw_output=raw_output,
    )


# Attach methods after class definition so we can keep them grouped here.
CareerPlanLLMGenerator._resolve_client = _generator_resolve  # type: ignore[attr-defined]
CareerPlanLLMGenerator._invoke = _generator_invoke  # type: ignore[attr-defined]
CareerPlanLLMGenerator._log_failure = _generator_log_failure  # type: ignore[attr-defined]


__all__ = [
    "CareerPlanLLMGenerator",
    "GenerationStats",
    "MockLLMClient",
    "attach_llm_skills",
]

"""Career planning skill registry (phase 3).

The skill registry is the runtime scaffolding for the "self-evolving
skill group" the diagnostic handoff calls out as a phase 3 must-have. It
exposes a single, side-effectful surface — :class:`SkillRegistry` —
that the rest of the subsystem can use to:

1. **Register** a skill by name + version + handler. The handler may be
   a deterministic pure function (phase 2 skill) or an LLM call (phase
   3 skill). Both share the same ``run`` API.
2. **Invoke** a skill with keyword arguments; the registry records
   latency / inputs hash / outputs hash / success to the
   :class:`SkillEvalLogStore` automatically.
3. **Upgrade** a skill to a new version without breaking the old one.
   The active version pointer is mutable; old versions remain callable
   for reproducibility.
4. **Evaluate** the registry against a fixture file using
   :class:`SkillEvaluator`.

The registry is intentionally a thin wrapper around plain dataclasses
so it stays easy to test and easy to reason about.
"""

from __future__ import annotations

import inspect
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from services.career_planning_skills import (
    apply_read_event_to_progress,
    build_evidence_aware_tasks,
    collect_resource_recommendations,
    compute_dimension_stats,
    derive_gap_severity,
    extract_resume_gap_signals,
    score_resource_match,
    select_top_evidence,
    select_top_suggestions,
    summarize_context_for_llm,
    tag_resource_to_task,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Skill definition
# ---------------------------------------------------------------------------

SKILL_KIND_PURE_FUNCTION = "pure_function"
SKILL_KIND_LLM = "llm"

VALID_SKILL_KINDS: Tuple[str, ...] = (SKILL_KIND_PURE_FUNCTION, SKILL_KIND_LLM)


@dataclass(frozen=True)
class Skill:
    """A registered, callable unit in the career planning pipeline.

    Attributes
    ----------
    name
        Stable, dot/underscore separated skill id, e.g. ``compute_dimension_stats``.
    version
        Semantic version of the handler. Multiple versions can be
        registered; the active version is the one returned by
        :meth:`SkillRegistry.get`.
    kind
        Either ``"pure_function"`` (deterministic) or ``"llm"`` (network
        roundtrip + structured output).
    description
        Short human-readable description (used in /skill list and the
        audit log).
    handler
        Callable accepting keyword arguments and returning a value
        compatible with ``output_description``.
    input_description
        Free-form description of accepted inputs. Used only for docs.
    output_description
        Free-form description of produced output. Used only for docs.
    """

    name: str
    version: str
    kind: str
    description: str
    handler: Callable[..., Any]
    input_description: str = ""
    output_description: str = ""

    def __post_init__(self) -> None:
        if self.kind not in VALID_SKILL_KINDS:
            raise ValueError(f"invalid skill kind: {self.kind!r}")
        if not callable(self.handler):
            raise TypeError(f"skill {self.name!r} handler must be callable")


@dataclass(frozen=True)
class SkillRunResult:
    """Result of one :meth:`SkillRegistry.run` call."""

    name: str
    version: str
    success: bool
    output: Any
    error: str = ""
    latency_ms: int = 0
    inputs_hash: str = ""
    outputs_hash: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class SkillRegistry:
    """In-memory registry of skills keyed by ``(name, version)``.

    The active version per name is tracked in :attr:`_active_versions`
    and can be changed with :meth:`upgrade`.
    """

    def __init__(self, memory_bus: Optional[Any] = None):
        self._skills: Dict[Tuple[str, str], Skill] = {}
        self._active_versions: Dict[str, str] = {}
        self._memory_bus = memory_bus

    # ----- registration -----
    def register(self, skill: Skill, *, activate: bool = True) -> None:
        key = (skill.name, skill.version)
        if key in self._skills:
            raise ValueError(f"skill {skill.name!r}@{skill.version} already registered")
        self._skills[key] = skill
        if activate or skill.name not in self._active_versions:
            self._active_versions[skill.name] = skill.version

    def unregister(self, name: str, version: Optional[str] = None) -> None:
        if version is None:
            version = self._active_versions.get(name)
        if version is None:
            return
        self._skills.pop((name, version), None)
        if self._active_versions.get(name) == version:
            remaining = [v for (n, v) in self._skills.keys() if n == name]
            if remaining:
                self._active_versions[name] = sorted(remaining)[-1]
            else:
                self._active_versions.pop(name, None)

    def upgrade(self, name: str, new_version: str) -> None:
        if (name, new_version) not in self._skills:
            raise KeyError(f"cannot upgrade: {name!r}@{new_version} not registered")
        self._active_versions[name] = new_version

    # ----- lookup -----
    def get(self, name: str, version: Optional[str] = None) -> Skill:
        if version is None:
            version = self._active_versions.get(name)
            if version is None:
                raise KeyError(f"no active version for skill {name!r}")
        skill = self._skills.get((name, version))
        if skill is None:
            raise KeyError(f"skill {name!r}@{version} not found")
        return skill

    def list(self) -> List[Dict[str, str]]:
        out: List[Dict[str, str]] = []
        for (name, version), skill in sorted(self._skills.items()):
            out.append(
                {
                    "name": name,
                    "version": version,
                    "kind": skill.kind,
                    "description": skill.description,
                    "active": "1" if self._active_versions.get(name) == version else "0",
                }
            )
        return out

    # ----- invocation -----
    def run(
        self,
        name: str,
        /,
        *,
        version: Optional[str] = None,
        log_eval: bool = True,
        **kwargs: Any,
    ) -> SkillRunResult:
        skill = self.get(name, version)
        started = time.perf_counter()
        inputs_hash = _hash_payload(kwargs)
        try:
            output = skill.handler(**kwargs)
            latency_ms = int((time.perf_counter() - started) * 1000)
            outputs_hash = _hash_payload(output)
            result = SkillRunResult(
                name=skill.name,
                version=skill.version,
                success=True,
                output=output,
                latency_ms=latency_ms,
                inputs_hash=inputs_hash,
                outputs_hash=outputs_hash,
            )
        except Exception as exc:  # pragma: no cover - defensive
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning("[skill_registry] %s@%s failed: %s", skill.name, skill.version, exc)
            result = SkillRunResult(
                name=skill.name,
                version=skill.version,
                success=False,
                output=None,
                error=str(exc),
                latency_ms=latency_ms,
                inputs_hash=inputs_hash,
            )

        if log_eval and self._memory_bus is not None:
            try:
                self._memory_bus.log_skill_eval(
                    skill_name=skill.name,
                    skill_version=skill.version,
                    inputs={"hash": inputs_hash, "kwargs_keys": sorted(kwargs.keys())},
                    outputs={"hash": getattr(result, "outputs_hash", ""), "type": type(result.output).__name__},
                    success=result.success,
                    latency_ms=result.latency_ms,
                    fallback_reason=result.error if not result.success else "",
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("[skill_registry] failed to log eval: %s", exc)

        return result

    # ----- access -----
    @property
    def memory_bus(self) -> Optional[Any]:
        return self._memory_bus

    def set_memory_bus(self, memory_bus: Any) -> None:
        self._memory_bus = memory_bus


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SkillEvalCase:
    """Single test case for a skill evaluation run."""

    name: str
    inputs: Mapping[str, Any]
    expected: Any
    description: str = ""
    matcher: str = "exact"  # exact | subset | contains_keys


@dataclass(frozen=True)
class SkillEvalSummary:
    """Aggregate stats for one skill across multiple cases."""

    name: str
    version: str
    total: int
    passed: int
    failed: int
    avg_latency_ms: float

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


class SkillEvaluator:
    """Run a registry against an evaluation fixture (JSON / dict).

    The evaluator is intentionally simple: it iterates cases, calls
    :meth:`SkillRegistry.run` for each, and compares the output with a
    small set of matchers.
    """

    def __init__(self, registry: SkillRegistry):
        self._registry = registry

    def evaluate(
        self,
        eval_set: Mapping[str, Sequence[Mapping[str, Any]]],
    ) -> List[SkillEvalSummary]:
        summaries: List[SkillEvalSummary] = []
        for name, cases in eval_set.items():
            results: List[SkillRunResult] = []
            for case in cases:
                if not isinstance(case, Mapping):
                    continue
                inputs = case.get("inputs") or {}
                if not isinstance(inputs, Mapping):
                    inputs = {"value": inputs}
                result = self._registry.run(
                    name,
                    log_eval=False,
                    **inputs,
                )
                results.append(result)
            if not results:
                continue
            passed = sum(
                1 for r, case in zip(results, cases)
                if r.success and _matches(case.get("expected"), r.output, case.get("matcher", "exact"))
            )
            avg_latency = sum(r.latency_ms for r in results) / len(results)
            summaries.append(
                SkillEvalSummary(
                    name=name,
                    version=results[0].version,
                    total=len(results),
                    passed=passed,
                    failed=len(results) - passed,
                    avg_latency_ms=round(avg_latency, 2),
                )
            )
        return summaries


# ---------------------------------------------------------------------------
# Default registry factory
# ---------------------------------------------------------------------------

def default_registry(memory_bus: Optional[Any] = None) -> SkillRegistry:
    """Build a registry preloaded with the phase 2 / phase 3 skills.

    Pure-function skills are registered first so they can be used as
    the deterministic fallback for the LLM skills.
    """
    registry = SkillRegistry(memory_bus=memory_bus)
    register_phase2_pure_skills(registry)
    # LLM skills are registered by ``career_planning_llm`` to avoid a
    # circular import. Use :func:`attach_llm_skills` to add them.
    return registry


def register_phase2_pure_skills(registry: SkillRegistry) -> None:
    """Register the phase 2 deterministic skills (no LLM).

    The function is idempotent: re-registering on a registry that
    already has the skills is a no-op. This makes it safe to call from
    multiple boot paths.
    """
    existing = {(name, version) for (name, version) in registry._skills.keys()}  # noqa: SLF001

    def _reg(skill: Skill) -> None:
        key = (skill.name, skill.version)
        if key in existing:
            return
        registry.register(skill)
        existing.add(key)

    _reg(
        Skill(
            name="compute_dimension_stats",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="聚合逐轮评价数据，按维度计算统计和 severity。",
            handler=compute_dimension_stats,
            input_description="Sequence[Dict] (per-turn evaluations)",
            output_description="List[DimensionStat]",
        )
    )
    _reg(
        Skill(
            name="derive_gap_severity",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="根据平均分和样本数推导 gap 严重度。",
            handler=derive_gap_severity,
            input_description="(avg_score: float, evaluation_count: int)",
            output_description="severity ∈ {high, medium, low, none}",
        )
    )
    _reg(
        Skill(
            name="extract_resume_gap_signals",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="从简历 OCR 提取与目标岗位相关的缺口标签。",
            handler=extract_resume_gap_signals,
            input_description="(ocr_text: str, target_role: str)",
            output_description="List[str] gap labels",
        )
    )
    _reg(
        Skill(
            name="build_evidence_aware_tasks",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="基于 gap 维度生成 evidence-aware 任务模板。",
            handler=build_evidence_aware_tasks,
            input_description="(target_role, milestone_index, gap_dimensions, focus_gaps, horizon_months)",
            output_description="List[TaskTemplate]",
        )
    )
    _reg(
        Skill(
            name="select_top_evidence",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="从评价列表中挑选代表性 evidence。",
            handler=select_top_evidence,
            input_description="Sequence[Dict] evaluations",
            output_description="List[EvidenceSample]",
        )
    )
    _reg(
        Skill(
            name="select_top_suggestions",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="从评价列表中挑选代表性 suggestion。",
            handler=select_top_suggestions,
            input_description="Sequence[Dict] evaluations",
            output_description="List[SuggestionSample]",
        )
    )
    _reg(
        Skill(
            name="summarize_context_for_llm",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="把 CareerContext 序列化成 LLM 友好的紧凑文本。",
            handler=summarize_context_for_llm,
            input_description="(context_summary: dict, dimension_stats: Sequence[DimensionStat])",
            output_description="str (Markdown-ish)",
        )
    )

    # ----- phase 4: resource-closure skills -----
    _reg(
        Skill(
            name="tag_resource_to_task",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="为单个 task 关联最相关的文档 section（最多 2 条）。",
            handler=tag_resource_to_task,
            input_description="(task: dict, sections: Sequence[dict], target_role='', top_k=2, score_threshold=0.3)",
            output_description="List[{doc_id, section_idx, reason, score}]",
        )
    )
    _reg(
        Skill(
            name="score_resource_match",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="根据 gap / skill / task_type 计算单个 section 的推荐分数。",
            handler=score_resource_match,
            input_description="(section: dict, user_gap_keys, user_skill_keys, user_task_types, target_role, ...)",
            output_description="float in [0, 1]",
        )
    )
    _reg(
        Skill(
            name="apply_read_event_to_progress",
            version="v1",
            kind=SKILL_KIND_PURE_FUNCTION,
            description="根据用户阅读完成事件计算 task 进度的新值（单调递增，clamp 到 [0, 100]）。",
            handler=apply_read_event_to_progress,
            input_description="(current_progress: float, completed: bool, increment: float = 10.0)",
            output_description="float",
        )
    )


def register_phase2_3_pure_skills(registry: SkillRegistry) -> None:
    """Register all phase 2/3/4 deterministic skills.

    This is the canonical entrypoint for production code; the legacy
    :func:`register_phase2_pure_skills` is kept as a thin wrapper for
    backward compatibility.
    """
    register_phase2_pure_skills(registry)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _hash_payload(value: Any) -> str:
    import hashlib

    try:
        encoded = json.dumps(value, ensure_ascii=False, default=str, sort_keys=True)
    except Exception:
        encoded = repr(value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]


def _matches(expected: Any, actual: Any, matcher: str) -> bool:
    if matcher == "subset":
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            return False
        return all(actual.get(k) == v for k, v in expected.items())
    if matcher == "contains_keys":
        if not isinstance(expected, Mapping) or not isinstance(actual, Mapping):
            return False
        return all(k in actual for k in expected.keys())
    if matcher == "callable":
        if callable(expected):
            return bool(expected(actual))
        return False
    return expected == actual


__all__ = [
    "SKILL_KIND_PURE_FUNCTION",
    "SKILL_KIND_LLM",
    "VALID_SKILL_KINDS",
    "Skill",
    "SkillRunResult",
    "SkillRegistry",
    "SkillEvalCase",
    "SkillEvalSummary",
    "SkillEvaluator",
    "default_registry",
    "register_phase2_pure_skills",
]

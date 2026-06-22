"""Career planning LLM prompt templates (phase 3).

This module centralises the prompt engineering for the LLM-driven
generation path. Every prompt is constructed in code (not stored in
JSON) so the templates are easy to read in source review and so unit
tests can render the same exact string a production run would send.

Design rules
------------

1. **Anti-hallucination first**: every system prompt starts with the
   same "你必须只能引用 context 中已经出现的数据" guardrail.
2. **Schema is the contract**: every user prompt ends with a JSON
   skeleton that matches :data:`CAREER_PLAN_STRUCTURED_SCHEMA`.
3. **Deterministic context serialisation**: the
   :func:`serialize_context_for_llm` helper produces the same string
   for the same :class:`CareerContext`, which lets us hash prompts for
   audit logs.
4. **Chinese-first**: prompts are in Chinese to match the project UI
   and the eval fixtures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from services.career_planning_context import CareerContext, ContextSummary, DimensionStat


# ---------------------------------------------------------------------------
# Common rules shared by every system prompt
# ---------------------------------------------------------------------------

COMMON_GUARDRAILS = """# 🚫 反幻觉底线（违反任何一条即为严重失败）
1. 【禁止捏造】所有 gap 名称、dimension、session_id、turn_no、evidence quote 必须来自下方 "用户数据快照" 提供的字段；不得编造 context 中没有出现的 session_id、turn_no、分数或引文。
2. 【禁止自创维度】gap.dimension 只能取自下方出现的 7 个评价维度：性能优化 / 系统设计 / 项目经验 / 问题定位 / 工程实践 / 沟通表达 / 学习能力。
3. 【目标岗位强绑定】title / description / summary / reason 中必须显式出现 target_role（至少 1 次），不得泛泛而谈。
4. 【证据可追溯】每个 task 至少包含 1 条 source_evidence，且 session_id 必须在 context.sessions 中出现过。
5. 【结构稳定】只输出 JSON，不输出 markdown 代码块包裹、不输出自然语言解释。JSON 顶层为 CareerPlanStructured 指定的字段。
"""


SYSTEM_PROMPT_PLAN = f"""# 角色定义 (Persona)
你是一位拥有 10 年大厂经验的资深 AI 产品经理 / 职业规划教练，正在为一位求职者生成可执行、可追溯、可验证的"职业规划"。

{COMMON_GUARDRAILS}

# 输出契约
- 严格输出 JSON，字段必须符合 CareerPlanStructured。
- 字段 current_stage 必须是下列之一：数据不足 / 仅有简历数据 / 仅有面试记录 / 冲刺中 / 成长中 / 打基础。
- 任务数 ≤ 24，每个 milestone 至少 1 个 task。
- task.priority 1..5，task_type 必须是 skill_practice / interview_prep / project / course 之一。
- 每个 task 必须携带 1 条以上 source_evidence（session_id + turn_no + score + quote），用作后续追问锚点。
"""


SYSTEM_PROMPT_MILESTONE = f"""# 角色定义
你是一位资深职业规划教练，正在为候选人细化每个阶段里程碑。

{COMMON_GUARDRAILS}

# 输出契约
- 输出 JSON，字段必须包含 sort_order / title / month / description / success_criteria / focus_gaps。
- title ≤ 32 字；description ≤ 240 字；success_criteria ≤ 160 字。
- milestone 数量必须与下方 "expected_milestone_count" 完全一致。
"""


SYSTEM_PROMPT_TASK = f"""# 角色定义
你是一位资深职业规划教练，正在为单个 gap 生成可验证的 1 个学习 / 面试 / 项目任务。

{COMMON_GUARDRAILS}

# 输出契约
- 输出 JSON 单个对象，字段与 schema 中 task 定义一致。
- 至少 1 条 source_evidence；estimated_effort 用 "N 周" 或 "N 个月"；success_criteria 给出可量化阈值。
"""


SYSTEM_PROMPT_RECOMMENDATION = f"""# 角色定义
你是一位资深职业规划教练，正在基于候选人的高优先级 gap 输出 1-3 条针对性推荐。

{COMMON_GUARDRAILS}

# 输出契约
- 输出 JSON 数组，每条包含 type / title / reason / url 四个字段；type 取 evidence_practice / course / project / practice 之一。
- reason 必须引用具体 gap / dimension / evidence；url 留空字符串即可（不要编造链接）。
"""


# ---------------------------------------------------------------------------
# User prompt templates
# ---------------------------------------------------------------------------

USER_PROMPT_PLAN_TEMPLATE = """# 用户数据快照
- target_role: {target_role}
- horizon_months: {horizon_months}
- generation_mode_hint: {generation_mode_hint}
- source_summary: {source_summary}

# 评价维度统计（来自真实逐轮评价）
{dimension_stats_block}

# 代表证据（evidence samples）
{evidence_block}

# 改进建议（suggestion samples）
{suggestion_block}

# 简历 gap signals
{resume_gap_block}

# 已有 milestone 数量要求
expected_milestone_count: {expected_milestone_count}

# 你的任务
请基于上述用户数据，输出 1 个 JSON，对应 CareerPlanStructured：
- profile.current_stage / overall_score / gap_tags / strength_tags / summary
- gaps[]：每个 gap 必须包含 evidence_quotes（来自上面"代表证据"）
- milestones[]：数量 = expected_milestone_count
- tasks[]：每 milestone 至少 1 个 task，最多 4 个；每个 task 至少 1 条 source_evidence
- recommendations[]：1-3 条针对性建议

请直接输出 JSON，不要使用 markdown 包裹。
"""


USER_PROMPT_MILESTONE_TEMPLATE = """# 用户数据快照
- target_role: {target_role}
- horizon_months: {horizon_months}
- existing_milestones_seed: {existing_milestones_seed}
- focus_gaps_seed: {focus_gaps_seed}
- expected_milestone_count: {expected_milestone_count}

# 评价维度统计
{dimension_stats_block}

# 你的任务
请基于上述数据，输出 1 个 JSON，包含 milestones 数组，长度 = expected_milestone_count。
不要输出其他字段。只输出 JSON。
"""


USER_PROMPT_TASK_TEMPLATE = """# 用户数据快照
- target_role: {target_role}
- horizon_months: {horizon_months}
- milestone_title: {milestone_title}
- gap: {gap_block}
- suggestion: {suggestion_block}
- evidence: {evidence_block}

# 你的任务
基于上述数据输出 1 个 task JSON 对象，对应 schema 中 task 字段。只输出 JSON。
"""


USER_PROMPT_RECOMMENDATION_TEMPLATE = """# 用户数据快照
- target_role: {target_role}
- horizon_months: {horizon_months}
- gap_dimensions: {gap_block}

# 你的任务
输出 JSON 数组 recommendations，1-3 条。只输出 JSON。
"""


# ---------------------------------------------------------------------------
# Public builders
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanPrompt:
    """Container for the plan-level prompt pair."""

    system_prompt: str
    user_prompt: str


def build_plan_prompt(
    *,
    context: CareerContext,
    target_role: str,
    horizon_months: int,
    expected_milestone_count: int,
) -> PlanPrompt:
    """Build the (system, user) pair for the all-in-one plan call."""
    user = USER_PROMPT_PLAN_TEMPLATE.format(
        target_role=target_role or "(未指定)",
        horizon_months=int(horizon_months),
        generation_mode_hint=_hint_for(context),
        source_summary=_format_source_summary(context),
        dimension_stats_block=_format_dimension_stats(context.dimension_stats),
        evidence_block=_format_evidence_samples(context),
        suggestion_block=_format_suggestion_samples(context),
        resume_gap_block=_format_resume_gap_signals(context),
        expected_milestone_count=int(expected_milestone_count),
    )
    return PlanPrompt(system_prompt=SYSTEM_PROMPT_PLAN, user_prompt=user)


def build_milestone_prompt(
    *,
    context: CareerContext,
    target_role: str,
    horizon_months: int,
    expected_milestone_count: int,
    existing_milestones_seed: Optional[Sequence[Dict[str, Any]]] = None,
    focus_gaps_seed: Optional[Sequence[str]] = None,
) -> PlanPrompt:
    user = USER_PROMPT_MILESTONE_TEMPLATE.format(
        target_role=target_role or "(未指定)",
        horizon_months=int(horizon_months),
        existing_milestones_seed=json.dumps(list(existing_milestones_seed or []), ensure_ascii=False),
        focus_gaps_seed=json.dumps(list(focus_gaps_seed or []), ensure_ascii=False),
        expected_milestone_count=int(expected_milestone_count),
        dimension_stats_block=_format_dimension_stats(context.dimension_stats),
    )
    return PlanPrompt(system_prompt=SYSTEM_PROMPT_MILESTONE, user_prompt=user)


def build_task_prompt(
    *,
    context: CareerContext,
    target_role: str,
    horizon_months: int,
    milestone_title: str,
    gap: Dict[str, Any],
    suggestion: str = "",
    evidence: Optional[Sequence[Dict[str, Any]]] = None,
) -> PlanPrompt:
    user = USER_PROMPT_TASK_TEMPLATE.format(
        target_role=target_role or "(未指定)",
        horizon_months=int(horizon_months),
        milestone_title=milestone_title or "本阶段",
        gap_block=json.dumps(gap or {}, ensure_ascii=False),
        suggestion_block=(suggestion or "").strip() or "(无)",
        evidence_block=json.dumps(list(evidence or []), ensure_ascii=False),
    )
    return PlanPrompt(system_prompt=SYSTEM_PROMPT_TASK, user_prompt=user)


def build_recommendation_prompt(
    *,
    context: CareerContext,
    target_role: str,
    horizon_months: int,
) -> PlanPrompt:
    user = USER_PROMPT_RECOMMENDATION_TEMPLATE.format(
        target_role=target_role or "(未指定)",
        horizon_months=int(horizon_months),
        gap_block=json.dumps([_dimension_to_dict(d) for d in context.dimension_stats], ensure_ascii=False),
    )
    return PlanPrompt(system_prompt=SYSTEM_PROMPT_RECOMMENDATION, user_prompt=user)


# ---------------------------------------------------------------------------
# Serialisation helpers (also used by tests)
# ---------------------------------------------------------------------------

def serialize_context_for_llm(context: CareerContext) -> str:
    """Render a :class:`CareerContext` as a deterministic Markdown-ish text."""
    parts: List[str] = []
    parts.append("# Career Planning Context")
    parts.append("## 数据概况")
    for key, value in _summary_to_dict(context.summary).items():
        parts.append(f"- {key}: {value}")
    if context.dimension_stats:
        parts.append("## 维度表现")
        for stat in context.dimension_stats[:6]:
            parts.append(
                f"- {stat.dimension}: avg={stat.avg_score}, n={stat.evaluation_count}, "
                f"low={stat.low_score_count}, severity={stat.severity}"
            )
    if context.evidence_samples:
        parts.append("## 代表证据")
        for sample in context.evidence_samples[:5]:
            parts.append(
                f"- [{sample.get('dimension')}] score={sample.get('score')} "
                f"session={sample.get('session_id')} turn={sample.get('turn_no')}: "
                f"{(sample.get('evidence') or '')[:120]}"
            )
    if context.suggestion_samples:
        parts.append("## 改进建议")
        for sample in context.suggestion_samples[:5]:
            parts.append(
                f"- [{sample.get('dimension')}] session={sample.get('session_id')}: "
                f"{(sample.get('text') or '')[:160]}"
            )
    if context.resume_summary.gap_signals:
        parts.append("## 简历缺口")
        for signal in context.resume_summary.gap_signals[:5]:
            parts.append(f"- {signal}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _hint_for(context: CareerContext) -> str:
    if context.summary.evaluation_count > 0:
        return "evidence"
    if context.summary.has_resume:
        return "fallback"
    return "empty"


def _format_source_summary(context: CareerContext) -> str:
    summary = context.summary
    return (
        f"简历={summary.has_resume}；session={summary.session_count}；"
        f"完成={summary.completed_session_count}；"
        f"评价={summary.evaluation_count}；"
        f"低分={summary.low_score_evaluation_count}；"
        f"均分={summary.avg_score}；"
        f"问题元数据={summary.question_metadata_count}；"
        f"简历缺口={summary.resume_gap_signal_count}"
    )


def _format_dimension_stats(stats: Sequence[DimensionStat]) -> str:
    if not stats:
        return "(无)"
    lines: List[str] = []
    for stat in stats[:7]:
        lines.append(
            f"- {stat.dimension}: avg={stat.avg_score}, n={stat.evaluation_count}, "
            f"low={stat.low_score_count}, severity={stat.severity}, "
            f"sessions_observed={stat.sessions_observed}"
        )
    return "\n".join(lines)


def _format_evidence_samples(context: CareerContext) -> str:
    if not context.evidence_samples:
        return "(无)"
    lines: List[str] = []
    for sample in context.evidence_samples[:8]:
        lines.append(
            f"- session_id={sample.get('session_id')} turn_no={sample.get('turn_no')} "
            f"dimension={sample.get('dimension')} score={sample.get('score')}: "
            f"{(sample.get('evidence') or '')[:120]}"
        )
    return "\n".join(lines)


def _format_suggestion_samples(context: CareerContext) -> str:
    if not context.suggestion_samples:
        return "(无)"
    lines: List[str] = []
    for sample in context.suggestion_samples[:6]:
        lines.append(
            f"- session_id={sample.get('session_id')} dimension={sample.get('dimension')}: "
            f"{(sample.get('text') or '')[:160]}"
        )
    return "\n".join(lines)


def _format_resume_gap_signals(context: CareerContext) -> str:
    signals = list(context.resume_summary.gap_signals or [])
    if not signals:
        return "(无)"
    return "\n".join(f"- {signal}" for signal in signals[:5])


def _summary_to_dict(summary: ContextSummary) -> Dict[str, Any]:
    return {
        "session_count": summary.session_count,
        "completed_session_count": summary.completed_session_count,
        "turn_count": summary.turn_count,
        "answered_turn_count": summary.answered_turn_count,
        "evaluation_count": summary.evaluation_count,
        "low_score_evaluation_count": summary.low_score_evaluation_count,
        "question_metadata_count": summary.question_metadata_count,
        "avg_score": summary.avg_score,
        "has_resume": summary.has_resume,
        "has_any_evidence": summary.has_any_evidence,
        "resume_gap_signal_count": summary.resume_gap_signal_count,
    }


def _dimension_to_dict(stat: DimensionStat) -> Dict[str, Any]:
    return {
        "dimension": stat.dimension,
        "avg_score": stat.avg_score,
        "evaluation_count": stat.evaluation_count,
        "low_score_count": stat.low_score_count,
        "severity": stat.severity,
        "evidence_samples": list(stat.evidence_samples or []),
    }


__all__ = [
    "SYSTEM_PROMPT_PLAN",
    "SYSTEM_PROMPT_MILESTONE",
    "SYSTEM_PROMPT_TASK",
    "SYSTEM_PROMPT_RECOMMENDATION",
    "USER_PROMPT_PLAN_TEMPLATE",
    "USER_PROMPT_MILESTONE_TEMPLATE",
    "USER_PROMPT_TASK_TEMPLATE",
    "USER_PROMPT_RECOMMENDATION_TEMPLATE",
    "PlanPrompt",
    "build_plan_prompt",
    "build_milestone_prompt",
    "build_task_prompt",
    "build_recommendation_prompt",
    "serialize_context_for_llm",
]

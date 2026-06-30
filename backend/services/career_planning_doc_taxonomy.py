"""Structured taxonomy for career-planning document sections.

Phase 4 establishes the section-level tag mapping that lets the
recommender score a document section against a user profile and a task
plan. The taxonomy is intentionally side-effect free: it returns a
:class:`SectionTaxonomy` dataclass with three orthogonal label sets
(``skill_tags`` aligned with :data:`DIMENSION_LIBRARY`,
``gap_tags`` aligned with career-gap keys used by the LLM/blueprint
pipeline, and ``task_types`` aligned with the enum on
:class:`TaskDraft.task_type`).

Sections not present in :data:`SECTION_TAXONOMY` return
``tag_known=False`` from :func:`get_section_taxonomy`; the recommender
will keep the section searchable via its free-form ``tags`` but will
not include it in the gap-driven ranking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, List, Optional, Tuple

from services.career_planning_skills import DIMENSION_LIBRARY


# ---------------------------------------------------------------------------
# Section taxonomy — heading → structured label sets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SectionTaxonomy:
    """Structured labels attached to a document section."""

    skill_tags: Tuple[str, ...] = ()
    gap_tags: Tuple[str, ...] = ()
    task_types: Tuple[str, ...] = ()
    # When True the section had no pre-defined mapping; the recommender
    # will treat it as "searchable only" and skip it in the gap-driven
    # ranking. This keeps unknown sections from being silently zero-scored.
    tag_known: bool = True


# Heading-keyed taxonomy table. Keys are stripped (whitespace trimmed) to
# tolerate small encoding differences in ``career_planning_docs.json``.
_SECTION_TAXONOMY_RAW: Dict[str, Dict[str, Tuple[str, ...]]] = {
    # job-seeking-guide
    "🔍 职业定位：找到你的核心竞争力": {
        "skill_tags": ("学习能力", "沟通表达"),
        "gap_tags": ("career_direction", "self_positioning"),
        "task_types": ("course", "skill_practice"),
    },
    "📄 简历优化：让HR一眼看上你": {
        "skill_tags": ("沟通表达", "工程实践"),
        "gap_tags": ("resume_star", "resume_quantification", "resume_layout"),
        "task_types": ("project", "skill_practice"),
    },
    "💬 面试技巧：把面试官变成你的支持者": {
        "skill_tags": ("沟通表达", "问题定位"),
        "gap_tags": ("interview_expression", "behavioral_star", "question_framing"),
        "task_types": ("interview_prep", "skill_practice"),
    },
    "💰 offer谈判：不要在钱上吃亏": {
        "skill_tags": ("沟通表达", "学习能力"),
        "gap_tags": ("offer_negotiation", "salary_research"),
        "task_types": ("course", "interview_prep"),
    },
    # ai-interview-master
    "🤖 认识AI面试：不是替代而是赋能": {
        "skill_tags": ("学习能力",),
        "gap_tags": ("ai_interview_understanding", "platform_awareness"),
        "task_types": ("course",),
    },
    "⚙️ 面试设置：找到最适合你的配置": {
        "skill_tags": ("工程实践", "学习能力"),
        "gap_tags": ("interview_setup", "difficulty_selection"),
        "task_types": ("skill_practice", "course"),
    },
    "📊 解读报告：把反馈变成行动": {
        "skill_tags": ("学习能力", "问题定位"),
        "gap_tags": ("report_interpretation", "gap_identification", "action_planning"),
        "task_types": ("course", "skill_practice"),
    },
    "📈 持续迭代：从青铜到王者的进化之路": {
        "skill_tags": ("学习能力", "沟通表达"),
        "gap_tags": ("iteration_planning", "feedback_loop", "habit_building"),
        "task_types": ("course", "skill_practice"),
    },
    # tech-career-roadmap
    "🛠️ 技术栈建设：打造你的核心竞争力": {
        "skill_tags": ("系统设计", "工程实践", "性能优化"),
        "gap_tags": ("tech_stack", "system_design_basics", "performance_fundamentals"),
        "task_types": ("course", "project", "skill_practice"),
    },
    "📂 项目经验：让你的简历会说话": {
        "skill_tags": ("项目经验", "工程实践", "沟通表达"),
        "gap_tags": ("project_narrative", "project_depth", "star_format"),
        "task_types": ("project", "skill_practice"),
    },
    "🎯 面试冲刺：从练习到offer": {
        "skill_tags": ("问题定位", "沟通表达", "系统设计"),
        "gap_tags": ("interview_expression", "system_design_practice", "mock_interview"),
        "task_types": ("interview_prep", "skill_practice"),
    },
    "🚀 职业跃迁：从执行到架构的成长曲线": {
        "skill_tags": ("系统设计", "学习能力", "沟通表达"),
        "gap_tags": ("career_direction", "tech_lead_transition", "offer_negotiation"),
        "task_types": ("course", "interview_prep"),
    },
}


def _normalise_heading(heading: str) -> str:
    """Normalise a heading for taxonomy lookup.

    Strips whitespace and a few common decorative emojis used as section
    prefixes in the JSON so the recommender is robust against minor
    copy edits. The match is intentionally fuzzy at the prefix level
    only — we want at most one taxonomy entry per section.
    """
    text = (heading or "").strip()
    # Strip the " 1️⃣ " style emoji at the very start to tolerate
    # editor re-pastes. Keep the rest of the heading intact.
    if len(text) >= 2 and text[0].isascii() is False and text[1] == " ":
        text = text[2:].lstrip()
    return text


# Pre-compute the stripped heading table once at import time.
SECTION_TAXONOMY: Dict[str, SectionTaxonomy] = {}
for _heading, _tags in _SECTION_TAXONOMY_RAW.items():
    SECTION_TAXONOMY[_normalise_heading(_heading)] = SectionTaxonomy(
        skill_tags=tuple(_tags.get("skill_tags") or ()),
        gap_tags=tuple(_tags.get("gap_tags") or ()),
        task_types=tuple(_tags.get("task_types") or ()),
    )


def get_section_taxonomy(heading: str) -> SectionTaxonomy:
    """Return the structured taxonomy for a section heading.

    Falls back to an empty :class:`SectionTaxonomy` with
    ``tag_known=False`` when the heading has no pre-defined mapping.
    """
    key = _normalise_heading(heading)
    if key in SECTION_TAXONOMY:
        return SECTION_TAXONOMY[key]
    # Tolerate minor emoji / whitespace differences by trying a few
    # candidate strip strategies before giving up.
    for candidate in _candidate_heading_keys(key):
        if candidate in SECTION_TAXONOMY:
            return SECTION_TAXONOMY[candidate]
    return SectionTaxonomy(tag_known=False)


def _candidate_heading_keys(heading: str) -> List[str]:
    """Return candidate heading keys to try in order of decreasing strictness."""
    keys: List[str] = []
    text = heading.strip()
    if not text:
        return keys
    # Drop the "：" part if present (the part after the colon is variable)
    if "：" in text:
        keys.append(text.split("：")[0].strip() + "：")
    # Drop everything after the first colon
    if ":" in text:
        head = text.split(":")[0].strip()
        keys.append(head)
    # Drop the trailing colon variant
    for variant in list(keys):
        if variant.endswith("："):
            keys.append(variant.rstrip("："))
    return keys


def known_skill_tags() -> FrozenSet[str]:
    """Return the set of skill tags used by the taxonomy (intersected with DIMENSION_LIBRARY)."""
    collected: set[str] = set()
    for tax in SECTION_TAXONOMY.values():
        collected.update(tax.skill_tags)
    return frozenset(collected & set(DIMENSION_LIBRARY))


def known_gap_tags() -> FrozenSet[str]:
    """Return the set of gap keys used by the taxonomy."""
    collected: set[str] = set()
    for tax in SECTION_TAXONOMY.values():
        collected.update(tax.gap_tags)
    return frozenset(collected)


def known_task_types() -> FrozenSet[str]:
    """Return the set of task types used by the taxonomy."""
    collected: set[str] = set()
    for tax in SECTION_TAXONOMY.values():
        collected.update(tax.task_types)
    return frozenset(collected)

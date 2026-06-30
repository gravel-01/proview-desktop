"""Reusable career-planning domain skills.

These pure-function skills compose the long/short-term memory of the
career-planning subsystem. They are deliberately side-effect free and
deterministic, so they can be:

1. unit-tested in isolation
2. re-used by ``build_career_context`` (the context aggregator)
3. fed into an LLM prompt during phase 3

The skills mirror the building blocks called out in the diagnostic
handoff (see ``career-planning-diagnostic-handoff.md`` §五):

- compute dimension statistics from per-turn evaluations
- derive gap severity (high/medium/low/none)
- extract resume-side gap signals via lightweight keyword matching
- build evidence-aware task templates
- sample top-N evidence and suggestions
- render a compact text summary for the LLM prompt context
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# Skill 1: dimension statistics
# ---------------------------------------------------------------------------

# 7 evaluation dimensions, aligned with ``services/question_metadata_extractor``.
DIMENSION_LIBRARY: Tuple[str, ...] = (
    "性能优化",
    "系统设计",
    "项目经验",
    "问题定位",
    "工程实践",
    "沟通表达",
    "学习能力",
)

# Threshold below which a single-turn evaluation counts as "low".
LOW_SCORE_THRESHOLD = 7

# Severity thresholds based on the average score and sample count.
SEVERITY_HIGH_AVG = 6.0
SEVERITY_MEDIUM_AVG = 7.0
SEVERITY_LOW_AVG = 8.0


@dataclass(frozen=True)
class DimensionStat:
    """Aggregated statistics for a single evaluation dimension."""

    dimension: str
    evaluation_count: int
    avg_score: float
    min_score: int
    max_score: int
    low_score_count: int
    severity: str
    evidence_samples: List[str]
    suggestion_samples: List[str]
    sessions_observed: int


def compute_dimension_stats(
    evaluations: Sequence[Dict[str, object]],
    *,
    evidence_limit: int = 3,
    suggestion_limit: int = 3,
    low_threshold: int = LOW_SCORE_THRESHOLD,
) -> List[DimensionStat]:
    """Group per-turn evaluations by ``dimension`` and compute statistics.

    ``evaluations`` follows the shape returned by
    ``DataServiceClient.list_turn_evaluations()``:

    .. code-block:: python

        {
            "session_id": "...",
            "turn_id": "...",
            "turn_no": 3,
            "dimension": "系统设计",
            "score": 5,
            "pass_level": "fail",
            "evidence": "回答缺少容量估算...",
            "suggestion": "下次先说取舍...",
        }

    The returned list is ordered by ``severity`` (high -> none) then
    ``avg_score`` ascending, which makes it directly usable as the
    ``gap_dimensions`` payload for the frontend.
    """
    if not evaluations:
        return []

    by_dimension: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for item in evaluations:
        dimension = str(item.get("dimension") or "").strip()
        if not dimension:
            continue
        by_dimension[dimension].append(item)

    stats: List[DimensionStat] = []
    for dimension, items in by_dimension.items():
        scores = [int(item.get("score") or 0) for item in items]
        if not scores:
            continue
        avg = sum(scores) / len(scores)
        low_count = sum(1 for s in scores if s < low_threshold)
        sessions = {str(item.get("session_id") or "") for item in items}
        sessions.discard("")
        evidence_samples = _sample_strings(items, "evidence", evidence_limit)
        suggestion_samples = _sample_strings(items, "suggestion", suggestion_limit)
        severity = derive_gap_severity(avg, len(items))
        stats.append(
            DimensionStat(
                dimension=dimension,
                evaluation_count=len(items),
                avg_score=round(avg, 2),
                min_score=min(scores),
                max_score=max(scores),
                low_score_count=low_count,
                severity=severity,
                evidence_samples=evidence_samples,
                suggestion_samples=suggestion_samples,
                sessions_observed=len(sessions),
            )
        )

    stats.sort(key=_severity_sort_key)
    return stats


def derive_gap_severity(avg_score: float, evaluation_count: int) -> str:
    """Map (avg_score, sample_size) to a severity label.

    The rule prioritises coverage: a single low-score evaluation does not
    auto-become a high-severity gap. Larger sample sizes with low averages
    are weighted more heavily.

    Thresholds
    ----------
    - ``avg < 6.0`` and ``count >= 2``       → ``high``
    - ``avg < 6.0``                          → ``medium``  (single low sample)
    - ``6.0 <= avg < 7.0`` and ``count >= 2`` → ``high``
    - ``6.0 <= avg < 7.0``                   → ``medium``
    - ``7.0 <= avg < 8.0``                   → ``low``
    - ``avg >= 8.0``                         → ``none``
    """
    if evaluation_count <= 0:
        return "none"
    if avg_score < SEVERITY_HIGH_AVG:
        return "high" if evaluation_count >= 2 else "medium"
    if avg_score < SEVERITY_MEDIUM_AVG:
        return "high" if evaluation_count >= 2 else "medium"
    if avg_score < SEVERITY_LOW_AVG:
        return "low"
    return "none"


def _severity_sort_key(stat: DimensionStat) -> Tuple[int, float]:
    severity_rank = {"high": 0, "medium": 1, "low": 2, "none": 3}.get(stat.severity, 4)
    return (severity_rank, stat.avg_score)


# ---------------------------------------------------------------------------
# Skill 2: resume gap signals
# ---------------------------------------------------------------------------

# Lightweight keyword library mapping common target roles to the
# technologies / concepts a strong resume usually mentions. We keep this
# table local to avoid coupling to the RAG document store.
RESUME_GAP_LIBRARY: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "前端": {
        "skill_groups": (
            ("性能优化", "webpack", "vite", "性能", "首屏", "白屏"),
            ("系统设计", "微前端", "组件库", "工程化", "ssr", "spa"),
            ("工程实践", "单元测试", "jest", "vitest", "ci", "e2e"),
        ),
    },
    "后端": {
        "skill_groups": (
            ("系统设计", "高并发", "微服务", "rpc", "消息队列", "分布式"),
            ("性能优化", "性能", "优化", "压测", "瓶颈", "缓存"),
            ("问题定位", "故障", "监控", "链路", "根因", "排查"),
            ("工程实践", "ci", "cd", "单元测试", "重构", "代码评审"),
        ),
    },
    "java": {
        "skill_groups": (
            ("系统设计", "jvm", "spring", "高并发", "微服务"),
            ("性能优化", "jvm 调优", "gc", "性能", "压测"),
            ("问题定位", "arthas", "故障", "监控"),
        ),
    },
    "python": {
        "skill_groups": (
            ("系统设计", "django", "flask", "fastapi", "celery"),
            ("性能优化", "asyncio", "性能", "瓶颈"),
            ("工程实践", "pytest", "ci", "重构"),
        ),
    },
    "数据": {
        "skill_groups": (
            ("系统设计", "数据仓库", "数仓", "olap", "oltp"),
            ("性能优化", "sql 优化", "查询优化", "索引"),
            ("工程实践", "airflow", "spark", "hive"),
        ),
    },
    "算法": {
        "skill_groups": (
            ("学习能力", "论文", "复现", "原理"),
            ("工程实践", "tensorflow", "pytorch", "cuda", "onnx"),
        ),
    },
    "测试": {
        "skill_groups": (
            ("工程实践", "自动化测试", "接口测试", "ui 测试", "性能测试"),
            ("问题定位", "缺陷", "根因", "复现"),
        ),
    },
    "运维": {
        "skill_groups": (
            ("系统设计", "k8s", "kubernetes", "docker", "服务网格"),
            ("问题定位", "故障", "监控", "告警", "根因"),
            ("工程实践", "ci", "cd", "基础设施即代码", "terraform"),
        ),
    },
    "产品": {
        "skill_groups": (
            ("沟通表达", "需求评审", "业务", "跨团队"),
            ("项目经验", "项目", "结果", "数据"),
        ),
    },
}

# Generic signals that always count as gaps when the resume is missing
# any concrete project terms. These are evaluated as a fallback.
GENERIC_RESUME_GAP_SIGNALS: Tuple[str, ...] = (
    "项目结果量化",
    "技术难点与解决",
    "代表性项目",
    "可讲述的项目故事",
)


def extract_resume_gap_signals(
    ocr_text: str,
    target_role: str,
    *,
    max_signals: int = 5,
) -> List[str]:
    """Heuristically detect resume gaps relative to ``target_role``.

    Returns a list of short human-readable gap labels (e.g. "k8s 经验",
    "性能优化案例"). The detector is intentionally lightweight: it only
    scans for known keyword groups and never mutates the input.
    """
    if not ocr_text:
        return []

    text = ocr_text.lower()
    signals: List[str] = []

    # Very short OCR text usually means OCR did not run or the resume is
    # image-only. Surface a dedicated signal and stop scanning so we do not
    # produce noisy "missing keyword" labels based on < 120 characters.
    if len(ocr_text.strip()) < 120:
        return ["简历正文过短（疑似扫描件无 OCR）"]

    role_libraries: List[Tuple[str, Dict[str, Tuple[str, ...]]]] = []
    role = (target_role or "").strip().lower()
    for key, library in RESUME_GAP_LIBRARY.items():
        if key in role or key in (target_role or "").lower():
            role_libraries.append((key, library))

    # If no specific role matched, fall back to "后端 + 前端" generic checks
    # to avoid producing zero signal on unknown roles.
    if not role_libraries:
        role_libraries = [("后端", RESUME_GAP_LIBRARY["后端"])]

    seen: set[str] = set()
    for _, library in role_libraries:
        for group in library.get("skill_groups", ()):
            # Each group is (dimension, keyword, keyword, ...).
            if len(group) < 2:
                continue
            dimension = str(group[0])
            keywords = tuple(str(item) for item in group[1:])
            hit = False
            for keyword in keywords:
                if keyword.lower() in text or keyword in ocr_text:
                    hit = True
                    break
            if hit:
                continue
            # None of the keywords present -> record the gap
            label = _format_gap_label(dimension, keywords)
            if label not in seen:
                seen.add(label)
                signals.append(label)
            if len(signals) >= max_signals:
                return signals

    if not signals:
        for label in GENERIC_RESUME_GAP_SIGNALS:
            if label not in seen:
                seen.add(label)
                signals.append(label)
            if len(signals) >= max_signals:
                break

    return signals[:max_signals]


def _format_gap_label(dimension: str, keywords: Tuple[str, ...]) -> str:
    sample = " / ".join(keywords[:3])
    return f"{dimension}相关:{sample}"


# ---------------------------------------------------------------------------
# Skill 3: build evidence-aware task templates
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TaskTemplate:
    title: str
    description: str
    task_type: str
    priority: int
    estimated_effort: str
    success_criteria: str
    gap_key: str


def build_evidence_aware_tasks(
    *,
    target_role: str,
    milestone_index: int,
    gap_dimensions: Sequence[DimensionStat],
    focus_gaps: Sequence[str],
    horizon_months: int,
) -> List[TaskTemplate]:
    """Generate per-milestone tasks driven by real evidence.

    The generator stays within the first stage's per-milestone task budget
    (≤ 4 tasks) to avoid blowing up the plan. When no real evidence is
    available (no gap_dimensions and no focus_gaps), an empty list is
    returned so the caller can fall back to ``_milestone_tasks()``.
    """
    if not focus_gaps and not gap_dimensions:
        return []

    candidates: List[TaskTemplate] = []
    for gap in gap_dimensions:
        if gap.dimension not in focus_gaps:
            continue
        if milestone_index == 1:
            template = _build_foundation_task(gap, target_role, horizon_months)
        elif milestone_index == 2:
            template = _build_application_task(gap, target_role, horizon_months)
        else:
            template = _build_consolidation_task(gap, target_role, horizon_months)
        candidates.append(template)

    if not candidates:
        for gap_key in focus_gaps[:1]:
            template = _build_generic_evidence_task(gap_key, target_role, milestone_index, horizon_months)
            if template:
                candidates.append(template)

    return candidates[:4]


def _build_foundation_task(
    gap: DimensionStat,
    target_role: str,
    horizon_months: int,
) -> TaskTemplate:
    weeks = max(2, horizon_months // 2)
    suggestion = gap.suggestion_samples[0] if gap.suggestion_samples else "结合真题拆解结构化表达"
    return TaskTemplate(
        title=f"补齐 {gap.dimension} 的结构化表达",
        description=(
            f"围绕目标岗位「{target_role}」补齐 {gap.dimension} 相关基础。"
            f"重点：根据近 {gap.evaluation_count} 次面试表现，"
            f"平均分 {gap.avg_score}，最低 {gap.min_score}。"
            f"建议参考：{suggestion[:80]}"
        ),
        task_type="skill_practice",
        priority=5 if gap.severity == "high" else 4,
        estimated_effort=f"{weeks} 周",
        success_criteria=(
            f"用 {gap.dimension} 相关题目模拟练习后，结构化评分稳定 ≥ {max(gap.max_score, 7)}"
        ),
        gap_key=gap.dimension,
    )


def _build_application_task(
    gap: DimensionStat,
    target_role: str,
    horizon_months: int,
) -> TaskTemplate:
    weeks = max(2, horizon_months // 2)
    evidence = gap.evidence_samples[0] if gap.evidence_samples else "近一次面试评价"
    return TaskTemplate(
        title=f"完成 {gap.dimension} 实战复盘",
        description=(
            f"以 {target_role} 真实项目为素材，完成 {gap.dimension} 方向复盘。"
            f"复盘要点：{evidence[:120]}"
        ),
        task_type="project",
        priority=5 if gap.severity in ("high", "medium") else 3,
        estimated_effort=f"{weeks} 周",
        success_criteria=f"沉淀一份 {gap.dimension} 实战复盘文档并能口头讲述",
        gap_key=gap.dimension,
    )


def _build_consolidation_task(
    gap: DimensionStat,
    target_role: str,
    horizon_months: int,
) -> TaskTemplate:
    return TaskTemplate(
        title=f"冲刺 {gap.dimension} 模拟面试",
        description=(
            f"针对 {gap.dimension} 开展至少 2 次完整模拟面试，记录得分和复盘。"
            f"目标：{target_role}。"
        ),
        task_type="interview_prep",
        priority=5,
        estimated_effort=f"{horizon_months // 2} 周",
        success_criteria=f"最近一次 {gap.dimension} 模拟面试评分 ≥ 8",
        gap_key=gap.dimension,
    )


def _build_generic_evidence_task(
    gap_key: str,
    target_role: str,
    milestone_index: int,
    horizon_months: int,
) -> Optional[TaskTemplate]:
    if milestone_index == 1:
        return TaskTemplate(
            title=f"梳理 {gap_key} 学习路径",
            description=f"围绕目标岗位「{target_role}」梳理 {gap_key} 的学习路径。",
            task_type="skill_practice",
            priority=4,
            estimated_effort=f"{horizon_months} 周",
            success_criteria=f"完成 {gap_key} 学习清单并自评可复述",
            gap_key=gap_key,
        )
    if milestone_index == 2:
        return TaskTemplate(
            title=f"{gap_key} 项目实战",
            description=f"用 1 个完整项目演练 {gap_key}，沉淀可讲述材料。",
            task_type="project",
            priority=4,
            estimated_effort=f"{horizon_months} 周",
            success_criteria="产出可讲述的实战故事",
            gap_key=gap_key,
        )
    return TaskTemplate(
        title=f"{gap_key} 面试冲刺",
        description=f"通过模拟面试验证 {gap_key} 掌握度。",
        task_type="interview_prep",
        priority=4,
        estimated_effort=f"{horizon_months // 2} 周",
        success_criteria="模拟面试评价稳定",
        gap_key=gap_key,
    )


# ---------------------------------------------------------------------------
# Skill 4: sample top-N evidence / suggestions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceSample:
    session_id: str
    turn_id: str
    turn_no: int
    dimension: str
    score: int
    quote: str


@dataclass(frozen=True)
class SuggestionSample:
    session_id: str
    turn_id: str
    turn_no: int
    dimension: str
    text: str


def select_top_evidence(
    evaluations: Sequence[Dict[str, object]],
    *,
    n: int = 5,
    prefer_low_score: bool = True,
) -> List[EvidenceSample]:
    """Pick up to ``n`` representative evidence items.

    ``prefer_low_score=True`` keeps the most useful items for gap
    remediation: lower scores rank first. Set it to ``False`` to focus on
    strengths instead.
    """
    candidates: List[EvidenceSample] = []
    for item in evaluations:
        evidence = str(item.get("evidence") or "").strip()
        if not evidence:
            continue
        candidates.append(
            EvidenceSample(
                session_id=str(item.get("session_id") or ""),
                turn_id=str(item.get("turn_id") or ""),
                turn_no=int(item.get("turn_no") or 0),
                dimension=str(item.get("dimension") or ""),
                score=int(item.get("score") or 0),
                quote=_truncate(evidence, 120),
            )
        )

    candidates.sort(key=lambda e: (e.score if prefer_low_score else -e.score, e.turn_no))
    return candidates[:n]


def select_top_suggestions(
    evaluations: Sequence[Dict[str, object]],
    *,
    n: int = 5,
) -> List[SuggestionSample]:
    """Pick up to ``n`` representative suggestions, preferring low scores."""
    candidates: List[SuggestionSample] = []
    for item in evaluations:
        suggestion = str(item.get("suggestion") or "").strip()
        if not suggestion:
            continue
        candidates.append(
            SuggestionSample(
                session_id=str(item.get("session_id") or ""),
                turn_id=str(item.get("turn_id") or ""),
                turn_no=int(item.get("turn_no") or 0),
                dimension=str(item.get("dimension") or ""),
                text=_truncate(suggestion, 160),
            )
        )

    score_lookup: Dict[Tuple[str, str], int] = {}
    for item in evaluations:
        key = (str(item.get("turn_id") or ""), str(item.get("dimension") or ""))
        score_lookup[key] = int(item.get("score") or 0)

    def _sort_key(sample: SuggestionSample) -> Tuple[int, int]:
        score = score_lookup.get((sample.turn_id, sample.dimension), 0)
        return (score, sample.turn_no)

    candidates.sort(key=_sort_key)
    return candidates[:n]


# ---------------------------------------------------------------------------
# Skill 5: compact text summary (for LLM prompt context in phase 3)
# ---------------------------------------------------------------------------

def summarize_context_for_llm(
    context_summary: Dict[str, object],
    dimension_stats: Sequence[DimensionStat],
    *,
    max_chars: int = 1200,
) -> str:
    """Render a short Markdown-ish summary suitable for an LLM prompt.

    This skill is intentionally simple in phase 2. It produces a
    deterministic string with three sections: profile, gap summary,
    and evidence highlights. The output is truncated to ``max_chars``.
    """
    parts: List[str] = []
    parts.append("# Career Planning Context")
    parts.append("## 数据概况")
    for key, value in context_summary.items():
        parts.append(f"- {key}: {value}")

    if dimension_stats:
        parts.append("## 维度表现")
        for stat in dimension_stats[:6]:
            parts.append(
                f"- {stat.dimension}: avg={stat.avg_score}, n={stat.evaluation_count}, "
                f"low={stat.low_score_count}, severity={stat.severity}"
            )

    text = "\n".join(parts)
    return _truncate(text, max_chars)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------

def _sample_strings(items: Sequence[Dict[str, object]], key: str, limit: int) -> List[str]:
    out: List[str] = []
    for item in items:
        value = str(item.get(key) or "").strip()
        if not value:
            continue
        if value in out:
            continue
        out.append(_truncate(value, 120))
        if len(out) >= limit:
            break
    return out


def _truncate(value: str, limit: int) -> str:
    text = value.strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


_RE_WHITESPACE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Public helper for tests: collapse whitespace runs."""
    return _RE_WHITESPACE.sub(" ", value or "").strip()


def iter_dimensions() -> Iterable[str]:
    """Iterate over the canonical evaluation dimension library."""
    return iter(DIMENSION_LIBRARY)


# ---------------------------------------------------------------------------
# Phase 4 skills: resource closure (task ↔ doc section)
# ---------------------------------------------------------------------------

# When the recommender has no profile gap data (empty / fallback mode),
# it falls back to these "evergreen" gap tags so the doc section list
# is never empty. Tags chosen from the doc taxonomy's known gap_tags.
DEFAULT_FALLBACK_GAP_TAGS: Tuple[str, ...] = (
    "career_direction",
    "resume_star",
    "interview_expression",
    "report_interpretation",
    "iteration_planning",
)

# Heavily-weighted keyword sets for the optional target-role bonus
# (see :func:`score_resource_match`). The match is intentionally
# substring-based so partial keywords ("vue" matches "vue 前端") count.
DEFAULT_TARGET_ROLE_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "前端": ("前端", "vue", "react", "typescript", "web", "css"),
    "后端": ("后端", "java", "golang", "python", "服务", "数据库"),
    "数据": ("数据", "sql", "数仓", "报表", "数据湖", "etl"),
    "ai": ("ai", "算法", "机器学习", "深度学习", "大模型", "nlp"),
    "产品": ("产品", "pm", "运营", "用户增长", "需求", "迭代"),
    "测试": ("测试", "qa", "自动化", "接口测试", "性能测试"),
}


def _target_role_keyword_hits(target_role: str) -> Tuple[str, ...]:
    """Return a tuple of taxonomy categories that ``target_role`` matches."""
    if not target_role:
        return ()
    text = str(target_role).lower()
    hits: List[str] = []
    for category, keywords in DEFAULT_TARGET_ROLE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                hits.append(category)
                break
    return tuple(hits)


@dataclass(frozen=True)
class ResourceMatch:
    """One ranked section produced by :func:`score_resource_match`."""

    doc_id: str
    section_idx: int
    score: float
    reason: str
    related_task_ids: Tuple[int, ...] = ()


def score_resource_match(
    section: Dict[str, Any],
    *,
    user_gap_keys: Sequence[str] = (),
    user_skill_keys: Sequence[str] = (),
    user_task_types: Sequence[str] = (),
    target_role: str = "",
    already_recommended_doc_ids: Sequence[str] = (),
    already_completed_doc_ids: Sequence[str] = (),
) -> float:
    """Compute a recommendation score in [0, 1] for a single section.

    The function is pure: it does not touch the database and can be
    unit-tested in isolation. The weighting intentionally mirrors the
    diagnostic handoff's P1 ask: "推荐资源要基于 profile / gap / task /
    target_role，而不是当前阅读文档的 tags 相似度"。
    """
    if not section.get("tag_known", False):
        return 0.0  # unknown sections only surface in free-text search
    gap_set = {str(g) for g in (user_gap_keys or [])}
    skill_set = {str(s) for s in (user_skill_keys or [])}
    type_set = {str(t) for t in (user_task_types or [])}
    if not (gap_set or skill_set or type_set):
        return 0.0

    section_gaps = {str(g) for g in (section.get("gap_tags") or [])}
    section_skills = {str(s) for s in (section.get("skill_tags") or [])}
    section_types = {str(t) for t in (section.get("task_types") or [])}

    gap_overlap = section_gaps & gap_set
    skill_overlap = section_skills & skill_set
    type_overlap = section_types & type_set
    if not (gap_overlap or skill_overlap or type_overlap):
        return 0.0

    score = 0.0
    score += 2.0 * len(gap_overlap)
    score += 1.0 * len(skill_overlap)
    score += 0.5 * len(type_overlap)
    if section.get("doc_is_featured"):
        score += 0.3
    if str(section.get("doc_id") or "") in set(already_recommended_doc_ids):
        score -= 0.5
    if str(section.get("doc_id") or "") in set(already_completed_doc_ids):
        score -= 1.0
    # Optional target-role bonus
    if target_role:
        hits = _target_role_keyword_hits(target_role)
        if hits and any(kw in (section.get("doc_tags") or []) for kw in ("面试", "简历", "offer")):
            score += 0.2 * len(hits)

    # Normalise to [0, 1] by clamping at 4.0 (two gap hits + one skill
    # + one type + featured). The clamp makes the score easy to filter
    # at a fixed threshold (>= 0.3) without weird float comparisons.
    if score < 0:
        return 0.0
    if score > 4.0:
        score = 4.0
    return round(score / 4.0, 3)


def explain_section_match(
    section: Dict[str, Any],
    *,
    user_gap_keys: Sequence[str] = (),
    user_skill_keys: Sequence[str] = (),
    user_task_types: Sequence[str] = (),
) -> str:
    """Return a short Chinese sentence explaining why a section matched."""
    parts: List[str] = []
    gap_overlap = set(section.get("gap_tags") or []) & set(user_gap_keys or [])
    skill_overlap = set(section.get("skill_tags") or []) & set(user_skill_keys or [])
    type_overlap = set(section.get("task_types") or []) & set(user_task_types or [])
    if gap_overlap:
        parts.append(f"覆盖你的 gap: { ' / '.join(sorted(gap_overlap)) }")
    if skill_overlap:
        parts.append(f"匹配能力维度 { ' / '.join(sorted(skill_overlap)) }")
    if type_overlap:
        parts.append(f"适用于 { ' / '.join(sorted(type_overlap)) } 类型任务")
    if not parts:
        return "与你当前规划相关"
    return "；".join(parts)


def collect_resource_recommendations(
    sections: Sequence[Dict[str, Any]],
    *,
    user_gap_keys: Sequence[str] = (),
    user_skill_keys: Sequence[str] = (),
    user_task_types: Sequence[str] = (),
    target_role: str = "",
    already_recommended_doc_ids: Sequence[str] = (),
    already_completed_doc_ids: Sequence[str] = (),
    limit: int = 4,
    score_threshold: float = 0.3,
    doc_per_doc_limit: int = 2,
) -> List[Dict[str, Any]]:
    """Rank sections against the user context and return top N.

    The function is the single seam between the service layer and the
    resource recommender: the service feeds in the catalogue
    (``sections``) plus the user-derived keys, and the function returns
    a list of {doc_id, section_idx, score, reason} dicts sorted by
    descending score.
    """
    if not sections:
        return []
    scored: List[Tuple[float, int, Dict[str, Any]]] = []
    for idx, section in enumerate(sections):
        score = score_resource_match(
            section,
            user_gap_keys=user_gap_keys,
            user_skill_keys=user_skill_keys,
            user_task_types=user_task_types,
            target_role=target_role,
            already_recommended_doc_ids=already_recommended_doc_ids,
            already_completed_doc_ids=already_completed_doc_ids,
        )
        if score < score_threshold:
            continue
        scored.append((score, idx, section))
    scored.sort(key=lambda item: (-item[0], item[1]))

    # Apply the per-doc cap so a single document does not dominate.
    per_doc_count: Dict[str, int] = {}
    out: List[Dict[str, Any]] = []
    for score, _, section in scored:
        doc_id = str(section.get("doc_id") or "")
        if per_doc_count.get(doc_id, 0) >= doc_per_doc_limit:
            continue
        per_doc_count[doc_id] = per_doc_count.get(doc_id, 0) + 1
        out.append(
            {
                "doc_id": doc_id,
                "doc_title": str(section.get("doc_title") or ""),
                "section_idx": int(section.get("section_idx") or 0),
                "section_heading": str(section.get("section_heading") or ""),
                "section_bullets": list(section.get("section_bullets") or []),
                "section_action_items": list(section.get("section_action_items") or []),
                "score": float(score),
                "reason": explain_section_match(
                    section,
                    user_gap_keys=user_gap_keys,
                    user_skill_keys=user_skill_keys,
                    user_task_types=user_task_types,
                ),
                "tag_known": bool(section.get("tag_known")),
            }
        )
        if len(out) >= limit:
            break
    return out


def tag_resource_to_task(
    task: Dict[str, Any],
    sections: Sequence[Dict[str, Any]],
    *,
    top_k: int = 2,
    score_threshold: float = 0.3,
    target_role: str = "",
) -> List[Dict[str, Any]]:
    """Return up to ``top_k`` {doc_id, section_idx, reason} refs for a task.

    The function is what the service layer calls when persisting a new
    plan: every task gets a small set of document sections that explain
    *how* to do the task. Sections whose ``gap_tags`` intersect the
    task's ``gap_key`` rank highest; sections whose ``task_types`` match
    the task's ``task_type`` get a small bonus.
    """
    if not sections or not task:
        return []
    user_gap_keys = [str(task.get("gap_key") or "")]
    user_skill_keys = [
        str(d) for d in (task.get("focus_dimensions") or []) if d
    ]  # optional
    user_task_types = [str(task.get("task_type") or "")]
    ranked = collect_resource_recommendations(
        sections,
        user_gap_keys=user_gap_keys,
        user_skill_keys=user_skill_keys,
        user_task_types=user_task_types,
        target_role=target_role,
        limit=top_k,
        score_threshold=score_threshold,
    )
    return [
        {
            "doc_id": r["doc_id"],
            "section_idx": int(r["section_idx"]),
            "reason": r["reason"],
            "score": r["score"],
        }
        for r in ranked
    ]


def apply_read_event_to_progress(
    *,
    current_progress: float,
    completed: bool,
    increment: float = 10.0,
) -> float:
    """Compute the new task progress after a doc read event.

    The function is deliberately tiny but exposed as a skill so the
    SkillRegistry records every invocation: this lets the recommender
    learn over time which (doc section, increment) pairings actually
    move the needle.
    """
    if not completed:
        return float(current_progress)
    delta = float(increment or 0)
    new_value = float(current_progress or 0) + delta
    if new_value > 100.0:
        new_value = 100.0
    if new_value < 0.0:
        new_value = 0.0
    return new_value

from __future__ import annotations

import re
from typing import Dict, List, Optional


DEFAULT_DIMENSION = {
    "name": "综合表现",
    "rubric": "结合本轮问题，评估候选人的表达、逻辑、经验真实性和岗位匹配度。",
    "pass_criteria": "回答能够正面回应问题，并给出清晰事实、过程或例子。",
    "expected_signals": ["正面回应问题", "事实清晰", "表达有条理"],
}


class QuestionMetadataExtractor:
    """Build deterministic question metadata without exposing JSON to candidates."""

    KEYWORD_RULES = [
        (
            "性能优化",
            ("性能", "优化", "慢", "耗时", "延迟", "吞吐", "qps", "响应", "缓存", "瓶颈"),
            "是否能描述问题背景、瓶颈定位、优化动作和量化结果。",
            "至少说明一个明确瓶颈、一个优化动作和一个结果指标。",
            ["量化指标", "定位过程", "优化前后对比"],
        ),
        (
            "系统设计",
            ("系统设计", "架构", "高并发", "可用性", "扩展", "一致性", "降级", "限流", "分布式"),
            "是否能拆解系统边界、数据流、关键瓶颈、扩展性和可靠性取舍。",
            "能说明核心模块、关键数据流和至少一个技术取舍。",
            ["模块拆分", "数据流", "权衡取舍"],
        ),
        (
            "项目经验",
            ("项目", "经历", "负责", "实习", "上线", "落地", "贡献", "业务", "需求"),
            "是否能说明项目背景、个人职责、技术方案、难点和结果。",
            "能够明确说明个人贡献、技术动作和项目结果。",
            ["个人职责", "技术难点", "结果影响"],
        ),
        (
            "问题定位",
            ("排查", "定位", "故障", "bug", "异常", "线上", "日志", "监控", "根因"),
            "是否能给出清晰的问题定位路径、证据和修复验证过程。",
            "能够说明定位步骤、关键证据和最终修复方式。",
            ["定位路径", "关键证据", "验证闭环"],
        ),
        (
            "工程实践",
            ("测试", "部署", "ci", "cd", "代码质量", "重构", "规范", "协作", "评审"),
            "是否具备工程化意识，包括质量保障、可维护性和团队协作。",
            "能够说明至少一个工程实践动作及其收益。",
            ["质量保障", "可维护性", "协作意识"],
        ),
        (
            "沟通表达",
            ("自我介绍", "介绍一下", "讲讲自己", "表达", "沟通", "团队", "冲突", "协作"),
            "是否能结构化表达经历、动机、优势和协作方式。",
            "表达清晰、有重点，并能提供具体例子。",
            ["结构清晰", "重点明确", "有具体例子"],
        ),
        (
            "学习能力",
            ("学习", "新技术", "成长", "复盘", "为什么", "理解", "原理", "源码"),
            "是否能体现主动学习、抽象理解和复盘改进能力。",
            "能够说明学习路径、理解方法或复盘改进结果。",
            ["主动学习", "原理理解", "复盘改进"],
        ),
    ]

    def build(
        self,
        *,
        question_text: str,
        question_type: str = "",
        source: str = "",
        difficulty: str = "",
        rag_candidates: Optional[List[Dict]] = None,
        previous_metadata: Optional[Dict] = None,
    ) -> Dict:
        text = _normalize(question_text)
        question_type = question_type or _infer_question_type(text)
        allow_rag = question_type != "opening"
        dimensions = self._dimensions_from_rag(text, rag_candidates or []) if allow_rag else []
        metadata_refs = self._metadata_refs_from_rag(text, rag_candidates or []) if allow_rag else []
        resolved_source = source or ""
        if dimensions and metadata_refs:
            resolved_source = "rag"

        if not dimensions and question_type == "followup":
            dimensions = self._dimensions_from_keywords(text)

        if not dimensions and question_type == "followup":
            dimensions = self._dimensions_from_previous(previous_metadata)
            if dimensions:
                resolved_source = "followup"

        if not dimensions:
            dimensions = self._dimensions_from_keywords(text)

        if not dimensions:
            dimensions = [dict(DEFAULT_DIMENSION)]

        return {
            "dimensions": _dedupe_dimensions(dimensions),
            "difficulty": difficulty or "",
            "question_type": question_type,
            "source": resolved_source or ("rag" if metadata_refs else "interviewer_llm"),
            "metadata_refs": metadata_refs,
        }

    def _dimensions_from_rag(self, question_text: str, candidates: List[Dict]) -> List[Dict]:
        result = []
        for item in _rank_rag_candidates(question_text, candidates):
            meta = item.get("metadata") or {}
            dimension = _normalize(meta.get("dimension"))
            if not dimension:
                continue
            rubric_5 = _normalize(meta.get("rubric_5") or meta.get("score_5"))
            rubric_3 = _normalize(meta.get("rubric_3") or meta.get("score_3"))
            rubric_1 = _normalize(meta.get("rubric_1") or meta.get("score_1"))
            result.append(
                {
                    "name": dimension,
                    "rubric": rubric_5 or rubric_3 or f"考察候选人在{dimension}方面的深度、真实性和表达完整度。",
                    "pass_criteria": rubric_3 or rubric_5 or f"能够围绕{dimension}给出清晰、具体、可信的回答。",
                    "excellent_criteria": rubric_5,
                    "fail_criteria": rubric_1,
                    "expected_signals": _signals_for_dimension(dimension),
                }
            )
            if len(result) >= 2:
                break
        return result

    def _metadata_refs_from_rag(self, question_text: str, candidates: List[Dict]) -> List[Dict]:
        refs = []
        for item in _rank_rag_candidates(question_text, candidates):
            item_id = item.get("id")
            if not item_id:
                continue
            refs.append(
                {
                    "type": "rag_question",
                    "id": item_id,
                    "score_hint": _overlap_score(question_text, item.get("document") or item.get("content") or ""),
                    "dimension": (item.get("metadata") or {}).get("dimension") or "",
                }
            )
            if len(refs) >= 2:
                break
        return refs

    def _dimensions_from_previous(self, previous_metadata: Optional[Dict]) -> List[Dict]:
        if not isinstance(previous_metadata, dict):
            return []
        dimensions = previous_metadata.get("dimensions") or []
        result = []
        for item in dimensions:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            copied = dict(item)
            copied["rubric"] = copied.get("rubric") or f"延续考察{copied['name']}相关能力。"
            copied["pass_criteria"] = copied.get("pass_criteria") or "能够补充更具体的事实、过程或取舍。"
            result.append(copied)
        return result[:2]

    def _dimensions_from_keywords(self, question_text: str) -> List[Dict]:
        lowered = question_text.lower()
        result = []
        for name, keywords, rubric, pass_criteria, signals in self.KEYWORD_RULES:
            if any(keyword.lower() in lowered for keyword in keywords):
                result.append(
                    {
                        "name": name,
                        "rubric": rubric,
                        "pass_criteria": pass_criteria,
                        "expected_signals": list(signals),
                    }
                )
        return result[:2]


def _rank_rag_candidates(question_text: str, candidates: List[Dict]) -> List[Dict]:
    scored = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        score = _overlap_score(question_text, item.get("document") or item.get("content") or "")
        if score > 0:
            scored.append((score, item))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in scored]


def _overlap_score(left: str, right: str) -> int:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0
    return len(left_tokens & right_tokens)


def _tokens(value: str) -> set[str]:
    text = _normalize(value).lower()
    words = set(re.findall(r"[a-z0-9_+#.-]{2,}", text))
    chinese_tokens = set()
    for chunk in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        chinese_tokens.add(chunk)
        for size in (2, 3):
            if len(chunk) <= size:
                continue
            chinese_tokens.update(chunk[idx:idx + size] for idx in range(0, len(chunk) - size + 1))
    return words | chinese_tokens


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _dedupe_dimensions(dimensions: List[Dict]) -> List[Dict]:
    result = []
    seen = set()
    for item in dimensions:
        if not isinstance(item, dict):
            continue
        name = _normalize(item.get("name"))
        if not name or name in seen:
            continue
        seen.add(name)
        normalized = dict(item)
        normalized["name"] = name
        normalized.setdefault("expected_signals", _signals_for_dimension(name))
        result.append(normalized)
    return result or [dict(DEFAULT_DIMENSION)]


def _signals_for_dimension(dimension: str) -> List[str]:
    mapping = {
        "性能优化": ["量化指标", "定位过程", "优化取舍"],
        "系统设计": ["模块拆分", "数据流", "可靠性取舍"],
        "项目经验": ["个人职责", "技术难点", "结果影响"],
        "问题定位": ["定位路径", "关键证据", "验证闭环"],
        "工程实践": ["质量意识", "可维护性", "协作方式"],
        "沟通表达": ["结构清晰", "重点明确", "例子具体"],
        "学习能力": ["学习路径", "原理理解", "复盘改进"],
    }
    return mapping.get(dimension, ["事实清晰", "逻辑完整", "表达具体"])


def _infer_question_type(question_text: str) -> str:
    text = _normalize(question_text)
    if any(key in text for key in ("追问", "刚才", "具体", "展开", "进一步")):
        return "followup"
    if any(key in text for key in ("自我介绍", "介绍一下", "讲讲自己")):
        return "opening"
    if any(key in text for key in ("设计", "架构", "系统")):
        return "system_design"
    if any(key in text for key in ("项目", "经历", "负责")):
        return "project_deep_dive"
    return "general"

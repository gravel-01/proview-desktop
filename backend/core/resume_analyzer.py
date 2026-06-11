"""
简历分析模块 — 利用 DeepSeek LLM 对 OCR 原文进行结构化解析与优化建议生成。
不使用 LangChain Agent，直接调用 LLM 客户端。
"""
import json
import re
import uuid
import threading
import queue
from typing import Optional, Generator
from core.llm_client import OpenAICompatibleClient
from core.prompts.resume_parser_prompt import generate_parser_prompt


class ResumeAnalyzer:
    """简历结构化分析与优化建议生成器"""

    def __init__(self, api_key: str, base_url: str, model: str = "deepseek-chat"):
        self.client = OpenAICompatibleClient(model=model, api_key=api_key, base_url=base_url)

    def analyze(self, ocr_text: str, job_title: str = "", report_context: Optional[dict] = None) -> dict:
        """
        输入 OCR 原文，返回结构化分析结果。
        Returns: { "sections": [...], "suggestions": [...], "builder_data": {...} }
        """
        # 第一步：结构化提取
        sections = self._extract_sections(ocr_text)
        # 第二步：生成优化建议
        suggestions = self._generate_suggestions(sections, job_title, report_context=report_context)
        suggestions = self._validate_resume_suggestions(suggestions, sections)
        # 第三步：提取结构化数据 + 自动检测模板
        builder_data = self._extract_builder_data(ocr_text)
        return {"sections": sections, "suggestions": suggestions, "builder_data": builder_data}

    def analyze_stream(self, ocr_text: str, job_title: str = "", report_context: Optional[dict] = None) -> Generator[dict, None, None]:
        """
        流式分析：每个 LLM 调用阶段实时输出思考过程。
        第一步串行（后续步骤依赖），第二步和第三步并行执行加速。
        """
        use_reasoning = hasattr(self.client, 'generate_stream_with_reasoning')

        def _collect_llm(messages) -> str:
            """非流式收集 LLM 输出（用于并行线程）"""
            raw = ""
            if use_reasoning:
                for chunk_type, chunk in self.client.generate_stream_with_reasoning(messages):
                    self._raise_if_llm_error(chunk)
                    if chunk_type == "content":
                        raw += chunk
            else:
                for chunk in self.client.generate_stream(messages):
                    self._raise_if_llm_error(chunk)
                    raw += chunk
            return raw

        def _stream_llm(messages):
            """流式调用，区分思维链和正文"""
            if use_reasoning:
                for chunk_type, chunk in self.client.generate_stream_with_reasoning(messages):
                    self._raise_if_llm_error(chunk)
                    if chunk_type == "thinking":
                        yield ("thinking", chunk)
                    else:
                        yield ("content", chunk)
            else:
                for chunk in self.client.generate_stream(messages):
                    self._raise_if_llm_error(chunk)
                    yield ("thinking", chunk)

        # ── 第一步：结构化提取（串行，后续步骤依赖结果） ──
        yield {"type": "stage", "stage": "正在解析简历结构..."}
        sections_raw = ""
        sections_messages = self._build_sections_messages(ocr_text)
        for kind, chunk in _stream_llm(sections_messages):
            if kind == "thinking":
                yield {"type": "thinking", "chunk": chunk}
            else:
                sections_raw += chunk
        sections = self._parse_json_array(sections_raw, fallback_id_prefix="sec")

        # ── 第二步 & 第三步：并行执行 ──
        yield {"type": "stage", "stage": "正在生成优化建议 & 提取结构化数据（并行）..."}

        # 线程安全队列收集思维链片段
        thinking_q: queue.Queue = queue.Queue()
        suggestions_result = {"raw": "", "done": False}
        builder_result = {"raw": "", "done": False}

        def _run_suggestions():
            try:
                msgs = self._build_suggestions_messages(sections, job_title, report_context=report_context)
                if msgs:
                    suggestions_result["raw"] = _collect_llm(msgs)
            except Exception as e:
                print(f"[ResumeAnalyzer] suggestions thread error: {e}")
                suggestions_result["error"] = str(e)
            suggestions_result["done"] = True
            thinking_q.put(None)  # 通知主线程

        def _run_builder():
            try:
                msgs = self._build_builder_messages(ocr_text)
                builder_result["raw"] = _collect_llm(msgs)
            except Exception as e:
                print(f"[ResumeAnalyzer] builder thread error: {e}")
                builder_result["error"] = str(e)
            builder_result["done"] = True
            thinking_q.put(None)  # 通知主线程

        t1 = threading.Thread(target=_run_suggestions, daemon=True)
        t2 = threading.Thread(target=_run_builder, daemon=True)
        t1.start()
        t2.start()

        # 等待两个线程完成
        while not (suggestions_result["done"] and builder_result["done"]):
            try:
                thinking_q.get(timeout=0.5)
            except queue.Empty:
                yield {"type": "thinking", "chunk": "."}

        t1.join(timeout=5)
        t2.join(timeout=5)

        thread_errors = [item.get("error") for item in (suggestions_result, builder_result) if item.get("error")]
        if thread_errors:
            raise RuntimeError("; ".join(thread_errors))

        suggestions = self._parse_json_array(suggestions_result["raw"], fallback_id_prefix="sug") if suggestions_result["raw"] else []
        suggestions = self._validate_resume_suggestions(suggestions, sections)
        builder_data = self._parse_json_object(builder_result["raw"]) if builder_result["raw"] else {}
        builder_data = self._validate_builder_data(builder_data)

        yield {"type": "done", "result": {
            "sections": sections,
            "suggestions": suggestions,
            "builder_data": builder_data,
        }}

    def _build_sections_messages(self, ocr_text: str) -> list:
        """构建结构化提取的 messages（复用 _extract_sections 的 prompt）"""
        prompt = f"""你是一个专业的简历解析与排版专家。请将以下 OCR 识别的简历原文拆分为结构化 JSON 数组，并对每个段落的内容进行 Markdown 格式规整。

## 输出格式

每个 section 是一个 JSON 对象：
- "id": 唯一标识，格式 "sec_1", "sec_2" 等
- "type": 只能是：personal_info / education / projects / experience / skills / certifications / other
- "title": 段落标题（如"教育背景"、"项目经历"）
- "content": 规整后的 Markdown 文本（见下方规整规则）

## Markdown 格式规整规则（极其重要）

OCR 原文存在大量格式混乱，你必须在 content 中修复：

1. **统一列表符号**：所有无序列表统一使用 `- `（短横线+空格），禁止出现 `·`、`•`、`*` 等其他符号
2. **有序列表**：使用 `1.`、`2.`、`3.` 标准编号，修复重复编号（如两个 `2.`）
3. **去除多余空行**：段落之间最多保留一个空行，列表项之间不要空行
4. **项目/经历格式**：每个项目用 `### 项目名称` 作为三级标题，紧接一行写时间和标签（如角色、奖项），然后用列表写详情
5. **个人信息格式**：联系方式用 ` | ` 分隔写在一行或两行内，紧凑排列。去掉嵌入的 HTML 标签（如 `<div>`, `<img>` 等）
6. **保留 LaTeX 公式**：`$...$` 和 `$$...$$` 包裹的数学公式原样保留，不要修改
7. **保留链接**：URL 保持原样，可以用 `[文字](URL)` 格式
8. **忠实原文**：只做格式规整，不要修改、删除或编造任何实质内容。OCR 识别错误的个别错字可以修正

请严格输出 JSON 数组，不要输出任何其他内容，不要用 markdown 代码块包裹。

简历原文：
{ocr_text[:5000]}"""
        return [
            {"role": "system", "content": "你是简历解析与排版专家。严格输出合法 JSON 数组，content 字段为规整后的 Markdown。"},
            {"role": "user", "content": prompt}
        ]

    def _format_report_context(self, report_context: Optional[dict]) -> str:
        if not report_context:
            return ""

        lines = []
        if report_context.get("questionnaireContext"):
            lines.append("## User Form Context (HIGH PRIORITY)")
            lines.append(report_context["questionnaireContext"])
            lines.append("")

        lines.append("## Prior interview feedback")
        if report_context.get("position"):
            lines.append(f"- Interview position: {report_context['position']}")
        if report_context.get("avgScore") is not None:
            lines.append(f"- Average score: {report_context['avgScore']}")
        if report_context.get("summary"):
            lines.append(f"- Summary: {report_context['summary']}")
        if report_context.get("strengths"):
            lines.append(f"- Strengths: {report_context['strengths']}")
        if report_context.get("weaknesses"):
            lines.append(f"- Weaknesses: {report_context['weaknesses']}")

        evaluations = report_context.get("evaluations") or []
        if evaluations:
            lines.append("- Dimension scores:")
            for item in evaluations:
                dimension = item.get("dimension", "unknown")
                score = item.get("score", "")
                comment = item.get("comment", "")
                entry = f"  - {dimension}: {score}/10"
                if comment:
                    entry += f", {comment}"
                lines.append(entry)

        lines.append("Treat this feedback as resume optimization goals. Prioritize fixing weaknesses and amplifying strengths without inventing experience.")
        return "\n".join(lines)

    def _build_suggestions_messages(self, sections: list, job_title: str = "", report_context: Optional[dict] = None) -> list:
        """构建优化建议的 messages"""
        analyzable = [s for s in sections if s.get("type") in ("experience", "projects", "skills", "education")]
        if not analyzable:
            return []
        job_context = f"目标岗位：{job_title}。" if job_title else ""
        report_feedback = self._format_report_context(report_context)
        sections_text = json.dumps(analyzable, ensure_ascii=False, indent=2)
        prompt = f"""{job_context}你是一位资深的硅谷大厂 HR 和简历优化专家。

{report_feedback}

请审查以下简历各段落，找出存在的问题并给出具体的重写建议。

常见问题类型：
- LACK_OF_METRICS: 缺乏量化指标
- WEAK_ACTION_VERB: 动词力度不足
- VAGUE_DESCRIPTION: 描述模糊
- MISSING_STAR: 不符合 STAR 法则
- ATS_KEYWORD_GAP: 缺少 ATS 关键词
- FORMAT_ISSUE: 格式问题

对每个发现的问题，输出一个 JSON 对象：
- "suggestionId": 唯一标识，格式 "sug_001", "sug_002" 等
- "targetBlockId": 对应 section 的 id
- "targetField": "content"
- "issueType": 上述问题类型之一
- "issueLabel": 问题的中文简短标签
- "originalText": 有问题的原始文本片段
- "suggestedText": 重写后的优化文本
- "reason": 修改理由
- "status": "PENDING"

请严格输出 JSON 数组，不要输出任何其他内容。不要用 markdown 代码块包裹。

简历段落：
{sections_text}"""
        return [
            {"role": "system", "content": "你是简历优化专家，只输出合法 JSON 数组。"},
            {"role": "user", "content": prompt}
        ]

    def _build_builder_messages(self, ocr_text: str) -> list:
        """构建 builder 数据提取的 messages"""
        system_prompt, user_prompt = generate_parser_prompt(ocr_text[:5000])
        template_instruction = """

另外，请根据简历内容判断最适合的模板风格，在 JSON 顶层增加 "detectedTemplate" 字段，只能是以下值之一：
- "classic": 传统单栏，通用型简历
- "modern": 双栏布局，适合有照片的简历
- "minimal": 极简纯文字风格
- "fresh": 应届生/校招简历
- "tech": 技术岗位（程序员/工程师）
- "creative": 创意岗位（设计师/运营）
- "executive": 商务岗位（产品/销售）
- "elegant": 高端/管理层简历

判断依据：根据简历中的岗位类型、工作年限、内容风格来选择。应届生选 fresh，技术类选 tech，设计/运营选 creative，管理层选 elegant，商务类选 executive，其他默认 classic。"""
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt + template_instruction}
        ]

    def _extract_sections(self, ocr_text: str) -> list:
        """让 LLM 将 OCR 原文拆分为结构化 sections，同时规整 Markdown 格式"""
        prompt = f"""你是一个专业的简历解析与排版专家。请将以下 OCR 识别的简历原文拆分为结构化 JSON 数组，并对每个段落的内容进行 Markdown 格式规整。

## 输出格式

每个 section 是一个 JSON 对象：
- "id": 唯一标识，格式 "sec_1", "sec_2" 等
- "type": 只能是：personal_info / education / projects / experience / skills / certifications / other
- "title": 段落标题（如"教育背景"、"项目经历"）
- "content": 规整后的 Markdown 文本（见下方规整规则）

## Markdown 格式规整规则（极其重要）

OCR 原文存在大量格式混乱，你必须在 content 中修复：

1. **统一列表符号**：所有无序列表统一使用 `- `（短横线+空格），禁止出现 `·`、`•`、`*` 等其他符号
2. **有序列表**：使用 `1.`、`2.`、`3.` 标准编号，修复重复编号（如两个 `2.`）
3. **去除多余空行**：段落之间最多保留一个空行，列表项之间不要空行
4. **项目/经历格式**：每个项目用 `### 项目名称` 作为三级标题，紧接一行写时间和标签（如角色、奖项），然后用列表写详情
5. **个人信息格式**：联系方式用 ` | ` 分隔写在一行或两行内，紧凑排列。去掉嵌入的 HTML 标签（如 `<div>`, `<img>` 等）
6. **保留 LaTeX 公式**：`$...$` 和 `$$...$$` 包裹的数学公式原样保留，不要修改
7. **保留链接**：URL 保持原样，可以用 `[文字](URL)` 格式
8. **忠实原文**：只做格式规整，不要修改、删除或编造任何实质内容。OCR 识别错误的个别错字可以修正

## 示例

OCR 原文片段：
```
桂林电子科技大学

· 学历：本科

2021.09 - 2025.06

· 专业：物联网工程

• GPA: 82.1/100 (专业前 10%)

- 主修课程：数据结构与算法设计、计算机网络
```

规整后 content：
```
桂林电子科技大学 | 本科 | 物联网工程 | 2021.09 - 2025.06

- GPA: 82.1/100（专业前 10%）
- 主修课程：数据结构与算法设计、计算机网络
```

请严格输出 JSON 数组，不要输出任何其他内容，不要用 markdown 代码块包裹。

简历原文：
{ocr_text[:5000]}"""

        messages = [
            {"role": "system", "content": "你是简历解析与排版专家。严格输出合法 JSON 数组，content 字段为规整后的 Markdown。"},
            {"role": "user", "content": prompt}
        ]
        raw = self.client.generate(messages)
        self._raise_if_llm_error(raw)
        return self._parse_json_array(raw, fallback_id_prefix="sec")

    def _generate_suggestions(self, sections: list, job_title: str = "", report_context: Optional[dict] = None) -> list:
        """对每个 section 生成优化建议"""
        # 只分析有实质内容的 section（跳过个人信息等）
        analyzable = [s for s in sections if s.get("type") in ("experience", "projects", "skills", "education")]
        if not analyzable:
            return []

        job_context = f"目标岗位：{job_title}。" if job_title else ""
        sections_text = json.dumps(analyzable, ensure_ascii=False, indent=2)

        # PLACEHOLDER_SUGGESTIONS_PROMPT
        prompt = f"""{job_context}你是一位资深的硅谷大厂 HR 和简历优化专家。

请审查以下简历各段落，找出存在的问题并给出具体的重写建议。

常见问题类型：
- LACK_OF_METRICS: 缺乏量化指标（没有具体数字、百分比、规模等）
- WEAK_ACTION_VERB: 动词力度不足（使用了"负责"、"参与"等模糊动词）
- VAGUE_DESCRIPTION: 描述模糊（缺乏具体技术栈、方法论或成果）
- MISSING_STAR: 不符合 STAR 法则（缺少情境、任务、行动或结果）
- ATS_KEYWORD_GAP: 缺少 ATS 关键词（与目标岗位相关的技术术语不足）
- FORMAT_ISSUE: 格式问题（时间线不清晰、排版混乱等）

对每个发现的问题，输出一个 JSON 对象：
- "suggestionId": 唯一标识，格式 "sug_001", "sug_002" 等
- "targetBlockId": 对应 section 的 id
- "targetField": "content"
- "issueType": 上述问题类型之一
- "issueLabel": 问题的中文简短标签
- "originalText": 有问题的原始文本片段
- "suggestedText": 重写后的优化文本
- "reason": 修改理由（简洁说明为什么要改）
- "status": "PENDING"

请严格输出 JSON 数组，不要输出任何其他内容。不要用 markdown 代码块包裹。
如果某个段落没有问题，就不要为它生成建议。

简历段落：
{sections_text}"""

        messages = [
            {"role": "system", "content": "你是简历优化专家，只输出合法 JSON 数组。"},
            {"role": "user", "content": prompt}
        ]
        raw = self.client.generate(messages)
        self._raise_if_llm_error(raw)
        return self._parse_json_array(raw, fallback_id_prefix="sug")

    def _extract_builder_data(self, ocr_text: str) -> dict:
        """提取结构化简历数据（builder 格式）并自动检测最佳模板"""
        system_prompt, user_prompt = generate_parser_prompt(ocr_text[:5000])

        # 追加模板检测指令
        template_instruction = """

另外，请根据简历内容判断最适合的模板风格，在 JSON 顶层增加 "detectedTemplate" 字段，只能是以下值之一：
- "classic": 传统单栏，通用型简历
- "modern": 双栏布局，适合有照片的简历
- "minimal": 极简纯文字风格
- "fresh": 应届生/校招简历
- "tech": 技术岗位（程序员/工程师）
- "creative": 创意岗位（设计师/运营）
- "executive": 商务岗位（产品/销售）
- "elegant": 高端/管理层简历

判断依据：根据简历中的岗位类型、工作年限、内容风格来选择。应届生选 fresh，技术类选 tech，设计/运营选 creative，管理层选 elegant，商务类选 executive，其他默认 classic。"""

        user_prompt_with_template = user_prompt + template_instruction

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt_with_template}
        ]
        raw = self.client.generate(messages)
        self._raise_if_llm_error(raw)
        data = self._parse_json_object(raw)

        # 校验并补全数据
        data = self._validate_builder_data(data)
        return data

    @staticmethod
    def _raise_if_llm_error(raw: object) -> None:
        text = str(raw or "").strip()
        if not text:
            return

        detail = ""
        if text.startswith("[错误:"):
            detail = text[len("[错误:"):].strip()
            if detail.endswith("]"):
                detail = detail[:-1].strip()
        elif text.startswith("错误:"):
            detail = text[len("错误:"):].strip()

        if detail:
            raise RuntimeError(f"LLM 调用失败: {detail}")

    @staticmethod
    def _parse_json_object(raw: str) -> dict:
        """从 LLM 输出中提取 JSON 对象，容错处理"""
        if not raw:
            return {}
        # 尝试直接解析
        try:
            result = json.loads(raw.strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 中的内容
        match = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', raw)
        if match:
            try:
                result = json.loads(match.group(1))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        # 尝试找到第一个 { 和最后一个 }
        start = raw.find('{')
        end = raw.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                result = json.loads(raw[start:end + 1])
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
        return {}

    @staticmethod
    def _to_text(value, default: str = "") -> str:
        if value is None:
            return default
        if isinstance(value, str):
            return value
        return str(value)

    @staticmethod
    def _to_bool(value, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {'true', '1', 'yes', 'y', 'on'}:
                return True
            if normalized in {'false', '0', 'no', 'n', 'off', ''}:
                return False
        return bool(value)

    @staticmethod
    def _validate_builder_data(data: dict) -> dict:
        """校验并补全 builder 格式数据"""
        if not isinstance(data, dict):
            data = {}

        # 确保 detectedTemplate 有效
        valid_templates = {'classic', 'modern', 'minimal', 'fresh', 'tech', 'creative', 'executive', 'elegant'}
        if data.get('detectedTemplate') not in valid_templates:
            data['detectedTemplate'] = 'classic'

        # 补全 basicInfo
        if not isinstance(data.get('basicInfo'), dict):
            data['basicInfo'] = {}
        basic_defaults = {
            'name': '', 'gender': '', 'birthday': '', 'email': '',
            'mobile': '', 'location': '', 'workYears': '', 'photoUrl': ''
        }
        for key, default in basic_defaults.items():
            data['basicInfo'][key] = ResumeAnalyzer._to_text(data['basicInfo'].get(key), default)

        # 处理 modules
        if not isinstance(data.get('modules'), list):
            data['modules'] = []

        normalized_modules = []
        for idx, module in enumerate(data['modules']):
            if not isinstance(module, dict):
                continue
            if not module.get('id'):
                module['id'] = f"mod_{uuid.uuid4().hex[:12]}"
            module['id'] = ResumeAnalyzer._to_text(module.get('id'))
            module['type'] = ResumeAnalyzer._to_text(module.get('type'), 'custom')
            module['title'] = ResumeAnalyzer._to_text(module.get('title'))
            module['visible'] = ResumeAnalyzer._to_bool(module.get('visible', True), True)
            try:
                module['sortIndex'] = int(module.get('sortIndex', idx))
            except (TypeError, ValueError):
                module['sortIndex'] = idx

            if 'content' in module:
                module['content'] = ResumeAnalyzer._to_text(module.get('content'))

            if 'tags' in module:
                tags = module.get('tags') if isinstance(module.get('tags'), list) else []
                module['tags'] = [ResumeAnalyzer._to_text(tag) for tag in tags if ResumeAnalyzer._to_text(tag).strip()]

            if 'skillBars' in module:
                skill_bars = module.get('skillBars') if isinstance(module.get('skillBars'), list) else []
                normalized_skills = []
                for skill in skill_bars:
                    if not isinstance(skill, dict):
                        continue
                    normalized_skill = dict(skill)
                    normalized_skill['name'] = ResumeAnalyzer._to_text(normalized_skill.get('name'))
                    try:
                        level = int(normalized_skill.get('level', 0))
                    except (TypeError, ValueError):
                        level = 0
                    normalized_skill['level'] = max(0, min(100, level))
                    normalized_skills.append(normalized_skill)
                module['skillBars'] = normalized_skills

            if 'entries' in module:
                entries = module.get('entries') if isinstance(module.get('entries'), list) else []
                normalized_entries = []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    normalized_entry = dict(entry)
                    if not normalized_entry.get('id'):
                        normalized_entry['id'] = f"ent_{uuid.uuid4().hex[:12]}"
                    normalized_entry['id'] = ResumeAnalyzer._to_text(normalized_entry.get('id'))
                    normalized_entry['timeStart'] = ResumeAnalyzer._to_text(normalized_entry.get('timeStart'))
                    normalized_entry['timeEnd'] = ResumeAnalyzer._to_text(normalized_entry.get('timeEnd'))
                    normalized_entry['isCurrent'] = ResumeAnalyzer._to_bool(normalized_entry.get('isCurrent', False), False)
                    normalized_entry['orgName'] = ResumeAnalyzer._to_text(normalized_entry.get('orgName'))
                    normalized_entry['role'] = ResumeAnalyzer._to_text(normalized_entry.get('role'))
                    normalized_entry['detail'] = ResumeAnalyzer._to_text(normalized_entry.get('detail'))
                    normalized_entries.append(normalized_entry)
                module['entries'] = normalized_entries

            normalized_modules.append(module)

        data['modules'] = normalized_modules
        return data

    @staticmethod
    def _validate_resume_suggestions(suggestions: list, sections: list) -> list:
        if not isinstance(suggestions, list) or not isinstance(sections, list):
            return []

        valid_issue_types = {
            'LACK_OF_METRICS', 'WEAK_ACTION_VERB', 'VAGUE_DESCRIPTION',
            'MISSING_STAR', 'ATS_KEYWORD_GAP', 'FORMAT_ISSUE'
        }
        section_by_id = {
            section.get('id'): section
            for section in sections
            if isinstance(section, dict) and section.get('id')
        }
        normalized = []
        seen_ids = set()

        for item in suggestions:
            if len(normalized) >= 10:
                break
            if not isinstance(item, dict):
                continue

            target_block_id = ResumeAnalyzer._to_text(item.get('targetBlockId')).strip()
            target_field = ResumeAnalyzer._to_text(item.get('targetField'), 'content').strip() or 'content'
            original_text = ResumeAnalyzer._to_text(item.get('originalText')).strip()
            suggested_text = ResumeAnalyzer._to_text(item.get('suggestedText')).strip()

            section = section_by_id.get(target_block_id)
            content = ResumeAnalyzer._to_text(section.get('content')) if section else ''
            if not section or target_field != 'content':
                continue
            if not original_text or not suggested_text or original_text == suggested_text:
                continue
            if original_text not in content:
                continue

            suggestion_id = ResumeAnalyzer._to_text(item.get('suggestionId')).strip()
            if not suggestion_id or suggestion_id in seen_ids:
                suggestion_id = f"sug_{len(normalized) + 1:03d}"
            seen_ids.add(suggestion_id)

            issue_type = ResumeAnalyzer._to_text(item.get('issueType'), 'VAGUE_DESCRIPTION').strip()
            if issue_type not in valid_issue_types:
                issue_type = 'VAGUE_DESCRIPTION'

            normalized.append({
                'suggestionId': suggestion_id,
                'targetBlockId': target_block_id,
                'targetField': 'content',
                'issueType': issue_type,
                'issueLabel': ResumeAnalyzer._to_text(item.get('issueLabel'), '优化建议').strip() or '优化建议',
                'originalText': original_text,
                'suggestedText': suggested_text,
                'reason': ResumeAnalyzer._to_text(item.get('reason')).strip(),
                'status': 'PENDING',
            })

        return normalized

    @staticmethod
    def validate_builder_polish_suggestions(suggestions: list, modules: list) -> list:
        if not isinstance(suggestions, list) or not isinstance(modules, list):
            return []

        module_by_id = {
            ResumeAnalyzer._to_text(module.get('id')): module
            for module in modules
            if isinstance(module, dict) and module.get('id')
        }
        normalized = []
        seen_ids = set()

        for item in suggestions:
            if len(normalized) >= 10:
                break
            if not isinstance(item, dict):
                continue

            module_id = ResumeAnalyzer._to_text(item.get('moduleId')).strip()
            module = module_by_id.get(module_id)
            if not module:
                continue

            entry_id = ResumeAnalyzer._to_text(item.get('entryId')).strip()
            field_path = ResumeAnalyzer._to_text(item.get('fieldPath')).strip()
            original_text = ResumeAnalyzer._to_text(item.get('originalText')).strip()
            suggested_text = ResumeAnalyzer._to_text(item.get('suggestedText')).strip()
            if not field_path or not original_text or not suggested_text or original_text == suggested_text:
                continue

            normalized_original = original_text
            normalized_suggested = suggested_text
            normalized_entry_id = entry_id or None

            if entry_id:
                if field_path != 'detail' or not isinstance(module.get('entries'), list):
                    continue
                entry = next(
                    (entry for entry in module['entries'] if isinstance(entry, dict) and ResumeAnalyzer._to_text(entry.get('id')) == entry_id),
                    None,
                )
                if not entry:
                    continue
                current_value = ResumeAnalyzer._to_text(entry.get('detail'))
                if not current_value or original_text not in current_value:
                    continue
                normalized_original = current_value
                normalized_suggested = current_value.replace(original_text, suggested_text, 1)
                if normalized_original == normalized_suggested:
                    continue
            else:
                if field_path != 'content':
                    continue
                current_value = ResumeAnalyzer._to_text(module.get('content'))
                if not current_value or original_text not in current_value:
                    continue

            suggestion_id = ResumeAnalyzer._to_text(item.get('id')).strip()
            if not suggestion_id or suggestion_id in seen_ids:
                suggestion_id = f"sug_{len(normalized) + 1:03d}"
            seen_ids.add(suggestion_id)

            normalized.append({
                'id': suggestion_id,
                'moduleId': module_id,
                'entryId': normalized_entry_id,
                'fieldPath': field_path,
                'originalText': normalized_original,
                'suggestedText': normalized_suggested,
                'reason': ResumeAnalyzer._to_text(item.get('reason')).strip(),
                'status': 'pending',
            })

        return normalized

    @staticmethod
    def _parse_json_array(raw: str, fallback_id_prefix: str = "item") -> list:
        """从 LLM 输出中提取 JSON 数组，容错处理"""
        if not raw:
            return []
        # 尝试直接解析
        try:
            result = json.loads(raw.strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
        # 尝试提取 ```json ... ``` 中的内容
        match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', raw)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        # 尝试找到第一个 [ 和最后一个 ]
        start = raw.find('[')
        end = raw.rfind(']')
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except json.JSONDecodeError:
                pass
        return []

"""
Prompt Generator Agent（元 Prompt 架构）
根据面试配置动态生成高质量的面试官 System Prompt。
使用轻量模型调用，生成结果缓存到 session 级别。
"""
from openai import OpenAI


class PromptGenerator:
    """
    元 Prompt Agent：根据面试配置动态生成高质量的面试官 System Prompt。
    使用与主面试 Agent 相同的 API（deepseek-chat），但通过专门的元 prompt 指导生成。
    """

    META_PROMPT = """你是一个面试 Prompt 工程师。你的任务是根据以下信息，为一个 AI 面试官生成一份高质量的 System Prompt。

## 输入信息
- 目标岗位：{job_title}
- 面试轮次：{interview_type}
- 难度级别：{difficulty}
- 面试风格：{style}
- 候选人简历摘要：{resume_summary}
- 岗位要求 / 职位描述：{job_requirements}

## 生成要求
1. 生成的 prompt 必须包含明确的角色定义、行为约束、提问策略
2. 必须包含以下反幻觉规则（原文嵌入，不可省略或改写）：
   - 【禁止捏造经历】严格基于工具解析出的真实简历内容或用户的真实回答来提问。如果未获取到简历，只能提问通用领域知识或让用户主动描述。绝不允许编造项目。
   - 【禁止自问自答】每次只抛出 1-2 个问题后必须立即停止输出，绝对不能在同一次回复中替候选人把答案说出来。
   - 【禁止编造技术事实】严禁瞎编不存在的框架、API、函数或技术名词。
   - 【禁止出戏】严禁出现"作为AI模型"、"我是人工智能"等免责声明。
3. 根据岗位特点设计 3-5 个核心考察维度
4. 如果有简历摘要，根据简历内容设计 2-3 个针对性的深挖方向
5. 根据难度级别调整提问深度和追问力度
6. 根据面试风格调整语气和互动方式
7. 如果提供了岗位要求 / 职位描述，必须把它作为岗位考察重点、追问方向和评分基准进行融合
8. 必须明确说明岗位要求不代表候选人已具备，候选人事实仍然只能来自简历和候选人回答
9. 岗位要求相关内容必须以独立章节呈现，不能混进候选人简历事实
10. 必须包含输出格式约束：每次回复控制在 200 字以内，只提 1-2 个问题然后停止
11. 必须包含"回应与过渡"规则：面试官在候选人每次回答后，必须先给出 1-2 句简短回应（认可、指出不足、或过渡），然后再提下一个问题。禁止无视回答直接抛新题。
12. 必须包含面试节奏控制：
   - 初级难度：总共 8-12 题，每话题最多追问 1-2 轮
   - 中级难度：总共 10-15 题，每话题最多追问 2-3 轮
   - 高级难度：总共 12-18 题，每话题最多追问 3-4 轮
   - 面试官必须默默计数题目，接近上限时进入收尾阶段，达到上限时必须结束面试并给出总结
   - 候选人连续两次无法回答同一话题时，必须切换话题
13. 必须包含面试收尾话术：接近题目上限时进入反问环节（"你有什么想问我的吗？"），最后一题后正式结束并给出简要评价和祝福语
14. 必须明确禁止输出任何括号中的语气说明、动作说明或舞台指令，例如“（语气冷静）”“【停顿】”“[提高语速]”；面试官只能直接输出候选人最终会听到的话术

## 输出
直接输出生成的 System Prompt 文本，不要包含任何解释或元信息。"""

    STYLE_MAP = {
        "default": "标准专业型（客观中立、专业均衡）",
        "strict": "严肃高压型（冷峻专业、施加压力、刁钻追问）",
        "friendly": "温和引导型（友善鼓励、循循善诱）",
    }

    TYPE_MAP = {
        "technical": "技术面/专业面",
        "hr": "HR面/综合素质面",
        "manager": "主管面/业务面",
    }

    DIFFICULTY_MAP = {
        "junior": "初级（基础概念、常见API）",
        "mid": "中级（实战经验、原理理解）",
        "senior": "高级（架构设计、底层源码）",
    }

    def __init__(self, api_key: str, base_url: str, model: str = "deepseek-chat"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    def generate(self, job_title: str, interview_type: str, difficulty: str,
                 style: str, resume_summary: str = "", job_requirements: str = "") -> str:
        """
        调用 LLM 生成定制化的面试 System Prompt。
        失败时抛出异常，由调用方决定降级策略。
        """
        prompt = self.META_PROMPT.format(
            job_title=job_title,
            interview_type=self.TYPE_MAP.get(interview_type, interview_type),
            difficulty=self.DIFFICULTY_MAP.get(difficulty, difficulty),
            style=self.STYLE_MAP.get(style, style),
            resume_summary=resume_summary if resume_summary else "未提供简历",
            job_requirements=job_requirements if job_requirements else "未提供岗位要求",
        )

        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=2000
        )
        return response.choices[0].message.content

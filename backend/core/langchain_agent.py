"""
LangChain 版本的面试 Agent
使用 OpenAI Functions Agent 架构，支持流畅的对话式交互
"""
import os
import sys
import json
import traceback
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

try:
    from utils.safe_log import safe_log
except Exception:
    backend_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from utils.safe_log import safe_log

# Keep legacy diagnostic prints from interrupting desktop flows on GBK consoles.
print = safe_log

# 1. 尝试导入本地的 llm_client（支持作为脚本或包两种导入方式）
OpenAICompatibleClient = None
try:
    from core.llm_client import OpenAICompatibleClient
except Exception:
    try:
        from .llm_client import OpenAICompatibleClient
    except Exception:
        try:
            from llm_client import OpenAICompatibleClient
        except Exception:
            OpenAICompatibleClient = None

# 2. 尝试导入 PromptManager
PromptManager = None
try:
    from core.prompt_manager import PromptManager
except Exception:
    try:
        from prompt_manager import PromptManager
    except Exception:
        PromptManager = None

try:
    from core.langfuse_tracing import merge_langfuse_callback_config
except Exception:
    try:
        from .langfuse_tracing import merge_langfuse_callback_config
    except Exception:
        def merge_langfuse_callback_config(config=None):
            return config

# 3. 尝试导入 langchain 的标准组件
HAVE_LANGCHAIN = False
create_openai_functions_agent = None
AgentExecutor = None
initialize_agent_fn = None
AgentTypeEnum = None
ChatOpenAI = None
ConversationBufferMemory = None
SystemMessage = None
MessagesPlaceholder = None
ChatPromptTemplate = None

try:
    from langchain import agents as lc_agents
    from langchain.schema import SystemMessage
    from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

    # 新版 LangChain API (>= 0.1.x)
    create_openai_functions_agent = getattr(lc_agents, "create_openai_functions_agent", None)
    AgentExecutor = getattr(lc_agents, "AgentExecutor", None)

    # 旧版 LangChain API (< 0.1.x)
    initialize_agent_fn = getattr(lc_agents, "initialize_agent", None)
    AgentTypeEnum = getattr(lc_agents, "AgentType", None)

    HAVE_LANGCHAIN = any([
        create_openai_functions_agent is not None and AgentExecutor is not None,
        initialize_agent_fn is not None and AgentTypeEnum is not None,
    ])
except Exception as e:
    # 避免启动日志噪音，仅在显式开启时输出导入调试信息
    if os.getenv("LANGCHAIN_IMPORT_DEBUG", "0") == "1":
        print(f"Warning: Failed to import langchain agents API: {e}")

try:
    from langchain_openai import ChatOpenAI
except Exception:
    try:
        from langchain.chat_models import ChatOpenAI
    except Exception:
        pass

try:
    from langchain.memory import ConversationBufferMemory
except Exception:
    try:
        from langchain_core.memory import ConversationBufferMemory
    except Exception:
        pass

# 4. 导入工具（优先使用现有 langchain_tools 注册表；如果不可用，提供本地回退实现）
try:
    from core.tools.langchain_tools import LangChainToolRegistry
except Exception:
    try:
        from .tools.langchain_tools import LangChainToolRegistry
    except Exception as e:
        print(f"Warning: Cannot import tools.langchain_tools: {e}. Using Mock tools.")
        def google_search(**kwargs): return "Mock Google Search Result"
        def perform_ocr(**kwargs): return "Mock OCR Result"

        class LangChainToolRegistry:
            def __init__(self):
                self._tools_map = {
                    "google_search": google_search,
                    "perform_ocr": perform_ocr,
                }
            def get_langchain_tools(self):
                return []
            def execute_tool(self, tool_name: str, **kwargs) -> str:
                if tool_name not in self._tools_map:
                    return f"错误：工具 {tool_name} 未定义。"
                return self._tools_map[tool_name](**kwargs)


class LangChainInterviewAgent:
    """
    基于 LangChain 的智能面试 Agent
    """

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        verbose: bool = False,
        llm_client: Optional[Any] = None,
        max_history_turns: int = 10,
        role: str = "interviewer",
        prompt_config_path: str = "",
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model
        self.verbose = verbose
        self.max_history_turns = max_history_turns
        self.role = role
        self.llm_client = llm_client
        self.chat_history: List[Dict[str, str]] = []
        self._agent_executor_hidden_context_mode = ""

        # 初始化动态 Prompt 管理器
        self.prompt_manager = PromptManager() if PromptManager else None

        # 加载静态 prompt 配置文件作为后备
        if not prompt_config_path:
            prompt_config_path = os.path.join(os.path.dirname(__file__), "prompts.json")
        self.prompt_config = self._load_prompt_config(prompt_config_path)
        self.current_style = "default"

        # 初始化工具注册表；工具层异常不应阻塞整个面试主流程。
        try:
            self.tool_registry = LangChainToolRegistry()
            self.tools = self.tool_registry.get_langchain_tools()
        except Exception as e:
            print(f"Warning: Failed to initialize LangChain tools: {e}. Continuing without tool support.")
            traceback.print_exc()

            class _EmptyToolRegistry:
                def get_langchain_tools(self):
                    return []

                def execute_tool(self, tool_name: str, **kwargs) -> str:
                    return f"错误：工具 {tool_name} 暂时不可用。"

            self.tool_registry = _EmptyToolRegistry()
            self.tools = []

        # 初始化记忆
        if ConversationBufferMemory is not None:
            self.memory = ConversationBufferMemory(
                memory_key="chat_history",
                input_key="input",
                return_messages=True,
                output_key="output"
            )
        else:
            class _SimpleMemory:
                def __init__(self):
                    self.chat_memory = type("CM", (), {"messages": []})()
                def clear(self):
                    self.chat_memory.messages.clear()
            self.memory = _SimpleMemory()

        self.prompt = self._build_prompt()

        # 尝试自动创建 llm_client（回退模式使用）
        if self.llm_client is None and OpenAICompatibleClient is not None:
            if self.api_key and self.base_url:
                try:
                    self.llm_client = OpenAICompatibleClient(
                        model=self.model_name,
                        api_key=self.api_key,
                        base_url=self.base_url
                    )
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ 无法自动创建 llm_client: {e}")

        # 核心：构建 Agent
        self._build_agent_executor(temperature)

    def _build_agent_executor(self, temperature: float = 0.7):
        """构建或重载真正的带工具的 Agent 执行器"""
        local_has_langchain = HAVE_LANGCHAIN and (ChatOpenAI is not None)
        self._agent_executor_hidden_context_mode = ""

        if local_has_langchain:
            try:
                llm = ChatOpenAI(
                    model=self.model_name,
                    api_key=self.api_key,
                    base_url=self.base_url,
                    temperature=temperature
                )

                # 使用新版 API
                if create_openai_functions_agent is not None and AgentExecutor is not None:
                    # 新版 LangChain (>= 0.1.0)
                    prompt = ChatPromptTemplate.from_messages([
                        ("system", self.prompt),
                        MessagesPlaceholder(variable_name="hidden_context", optional=True),
                        MessagesPlaceholder(variable_name="chat_history", optional=True),
                        ("human", "{input}"),
                        MessagesPlaceholder(variable_name="agent_scratchpad"),
                    ])

                    agent = create_openai_functions_agent(llm, self.tools, prompt)
                    self.agent_executor = AgentExecutor(
                        agent=agent,
                        tools=self.tools,
                        verbose=self.verbose,
                        memory=self.memory,
                        handle_parsing_errors=True
                    )
                    self._agent_executor_hidden_context_mode = "messages"
                elif initialize_agent_fn is not None and AgentTypeEnum is not None:
                    # 旧版 LangChain (< 0.1.0) - 使用 initialize_agent
                    system_message = SystemMessage(content=self.prompt)

                    self.agent_executor = initialize_agent_fn(
                        tools=self.tools,
                        llm=llm,
                        agent=AgentTypeEnum.OPENAI_FUNCTIONS,
                        verbose=self.verbose,
                        agent_kwargs={"system_message": system_message},
                        memory=self.memory,
                        handle_parsing_errors=True
                    )
                else:
                    raise RuntimeError("No compatible LangChain agent API found in current environment")

                if self.verbose:
                    print("Successfully initialized LangChain Agent with tools")

            except Exception as e:
                print(f"Warning: Failed to create LangChain agent: {e}, falling back to no-tool mode")
                traceback.print_exc()
                self.agent_executor = None
                local_has_langchain = False

        # 降级模式：不支持工具调用
        if not local_has_langchain:
            class _FallbackExecutor:
                def __init__(self, llm_client, system_prompt, parent_agent):
                    self.llm_client = llm_client
                    self.system_prompt = system_prompt
                    self.parent_agent = parent_agent

                supports_hidden_context = True
                hidden_context_mode = "system"

                def invoke(self, inputs: dict, config: Optional[dict] = None, **kwargs):
                    full = inputs.get("input") if isinstance(inputs, dict) else str(inputs)
                    hidden_context = inputs.get("_hidden_context", "") if isinstance(inputs, dict) else ""

                    # 记录降级模式的调试信息
                    fallback_step = {
                        "tool": "FallbackMode",
                        "tool_input": "使用降级模式(无LangChain支持)",
                        "log": "Agent处于降级模式，直接调用LLM客户端，不支持工具调用",
                        "observation": "降级模式已激活"
                    }

                    if self.llm_client is not None:
                        messages = [{"role": "system", "content": self.system_prompt}]
                        if hidden_context:
                            messages.append({"role": "system", "content": hidden_context})
                        messages.extend(self.parent_agent.chat_history)
                        messages.append({"role": "user", "content": full})
                        try:
                            answer = self.llm_client.generate(messages)
                            fallback_step["observation"] = f"成功调用LLM，返回{len(answer)}字符"
                        except Exception as e:
                            answer = f"（回退）调用 llm_client 时出错: {e}"
                            fallback_step["observation"] = f"错误: {str(e)}"
                        return {"output": answer, "intermediate_steps": [fallback_step]}
                    else:
                        fallback_step["observation"] = "严重错误：llm_client未初始化"
                        return {"output": f"（严重错误）缺少 langchain 且 llm_client 未初始化。收到输入：{full}", "intermediate_steps": [fallback_step]}

            self.agent_executor = _FallbackExecutor(self.llm_client, self.prompt, self)
            self._agent_executor_hidden_context_mode = "system"
            if self.verbose:
                print("Warning: Agent started in fallback mode without tool support.")

    def _load_prompt_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config
        except Exception as e:
            if self.verbose:
                print(f"Warning: Failed to load prompt config: {e}, using default config")
            return {
                "interviewer": {
                    "system_prompt": "You are a professional technical interviewer.",
                    "greeting": "Hello, welcome to the interview."
                },
                "styles": {
                    "default": {"injection": ""}
                }
            }

    def _build_prompt(self) -> str:
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        role_config = self.prompt_config.get(self.role, {})
        base_prompt = role_config.get("system_prompt", "你是一个 AI 面试官。")
        return f"[当前系统时间: {current_time}]\n\n{base_prompt}"

    def get_greeting(self) -> str:
        role_config = self.prompt_config.get(self.role, {})
        return role_config.get("greeting", "你好！")

    def get_available_styles(self) -> List[str]:
        styles = self.prompt_config.get("styles", {})
        return list(styles.keys())

    def run(
        self,
        query: str,
        context: Optional[str] = None,
        trace_context: Optional[dict] = None,
    ) -> Tuple[str, List[Dict]]:
        visible_input = query
        full_input = f"{context}\n\n{query}" if context else query

        try:
            if self.agent_executor:
                # AgentExecutor 接收 dict 格式输入
                run_config = merge_langfuse_callback_config(trace_context=trace_context)
                hidden_context_mode = self._agent_executor_hidden_context_mode
                if context and hidden_context_mode == "messages" and SystemMessage is not None:
                    invoke_payload = {
                        "input": visible_input,
                        "hidden_context": [SystemMessage(content=context)],
                    }
                elif context and hidden_context_mode == "system":
                    invoke_payload = {"input": visible_input, "_hidden_context": context}
                else:
                    invoke_payload = {"input": full_input}
                if run_config:
                    result = self.agent_executor.invoke(invoke_payload, config=run_config)
                else:
                    result = self.agent_executor.invoke(invoke_payload)
                response = result.get("output", "抱歉，我没有生成有效的回应。")
                raw_steps = result.get("intermediate_steps", [])
                if context:
                    self._scrub_latest_memory_user_message(full_input, visible_input)
            else:
                response = "Agent 尚未正确初始化。"
                raw_steps = []

            # 【核心修改】格式化中间步骤 (将 Agent的内部动作 序列化为 JSON 友好的字典格式)
            intermediate_steps = []
            for step in raw_steps:
                if isinstance(step, tuple) and len(step) == 2:
                    action, obs = step
                    intermediate_steps.append({
                        "tool": getattr(action, "tool", "Unknown"),
                        "tool_input": getattr(action, "tool_input", ""),
                        "log": getattr(action, "log", ""),
                        "observation": str(obs)
                    })
                else:
                    intermediate_steps.append({"raw": str(step)})

            self._add_to_history({"role": "user", "content": visible_input})
            self._add_to_history({"role": "assistant", "content": response})
            return response, intermediate_steps

        except Exception as e:
            if self.verbose:
                print(f"Error during execution: {str(e)}")
                traceback.print_exc()
            return "Sorry, the system encountered some issues. Let's continue the interview, please answer the previous question again.", []

    def run_stream(self, query: str, context: Optional[str] = None):
        """
        流式运行：逐 chunk 返回 LLM 输出，区分思维链和正式回复。
        yield ("thinking", chunk) — 思维链片段
        yield ("content", chunk) — 正式回复片段
        """
        # 构建消息列表
        messages = [{"role": "system", "content": self.prompt}]
        if context:
            messages.append({"role": "system", "content": context})
        messages.extend(self.chat_history)
        messages.append({"role": "user", "content": query})

        response_text = ""
        try:
            if self.llm_client:
                if hasattr(self.llm_client, 'generate_stream_with_reasoning'):
                    for chunk_type, chunk in self.llm_client.generate_stream_with_reasoning(messages):
                        if chunk_type == "content":
                            response_text += chunk
                        yield (chunk_type, chunk)
                else:
                    for chunk in self.llm_client.generate_stream(messages):
                        response_text += chunk
                        yield ("content", chunk)
            else:
                response_text = "Agent 尚未正确初始化。"
                yield ("content", response_text)
        except Exception as e:
            if self.verbose:
                print(f"Stream error: {e}")
            if not response_text:
                response_text = "抱歉，系统遇到了问题。"
                yield ("content", response_text)

        # 记录到对话历史
        self._add_to_history({"role": "user", "content": query})
        self._add_to_history({"role": "assistant", "content": response_text})

    def _add_to_history(self, message: Dict[str, str]):
        self.chat_history.append(message)
        if self.max_history_turns > 0:
            max_messages = self.max_history_turns * 2
            if len(self.chat_history) > max_messages:
                self.chat_history = self.chat_history[-max_messages:]

    def _scrub_latest_memory_user_message(self, hidden_input: str, visible_input: str) -> None:
        memory = getattr(self, "memory", None)
        chat_memory = getattr(memory, "chat_memory", None)
        messages = getattr(chat_memory, "messages", None)
        if not isinstance(messages, list):
            return
        for message in reversed(messages):
            if getattr(message, "content", None) == hidden_input:
                try:
                    message.content = visible_input
                except Exception:
                    pass
                return

    def reset_memory(self):
        self.chat_history.clear()
        if hasattr(self, 'memory'):
            self.memory.clear()

    def get_chat_history(self) -> List[Dict]:
        return self.chat_history

    def evaluate_interview(self, draft: dict = None) -> Dict:
        """面试结束时，基于完整对话历史生成评估报告。
        返回 { evaluations: [{dimension, score, comment}], summary: str }
        """
        if not self.chat_history:
            return {}

        # 构建草稿参考段落
        draft_context = ""
        if draft and (draft.get("strengths") or draft.get("weaknesses")):
            s_lines = "\n".join(
                f"  - 第{x['turn']}轮：{x['text']}" for x in draft.get("strengths", [])
            )
            w_lines = "\n".join(
                f"  - 第{x['turn']}轮：{x['text']}" for x in draft.get("weaknesses", [])
            )
            notes = "\n".join(
                f"  - 第{x['turn']}轮：{x['note']}" for x in draft.get("turn_notes", [])
            )
            draft_context = (
                f"\n\n【过程观察记录（供参考，请结合对话综合判断）】\n"
                f"优势观察：\n{s_lines}\n"
                f"不足观察：\n{w_lines}\n"
                f"关键节点：\n{notes}"
            )

        eval_prompt = f"""你是一位资深面试评估专家。请根据以下面试对话记录，生成一份客观、专业的面试评估报告。

请严格按照以下 JSON 格式输出（不要输出任何其他内容）：
{{
  "evaluations": [
    {{"dimension": "技术深度", "score": 1-10的整数, "comment": "一句话点评"}},
    {{"dimension": "沟通表达", "score": 1-10的整数, "comment": "一句话点评"}},
    {{"dimension": "逻辑思维", "score": 1-10的整数, "comment": "一句话点评"}},
    {{"dimension": "项目经验", "score": 1-10的整数, "comment": "一句话点评"}},
    {{"dimension": "学习潜力", "score": 1-10的整数, "comment": "一句话点评"}}
  ],
  "strengths": "2-3句话总结候选人的优势亮点",
  "weaknesses": "2-3句话总结候选人的不足和改进建议",
  "summary": "1-2句话的总体评价"
}}

评分标准：
- 1-3分：明显不足，回答偏离主题或无法作答
- 4-5分：基本合格，但缺乏深度
- 6-7分：良好，有一定深度和条理
- 8-9分：优秀，回答全面且有独到见解
- 10分：卓越，超出预期

请根据实际对话内容客观评分，不要给所有维度相同的分数。"""

        messages = [{"role": "system", "content": eval_prompt}]

        # 构建对话摘要（避免超长）
        history_text = ""
        for msg in self.chat_history:
            role_label = "面试官" if msg["role"] == "assistant" else "候选人"
            content = msg["content"][:500]
            history_text += f"{role_label}: {content}\n\n"

        messages.append({"role": "user", "content": f"以下是本次面试的对话记录：\n\n{history_text}{draft_context}\n\n请生成评估报告。"})

        try:
            if self.llm_client:
                raw = self.llm_client.generate(messages)
            else:
                return {}

            # 解析 JSON
            import re
            json_match = re.search(r'\{[\s\S]*\}', raw)
            if json_match:
                result = json.loads(json_match.group())
                return result
        except Exception as e:
            print(f"[evaluate_interview] 评估生成失败: {e}")
            traceback.print_exc()
        return {}

    def set_max_history_turns(self, max_turns: int):
        self.max_history_turns = max_turns
        if max_turns > 0:
            max_messages = max_turns * 2
            if len(self.chat_history) > max_messages:
                self.chat_history = self.chat_history[-max_messages:]

    def _merge_custom_prompt_context(
        self,
        custom_prompt: str,
        resume_summary: str = "",
        rag_context: str = "",
        job_requirements: str = "",
    ) -> str:
        """Keep externally generated prompts, but backfill missing runtime context."""
        merged = custom_prompt or ""

        if resume_summary:
            has_resume_anchor = (
                "候选人简历摘要" in merged
                or "简历摘要" in merged
                or resume_summary[:80] in merged
            )
            if not has_resume_anchor:
                merged += (
                    "\n\n## 候选人简历摘要（运行时补充注入）\n"
                    f"{resume_summary}\n"
                )

        if rag_context:
            has_rag_anchor = (
                "知识库参考" in merged
                or "RAG" in merged
                or rag_context[:80] in merged
            )
            if not has_rag_anchor:
                merged += (
                    "\n\n## 知识库参考（运行时补充注入，仅供出题和评分参考，不要直接暴露给候选人）\n"
                    f"{rag_context}\n"
                )

        if job_requirements:
            has_job_requirements_anchor = (
                "岗位要求" in merged
                or "职位描述" in merged
                or job_requirements[:80] in merged
            )
            if not has_job_requirements_anchor:
                merged += (
                    "\n\n## 岗位要求（运行时补充注入，用于考察重点和评分基准，不代表候选人已具备）\n"
                    f"{job_requirements}\n"
                    "\n请仅将上述内容作为本场面试的岗位考察标准和评分基准，"
                    "不要把它当作候选人的真实经历、技能或项目事实。\n"
                )

        return merged

    def update_dynamic_prompt(self, job_title: str, interview_type: str, difficulty: str,
                              style: str, feature_vad: bool, feature_deep: bool,
                              resume_summary: str = "", custom_prompt: str = "",
                              job_requirements: str = "",
                              rag_context: str = ""):
        """基于前端传递的详细参数，动态生成 System Prompt。

        Args:
            custom_prompt: 由 PromptGenerator 外部生成时直接使用，跳过 prompt_manager。
            resume_summary: 简历解析摘要，注入 prompt 作为事实锚点。
            rag_context: RAG 检索结果，注入 prompt 作为出题和评分参考。
        """
        from datetime import datetime
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # ===== 记录 Prompt 来源 =====
        prompt_source = ""
        new_prompt = ""
        
        if custom_prompt:
            # ✅ custom_prompt 优先级最高，但仍需补齐运行时上下文
            new_prompt = self._merge_custom_prompt_context(
                custom_prompt=custom_prompt,
                resume_summary=resume_summary,
                rag_context=rag_context,
                job_requirements=job_requirements,
            )
            prompt_source = "custom_prompt (外部传入，已补齐运行时上下文)"
        elif self.prompt_manager:
            # ✅ 使用 prompt_manager 生成默认 prompt
            new_prompt = self.prompt_manager.generate_system_prompt(
                job_title=job_title,
                interview_type=interview_type,
                difficulty=difficulty,
                style=style,
                feature_vad=feature_vad,
                feature_deep=feature_deep,
                resume_summary=resume_summary,
                rag_context=rag_context,
                job_requirements=job_requirements,
            )
            prompt_source = "prompt_manager (默认生成)"
        else:
            # ✅ 降级方案：使用 JSON 配置
            self.update_system_prompt(style)
            return

        # ===== 组装最终 prompt =====
        self.prompt = f"[当前系统时间：{current_time}]\n\n{new_prompt}"
        self.current_style = style

        # ===== 日志打印：完整记录上传至大模型的 sysprompt =====
        print(f"\n{'='*80}")
        print(f"[{current_time}] 📋 系统提示词 (System Prompt) 已更新")
        print(f"{'='*80}")
        print(f"📌 Prompt 来源：{prompt_source}")
        print(f"📌 参数信息:")
        print(f"   - 目标岗位：{job_title}")
        print(f"   - 面试轮次：{interview_type}")
        print(f"   - 难度级别：{difficulty}")
        print(f"   - 面试风格：{style}")
        print(f"   - 功能开关：VAD={feature_vad}, Deep={feature_deep}")
        print(f"   - 简历摘要：{'有' if resume_summary else '无'} ({len(resume_summary)} 字符)")
        print(f"   - 岗位要求：{'有' if job_requirements else '无'} ({len(job_requirements)} 字符)")
        print(f"   - RAG 上下文：{'有' if rag_context else '无'} ({len(rag_context)} 字符)")
        print(f"   - custom_prompt: {'有' if custom_prompt else '无'} ({len(custom_prompt)} 字符)")
        print(f"{'='*80}")
        print(f"📄 完整 System Prompt 内容:")
        print(f"{'-'*80}")
        print(self.prompt)
        print(f"{'-'*80}")
        print(f"📊 Prompt 统计:")
        print(f"   - 总字符数：{len(self.prompt)}")
        print(f"   - 预计 token 数：~{len(self.prompt) // 4}")
        print(f"{'='*80}\n")

        if self.verbose:
            print(f"Info: 正在重建 Agent 以应用新 prompt...\n")

        self._build_agent_executor()
    
    def update_system_prompt(self, style: str = "default"):
        """动态更新系统 Prompt（基于 JSON 配置的回退方案）"""
        base_prompt = self._build_prompt()
        styles = self.prompt_config.get("styles", {})
        style_config = styles.get(style, styles.get("default", {}))
        style_injection = style_config.get("injection", "")

        self.prompt = base_prompt + style_injection if style_injection else base_prompt
        self.current_style = style

        if self.verbose:
            style_name = style_config.get("name", style)
            print(f"Info: Switched to interview style: {style_name}")

        self._build_agent_executor()


if __name__ == "__main__":
    try:
        from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, reload_runtime_settings

        reload_runtime_settings()
        api_key = DEEPSEEK_API_KEY
        base_url = DEEPSEEK_BASE_URL
    except Exception:
        load_dotenv()
        api_key = os.getenv("DEEPSEEK_API_KEY", "")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

    try:
        from langchain.tools import Tool
    except Exception:
        try:
            from langchain_core.tools import Tool
        except Exception:
            Tool = None

    try:
        from core.langfuse_tracing import get_langfuse_callback_handler
    except Exception:
        try:
            from langfuse_tracing import get_langfuse_callback_handler
        except Exception:
            def get_langfuse_callback_handler():
                return None

    def demo_candidate_profile(candidate_name: str) -> str:
        """Return a deterministic candidate profile for Langfuse agent tracing demos."""
        raw_name = str(candidate_name or "").strip()
        try:
            parsed = json.loads(raw_name)
            if isinstance(parsed, dict):
                raw_name = parsed.get("candidate_name") or parsed.get("name") or raw_name
        except Exception:
            pass
        raw_name = raw_name.strip().strip('"').strip("'") or "张三"
        return (
            f"{raw_name} 的候选人画像：3 年 Python 后端经验，"
            "熟悉 FastAPI、SQLAlchemy、Redis 和异步任务处理；"
            "最近项目是 AI 面试系统，负责 Agent 编排、LLM 调用和可观测性建设。"
        )

    print("=== Langfuse LangChain Agent Tool Trace Demo ===")
    print(f"LangChain available: {HAVE_LANGCHAIN}")
    print(f"ChatOpenAI available: {ChatOpenAI is not None}")
    print(f"Tool available: {Tool is not None}")
    print(f"ReAct agent available: {initialize_agent_fn is not None and AgentTypeEnum is not None}")
    print(f"Langfuse callback enabled: {get_langfuse_callback_handler() is not None}")
    print(f"LLM API key configured: {bool(api_key)}")
    print(f"LLM base_url: {base_url}")
    print()

    interviewer = LangChainInterviewAgent(
        api_key=api_key,
        base_url=base_url,
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        verbose=True,
        max_history_turns=3,
        role="interviewer",
    )

    if (
        Tool is not None
        and ChatOpenAI is not None
        and initialize_agent_fn is not None
        and AgentTypeEnum is not None
    ):
        demo_tool = Tool.from_function(
            func=demo_candidate_profile,
            name="demo_candidate_profile",
            description=(
                "Use this first to look up a candidate profile. "
                "Input must be the candidate name as plain text, for example: 张三."
            ),
        )
        interviewer.tools = [demo_tool]
        react_llm = ChatOpenAI(
            model=interviewer.model_name,
            api_key=api_key,
            base_url=base_url,
            temperature=0,
        )
        interviewer.agent_executor = initialize_agent_fn(
            tools=[demo_tool],
            llm=react_llm,
            agent=AgentTypeEnum.ZERO_SHOT_REACT_DESCRIPTION,
            verbose=True,
            handle_parsing_errors=True,
            return_intermediate_steps=True,
            max_iterations=3,
            agent_kwargs={
                "prefix": (
                    "You are a Python backend technical interviewer. "
                    "You must use demo_candidate_profile before answering any question about a candidate. "
                    "After using the tool, answer in Chinese with one concise interview opening and one concrete question."
                )
            },
        )
        print("Using ReAct Agent demo so LangChain can execute a real tool call without OpenAI function calling.")
    else:
        print("ReAct demo dependencies are unavailable; this run can only demonstrate LLM tracing, not tool tracing.")

    test_query = (
        "You must use the demo_candidate_profile tool first. "
        "Candidate name: 张三. After the observation, answer in Chinese and ask one Python backend interview question."
    )
    print("=== Test Query ===")
    print(test_query)
    print()

    response, steps = interviewer.run(test_query)

    print("=== Agent Response ===")
    print(response)
    print()
    print("=== Intermediate Steps ===")
    print(json.dumps(steps, ensure_ascii=False, indent=2))
    print()
    print("If Langfuse callback enabled=True, open Langfuse and inspect this trace's AgentExecutor, LLM, and tool spans.")

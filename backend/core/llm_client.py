import os
from typing import Generator, Tuple
from openai import OpenAI


class OpenAICompatibleClient:
    """
    一个用于调用任何兼容OpenAI接口的LLM服务的客户端。
    """

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, messages: list) -> str:
        """调用LLM API来生成回应。"""
        print("正在调用大语言模型...")
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=False,
            )
            answer = response.choices[0].message.content
            print("大语言模型响应成功。")
            return answer
        except Exception as e:
            print(f"调用LLM API时发生错误: {e}")
            return f"错误: 调用语言模型服务时出错: {e}"

    def generate_stream(self, messages: list) -> Generator[str, None, None]:
        """流式调用 LLM API，逐 chunk 返回文本片段（仅 content）。"""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )
            for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if delta and delta.content:
                    yield delta.content
        except Exception as e:
            print(f"流式调用LLM API时发生错误: {e}")
            yield f"[错误: {e}]"

    def generate_stream_with_reasoning(self, messages: list) -> Generator[Tuple[str, str], None, None]:
        """
        流式调用 LLM API，区分思维链和正式回复。
        yield ("thinking", chunk) — 思维链片段（reasoning_content）
        yield ("content", chunk) — 正式回复片段（content）
        支持 DeepSeek / 文心一言 thinking 模型的 reasoning_content 字段。
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )
            for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue
                # 思维链内容（reasoning_content / reasoning）
                reasoning = getattr(delta, 'reasoning_content', None) or getattr(delta, 'reasoning', None)
                if reasoning:
                    yield ("thinking", reasoning)
                # 正式回复内容
                if delta.content:
                    yield ("content", delta.content)
        except Exception as e:
            print(f"流式调用LLM API时发生错误: {e}")
            yield ("content", f"[错误: {e}]")

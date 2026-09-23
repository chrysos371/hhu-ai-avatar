"""大语言模型接入：OpenAI 兼容接口。"""
from __future__ import annotations

from typing import Optional

from openai import OpenAI

from ..config import config


class LLMEngine:
    """OpenAI 兼容的 LLM 客户端，一套接口通吃 DeepSeek/通义/Kimi/本地 vLLM/Ollama。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self.base_url = base_url or config.llm.base_url
        self.api_key = api_key or config.llm.api_key
        self.model = model or config.llm.model
        self.available = bool(self.api_key)
        self._client = None
        if self.available:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def chat(
        self,
        messages: list[dict],
        temperature: float = 0.8,
        max_tokens: int = 512,
    ) -> str:
        """发送对话，返回助手回复文本。"""
        if not self.available or self._client is None:
            raise RuntimeError("LLM 未配置：请在 .env 设置 LLM_API_KEY")
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

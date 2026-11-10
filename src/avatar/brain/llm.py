"""大语言模型接入：OpenAI 兼容接口。"""
from __future__ import annotations

from typing import Optional

from openai import OpenAI, AsyncOpenAI

from ..config import config
from .analysis_protocol import ANALYSIS_RESPONSE_FORMAT
from .response_review import REVIEW_FORMATS
from ..cancellation import CancellationToken


class LLMEngine:
    """OpenAI 兼容的 LLM 客户端，一套接口通吃 DeepSeek/通义/Kimi/本地 vLLM/Ollama。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 0,
    ):
        self.base_url = base_url or config.llm.base_url
        self.api_key = api_key or config.llm.api_key
        self.model = model or config.llm.model
        self.timeout = timeout
        self.available = bool(self.api_key)
        self._client = None
        if self.available:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key,
                                  timeout=timeout, max_retries=max_retries)

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

    def chat_tools(self, messages: list[dict], *, tools: list[dict],
                   temperature: float = 0.2, max_tokens: int = 768) -> dict:
        """Preserve native tool calls; ordinary chat and cognitive analysis stay unchanged."""
        if not self.available or self._client is None:
            raise RuntimeError('LLM未配置，不能进行原生工具选择。')
        options = dict(model=self.model, messages=messages, temperature=temperature,
                       max_tokens=max_tokens, timeout=45)
        if tools:
            options['tools'] = tools
        response = self._client.chat.completions.create(**options)
        return response.choices[0].message.model_dump(exclude_none=True)

    def chat_analysis(self, messages: list[dict], temperature: float = 0) -> str:
        """Request constrained JSON; unsupported endpoints fail into visible rule fallback."""
        if not self.available or self._client is None:
            raise RuntimeError('LLM 未配置')
        response = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, max_tokens=512,
            response_format=ANALYSIS_RESPONSE_FORMAT, timeout=45)
        return response.choices[0].message.content or ''

    def chat_web(self, messages: list[dict]) -> str:
        """Bounded synthesis after a tool chain, without exposing more tools."""
        return self.chat_tools(messages, tools=[]).get('content') or ''

    def stream_chat(self, messages, *, temperature=0.8, max_tokens=512,
                    cancel=None, on_delta=None, response_format=None):
        """Stream over an interruptible async transport, including response headers."""
        if not self.available:
            raise RuntimeError("LLM 未配置")
        token = cancel or CancellationToken()
        async def run():
            options = dict(model=self.model, messages=messages, temperature=temperature,
                           max_tokens=max_tokens, stream=True)
            if response_format is not None:
                options["response_format"] = response_format
            parts, characters = [], 0
            async with AsyncOpenAI(base_url=self.base_url, api_key=self.api_key,
                                   timeout=self.timeout, max_retries=0) as client:
                stream = await client.chat.completions.create(**options)
                async with stream:
                    async for chunk in stream:
                        token.checkpoint()
                        text = chunk.choices[0].delta.content if chunk.choices else None
                        if not isinstance(text, str) or not text:
                            continue
                        characters += len(text)
                        if characters > 16000:
                            raise ValueError("stream response exceeds character limit")
                        parts.append(text)
                        if on_delta:
                            on_delta(text)
            token.checkpoint()
            return ''.join(parts)
        return token.run_async(run, timeout=self.timeout)

    def chat_analysis_stream(self, messages, *, temperature=0, cancel=None):
        return self.stream_chat(messages, temperature=temperature, cancel=cancel,
                                response_format=ANALYSIS_RESPONSE_FORMAT)

    def review_response(self, messages, *, cancel=None, version='v1'):
        """Experimental structured triage, kept separate from cognitive analysis."""
        if version not in REVIEW_FORMATS:
            raise ValueError('Unknown review protocol version')
        return self.stream_chat(messages, temperature=0, max_tokens=384, cancel=cancel,
                                response_format=REVIEW_FORMATS[version])

    def compose_literal_slots(self, messages, layout, *, cancel=None):
        """Plan surrounding text; immutable user literals are rendered locally."""
        return self.stream_chat(layout.messages(messages), temperature=0, max_tokens=512,
            cancel=cancel, on_delta=None, response_format=layout.response_format)

    def close(self):
        if self._client is not None:
            self._client.close()

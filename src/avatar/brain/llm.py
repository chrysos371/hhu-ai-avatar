"""大语言模型接入：OpenAI 兼容接口。"""
from __future__ import annotations

from typing import Optional
import os

from openai import OpenAI

from ..config import config
from .analysis_protocol import ANALYSIS_RESPONSE_FORMAT


class LLMEngine:
    """OpenAI 兼容的 LLM 客户端，一套接口通吃 DeepSeek/通义/Kimi/本地 vLLM/Ollama。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        profile=None,
    ):
        self.profile = profile
        self.profile_id = profile.id if profile else 'default'
        self.protocol_fallbacks = []
        self.base_url = profile.base_url if profile else (base_url or config.llm.base_url)
        self.api_key = os.getenv(profile.api_key_env, '') if profile else (api_key or config.llm.api_key)
        self.model = profile.model if profile else (model or config.llm.model)
        self.available = bool(self.api_key)
        self._client = None
        if self.available:
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)

    def _options(self):
        if self.profile and self.profile.thinking is not None:
            return {'extra_body': {'chat_template_kwargs': {'enable_thinking': self.profile.thinking}}}
        return {}

    @staticmethod
    def _content(response):
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError('No visible model reply')
        # Never expose an endpoint's reasoning stream as the user-facing reply.
        if '<think>' in content or '</think>' in content:
            import re
            content = re.sub(r'<think>.*?</think>', '', content, flags=re.S).strip()
            if '<think>' in content or '</think>' in content or not content:
                raise ValueError('Incomplete reasoning output')
        return content

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
            **self._options(),
        )
        return self._content(resp)

    def chat_tools(self, messages: list[dict], *, tools: list[dict],
                   temperature: float = 0.2, max_tokens: int = 768) -> dict:
        """Preserve native tool calls; ordinary chat and cognitive analysis stay unchanged."""
        if not self.available or self._client is None:
            raise RuntimeError('LLM未配置，不能进行原生工具选择。')
        if tools and self.profile and not self.profile.tools:
            self.protocol_fallbacks.append('native_tools_unsupported')
            raise ValueError('Model profile does not support native tools')
        options = dict(model=self.model, messages=messages, temperature=temperature,
                       max_tokens=max_tokens, timeout=45)
        options.update(self._options())
        if tools:
            options['tools'] = tools
        response = self._client.chat.completions.create(**options)
        message = response.choices[0].message.model_dump(exclude_none=True)
        # Only fields needed by the tool executor; omit provider reasoning fields.
        result = {k:v for k,v in message.items() if k in ('role','content','tool_calls')}
        if result.get('content'):
            result['content'] = self._content(response)
        return result

    def chat_analysis(self, messages: list[dict], temperature: float = 0) -> str:
        """Request constrained JSON; unsupported endpoints fail into visible rule fallback."""
        if not self.available or self._client is None:
            raise RuntimeError('LLM 未配置')
        mode = self.profile.structured_analysis if self.profile else 'json_schema'
        if mode == 'none':
            self.protocol_fallbacks.append('structured_analysis_unsupported')
            raise ValueError('Structured analysis unsupported; use visible rule fallback')
        response = self._client.chat.completions.create(
            model=self.model, messages=messages, temperature=temperature, max_tokens=512,
            response_format=ANALYSIS_RESPONSE_FORMAT if mode == 'json_schema' else {'type':'json_object'}, timeout=45,
            **self._options())
        return self._content(response)

    def chat_web(self, messages: list[dict]) -> str:
        """Bounded synthesis after a tool chain, without exposing more tools."""
        return self.chat_tools(messages, tools=[]).get('content') or ''

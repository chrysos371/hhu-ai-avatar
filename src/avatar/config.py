"""全局配置：从环境变量 / .env 文件读取。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# 加载项目根目录下的 .env（若存在）
load_dotenv()


def _get(key: str, default: str = "") -> str:
    return os.getenv(key, default)


@dataclass
class LLMConfig:
    """大语言模型接入配置（OpenAI 兼容接口）。"""

    base_url: str = field(
        default_factory=lambda: _get("LLM_BASE_URL", "https://api.deepseek.com/v1")
    )
    api_key: str = field(default_factory=lambda: _get("LLM_API_KEY", ""))
    model: str = field(default_factory=lambda: _get("LLM_MODEL", "deepseek-chat"))


@dataclass
class Config:
    """项目全局配置。"""

    llm: LLMConfig = field(default_factory=LLMConfig)
    avatar_name: str = field(default_factory=lambda: _get("AVATAR_NAME", "小海"))
    avatar_persona: str = field(
        default_factory=lambda: _get("AVATAR_PERSONA", "一个温柔又有点好奇心的AI伙伴")
    )
    memory_db_path: str = field(
        default_factory=lambda: _get("MEMORY_DB_PATH", "./data/memory.db")
    )
    sample_rate: int = field(
        default_factory=lambda: int(_get("AUDIO_SAMPLE_RATE", "24000"))
    )


# 模块级单例：`from avatar.config import config`
config = Config()

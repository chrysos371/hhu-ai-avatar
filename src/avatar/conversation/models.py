"""Configured profiles, independent of character personas; secrets stay in env."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ModelProfile:
    id: str
    model: str
    base_url: str
    api_key_env: str = 'LLM_API_KEY'
    structured_analysis: str = 'json_schema'
    tools: bool = True
    thinking: bool | None = None

    def __post_init__(self):
        if (not self.id or not self.model or urlsplit(self.base_url).scheme not in ('http','https')
                or urlsplit(self.base_url).username or urlsplit(self.base_url).password
                or urlsplit(self.base_url).query
                or self.structured_analysis not in ('json_schema','json_object','none')
                or type(self.tools) is not bool or (self.thinking is not None and type(self.thinking) is not bool)):
            raise ValueError('Invalid model profile')

    def public(self):
        return {'id': self.id, 'model': self.model, 'structured_analysis': self.structured_analysis,
                'tools': self.tools, 'thinking': self.thinking}


def profiles():
    from ..config import config
    result = {'default': ModelProfile('default', config.llm.model, config.llm.base_url)}
    path = os.getenv('AVATAR_MODEL_PROFILES')
    if path:
        for row in json.loads(Path(path).read_text()):
            profile = ModelProfile(**row)
            if profile.id in result:
                raise ValueError('Duplicate model profile')
            result[profile.id] = profile
    return result


def create_llm(profile_id):
    from ..brain.llm import LLMEngine
    return LLMEngine(profile=profiles()[profile_id])

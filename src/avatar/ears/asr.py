"""语音识别（ASR）：FunASR 实现 + 文本降级。"""
from __future__ import annotations

from typing import Protocol


class ASREngine(Protocol):
    def transcribe(self, audio_path: str) -> str:
        """音频文件 → 文本。"""
        ...


class FunASREngine:
    """FunASR 中文语音识别（需 `pip install funasr`，首次运行会下载模型）。"""

    def __init__(self, model: str = "paraformer-zh"):
        from funasr import AutoModel  # 延迟导入，避免强依赖

        self.model = AutoModel(model=model)

    def transcribe(self, audio_path: str) -> str:
        result = self.model.generate(input=audio_path)
        return result[0]["text"] if result else ""


class TextInputEngine:
    """降级：不做语音识别，直接把输入当作文本（demo 模式）。"""

    def transcribe(self, text_or_path: str) -> str:
        return text_or_path

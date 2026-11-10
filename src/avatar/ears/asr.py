"""语音识别（ASR）：FunASR 实现 + 文本降级。"""
from __future__ import annotations

from typing import Protocol


class ASREngine(Protocol):
    def transcribe(self, audio_path: str) -> str:
        """音频文件 → 文本。"""
        ...


class FunASREngine:
    """FunASR 中文语音识别（需 `pip install funasr`，首次运行会下载模型）。"""

    def __init__(self, model: str = "paraformer-zh", device: str = "cpu"):
        from funasr import AutoModel  # 延迟导入，避免强依赖

        self.model = AutoModel(model=model, device=device, disable_update=True)

    def transcribe(self, audio_path: str) -> str:
        result = self.model.generate(input=audio_path)
        return result[0]["text"] if result else ""


class TextInputEngine:
    """降级：不做语音识别，直接把输入当作文本（demo 模式）。"""

    def transcribe(self, text_or_path: str) -> str:
        return text_or_path


class FasterWhisperEngine:
    """Local CTranslate2 model; optional dependency, no implicit model download."""

    def __init__(self, model_path: str, *, device: str = 'cpu', cpu_threads: int = 4):
        from pathlib import Path
        from faster_whisper import WhisperModel
        path = Path(model_path).expanduser().resolve()
        if not path.is_dir():
            raise ValueError('ASR 模型目录不存在')
        if device not in ('cpu', 'cuda'):
            raise ValueError('ASR device must be cpu or cuda; select visible GPUs explicitly')
        self.model = WhisperModel(str(path), device=device,
            compute_type='int8_float16' if device == 'cuda' else 'int8',
            cpu_threads=cpu_threads, num_workers=1, local_files_only=True)

    def transcribe(self, audio_path: str) -> str:
        segments, _ = self.model.transcribe(audio_path, language='zh', beam_size=5,
            vad_filter=True, condition_on_previous_text=False, temperature=0,
            initial_prompt='以下是普通话，请使用简体中文。')
        return ''.join(segment.text for segment in segments).strip()

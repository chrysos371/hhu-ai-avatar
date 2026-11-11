"""语音合成（TTS）：Edge-TTS 实现。"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
import tempfile
from typing import Protocol

import edge_tts
from ..cancellation import CancellationToken


class TTSEngine(Protocol):
    def synthesize(
        self, text: str, out_path: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> str:
        """文本 → 语音文件，返回文件路径。"""
        ...


class EdgeTTSEngine:
    """微软 Edge-TTS：免费、中文自然、零部署。输出 mp3。"""

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural", timeout: float = 30.0):
        self.voice = voice
        self.timeout = timeout

    def synthesize(
        self, text: str, out_path: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> str:
        return self.synthesize_cancellable(text, out_path, rate, pitch)

    def synthesize_cancellable(self, text, out_path, rate="+0%", pitch="+0Hz", *, cancel=None):
        """Publish a complete MP3 atomically; failed/cancelled saves retain the target."""
        token = cancel or CancellationToken()
        token.checkpoint()
        target = Path(out_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, owned_path = tempfile.mkstemp(prefix='.avatar-tts-', suffix='.part', dir=target.parent)
        os.close(descriptor)
        staged = Path(owned_path)

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice, rate=rate, pitch=pitch)
            await asyncio.wait_for(communicate.save(str(staged)), timeout=self.timeout)
            token.checkpoint()
            if staged.stat().st_size == 0:
                raise ValueError('TTS produced an empty audio file')
            os.replace(staged, target)

        try:
            token.run_async(_run)
            return out_path
        finally:
            staged.unlink(missing_ok=True)

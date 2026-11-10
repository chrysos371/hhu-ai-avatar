"""语音合成（TTS）：Edge-TTS 实现。"""
from __future__ import annotations

import asyncio
from pathlib import Path
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
        """合成到 MP3；取消时关闭本机异步网络任务。"""

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice, rate=rate, pitch=pitch)
            await asyncio.wait_for(communicate.save(out_path), timeout=self.timeout)

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        (cancel or CancellationToken()).run_async(_run)
        return out_path

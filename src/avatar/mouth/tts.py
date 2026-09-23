"""语音合成（TTS）：Edge-TTS 实现。"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

import edge_tts


class TTSEngine(Protocol):
    def synthesize(
        self, text: str, out_path: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> str:
        """文本 → 语音文件，返回文件路径。"""
        ...


class EdgeTTSEngine:
    """微软 Edge-TTS：免费、中文自然、零部署。输出 mp3。"""

    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"):
        self.voice = voice

    def synthesize(
        self, text: str, out_path: str, rate: str = "+0%", pitch: str = "+0Hz"
    ) -> str:
        """合成语音到 out_path（mp3），返回路径。"""

        async def _run() -> None:
            communicate = edge_tts.Communicate(text, self.voice, rate=rate, pitch=pitch)
            await communicate.save(out_path)

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(_run())
        return out_path

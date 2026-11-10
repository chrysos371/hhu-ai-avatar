"""Explicit, local-only WAV transcription; never sends or remembers a message."""
from __future__ import annotations

import io
from pathlib import Path
import tempfile
import threading
import wave

from .brain.operations import OperationError


class TranscriptionService:
    MAX_BYTES = 6 * 1024 * 1024
    MAX_SECONDS = 60

    def __init__(self, engine=None):
        self.engine = engine
        self._busy = threading.Lock()

    def capabilities(self):
        return {"asr_enabled": self.engine is not None, "format": "audio/wav",
                "max_seconds": self.MAX_SECONDS, "max_bytes": self.MAX_BYTES,
                "reason": None if self.engine else "语音识别未启用；请先配置本机 ASR 模型。"}

    def transcribe(self, audio):
        if self.engine is None:
            raise OperationError(503, "asr_disabled", "本机语音识别尚未启用，请使用文字输入。")
        if not 0 < len(audio) <= self.MAX_BYTES:
            raise OperationError(422, "invalid_audio", "音频文件为空或超过 6 MiB。")
        try:
            with wave.open(io.BytesIO(audio), "rb") as stream:
                channels, width, sr, frames, compression, _ = stream.getparams()
                if (channels not in (1, 2) or width != 2 or not 8000 <= sr <= 48000
                        or compression != "NONE" or not 0 < frames / sr <= self.MAX_SECONDS):
                    raise ValueError("invalid PCM WAV")
                if len(stream.readframes(frames)) != frames * channels * width:
                    raise ValueError("truncated PCM WAV")
        except (wave.Error, EOFError, ValueError):
            raise OperationError(422, "invalid_audio", "请使用 60 秒内、8–48 kHz、16 位 PCM WAV 文件。") from None
        if not self._busy.acquire(blocking=False):
            raise OperationError(429, "asr_busy", "正在识别其他音频，请稍后重试。")
        try:
            with tempfile.TemporaryDirectory(prefix="avatar-asr-") as folder:
                path = Path(folder) / "input.wav"
                path.write_bytes(audio)
                text = self.engine.transcribe(str(path))
            if not isinstance(text, str) or not text.strip():
                raise OperationError(422, "empty_transcript", "没有识别到语音，请靠近麦克风后重试。")
            if len(text.strip()) > 4000:
                raise OperationError(422, "transcript_too_long", "识别结果过长，请使用较短录音。")
            return {"transcript": text.strip()}
        except OperationError:
            raise
        except Exception:
            raise OperationError(503, "asr_unavailable", "本机语音识别失败，请重试或使用文字输入。") from None
        finally:
            self._busy.release()

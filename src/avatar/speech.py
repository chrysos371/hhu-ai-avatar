"""On-demand speech with bounded, ephemeral audio storage for the local UI."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
import math
import re
import secrets
import tempfile
import threading
import time

import numpy as np

from .brain.operations import OperationError
from .face.lipsync import LipSyncEngine
from .mouth.tts import EdgeTTSEngine
from .utils.audio import load_audio
from .cancellation import CancellationToken, Cancelled


class SpeechService:
    MAX_AUDIO_BYTES = 8 * 1024 * 1024
    MAX_CACHE_BYTES = 32 * 1024 * 1024
    MAX_SECONDS = 120

    def __init__(self, engine=None, *, clock=time.time, ttl=900, max_items=8):
        self.engine = engine or EdgeTTSEngine()
        self.clock, self.ttl, self.max_items = clock, ttl, max_items
        self._audio = OrderedDict()
        self._lock = threading.Lock()
        self._busy = threading.Lock()
        self._active_lock = threading.Lock()
        self._active = {}
        self._cancelled = OrderedDict()

    def cancel(self, request_id):
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', request_id):
            raise OperationError(422, 'invalid_speech_request', '语音请求编号无效。')
        with self._active_lock:
            self._cancelled[request_id] = time.monotonic()
            while len(self._cancelled) > 64:
                self._cancelled.popitem(last=False)
            token = self._active.get(request_id)
        if token:
            token.cancel()
        return {'cancelled': True}

    def close(self):
        with self._active_lock:
            active = tuple(self._active.values())
        for token in active:
            token.cancel()

    def _prune(self):
        now = self.clock()
        for key in list(self._audio):
            if self._audio[key][0] <= now:
                del self._audio[key]

    def synthesize(self, data):
        if not isinstance(data, dict) or not set(data) <= {"text", "rate", "pitch", "mouth_intensity", "request_id"}:
            raise OperationError(422, "invalid_speech", "朗读参数无效。")
        text = data.get("text")
        rate, pitch = data.get("rate", "+0%"), data.get("pitch", "+0Hz")
        intensity = data.get("mouth_intensity", 0.75)
        request_id = data.get('request_id', secrets.token_urlsafe(24))
        if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', request_id):
            raise OperationError(422, 'invalid_speech_request', '语音请求编号无效。')
        if (not isinstance(text, str) or not 1 <= len(text.strip()) <= 2000
                or not isinstance(rate, str) or not re.fullmatch(r"[+-]\d{1,2}%", rate)
                or not -30 <= int(rate[:-1]) <= 30
                or not isinstance(pitch, str) or not re.fullmatch(r"[+-]\d{1,2}Hz", pitch)
                or not -20 <= int(pitch[:-2]) <= 20
                or type(intensity) not in (int, float) or not math.isfinite(intensity)
                or not 0.1 <= intensity <= 1.2):
            raise OperationError(422, "invalid_speech", "朗读限 2000 字，语音参数超出支持范围。")
        if not self._busy.acquire(blocking=False):
            raise OperationError(429, "speech_busy", "正在生成其他语音，请稍后重试。")
        token = CancellationToken()
        try:
            with self._active_lock:
                if request_id in self._cancelled:
                    token.cancel()
                self._active[request_id] = token
            token.checkpoint()
            with tempfile.TemporaryDirectory(prefix="avatar-speech-") as folder:
                target = Path(folder) / "reply.mp3"
                if hasattr(self.engine, 'synthesize_cancellable'):
                    self.engine.synthesize_cancellable(text.strip(), str(target), rate, pitch, cancel=token)
                else:
                    self.engine.synthesize(text.strip(), str(target), rate, pitch)
                token.checkpoint()
                if not target.is_file() or not 0 < target.stat().st_size <= self.MAX_AUDIO_BYTES:
                    raise ValueError("invalid audio size")
                audio = target.read_bytes()
                content_type = "audio/wav" if audio[:4] == b"RIFF" and audio[8:12] == b"WAVE" else "audio/mpeg"
                frames, duration, warning = [], None, None
                try:
                    samples, sr = load_audio(target)
                    duration = len(samples) / sr
                    if not 0 < duration <= self.MAX_SECONDS:
                        raise OperationError(422, "speech_too_long", "语音超过 120 秒，请缩短朗读内容。")
                    # Limit analysis cost independently of the synthesizer's sample rate.
                    if sr > 16000:
                        samples = np.interp(np.arange(0, len(samples), sr / 16000), np.arange(len(samples)), samples).astype(np.float32)
                        sr = 16000
                    frames = [asdict(frame) | {"mouth_open": min(1.0, frame.mouth_open * intensity)}
                              for frame in LipSyncEngine().analyze(samples, sr, cancel=token)]
                except Cancelled:
                    raise
                except OperationError:
                    raise
                except Exception:
                    warning = "语音已生成，口型分析不可用；可安装音频扩展后重试。"
            key, expires = secrets.token_urlsafe(24), self.clock() + self.ttl
            token.checkpoint()
            with self._lock:
                self._prune()
                while self._audio and (len(self._audio) >= self.max_items
                        or sum(len(item[1]) for item in self._audio.values()) + len(audio) > self.MAX_CACHE_BYTES):
                    self._audio.popitem(last=False)
                self._audio[key] = (expires, audio, content_type)
            return {"audio_id": key, "duration": duration, "frames": frames,
                    "expires_at": expires, "warning": warning}
        except Cancelled:
            raise OperationError(409, 'speech_cancelled', '语音生成已停止。') from None
        except OperationError:
            raise
        except Exception:
            raise OperationError(503, "speech_unavailable", "语音生成失败或超时，文字回复已保留，可稍后重试。") from None
        finally:
            with self._active_lock:
                self._active.pop(request_id, None)
            self._busy.release()

    def read(self, key):
        with self._lock:
            self._prune()
            item = self._audio.get(key)
            if item is None:
                raise OperationError(404, "audio_expired", "音频已过期，请重新生成。")
            return item[1], item[2]

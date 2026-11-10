"""Disposable, offline browser-test fixture. Never opens the user's database."""

from pathlib import Path
import os
import tempfile
import wave
import numpy as np
from avatar.config import config
from avatar.brain.memory import MemoryStore
from avatar.web import create_server

root = Path(__file__).resolve().parents[3]
folder = tempfile.TemporaryDirectory(prefix="admin-e2e-", dir=root / "runtime/tmp")
config.llm.api_key = ""
config.embedding.model = ""
memory = MemoryStore(str(Path(folder.name) / "browser.db"))
memory.remember_user("名字", "浏览器测试原名")
memory.close()
server = create_server(
    str(Path(folder.name) / "browser.db"), port=18765, legacy_writes=False
)

# Offline fixtures exercise real browser codecs/AudioWorklet without network or models.
class FixtureTTS:
    def synthesize(self, text, path, rate, pitch):
        t = np.arange(48000) / 16000
        samples = 0.25 * np.sin(2 * np.pi * 220 * t)
        samples[(t % 1) > 0.7] = 0
        with wave.open(path, "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes((samples * 32767).astype("<i2").tobytes())
        return path

class FixtureASR:
    def transcribe(self, path):
        with wave.open(path) as stream:
            assert stream.getnframes() > 0
        return "浏览器识别草稿"

if os.getenv("AVATAR_E2E_REAL_TTS") != "1":
    server.speech.engine = FixtureTTS()
server.transcription.engine = FixtureASR()
server.token = "mission-control-disposable-e2e-token"
try:
    server.serve_forever()
finally:
    server.server_close()
    folder.cleanup()

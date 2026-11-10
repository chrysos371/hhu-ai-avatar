import json
import threading
import urllib.error
import urllib.request
import wave

import numpy as np
import pytest

from avatar.brain.operations import OperationError
from avatar.speech import SpeechService
from avatar.web import create_server


class WaveTTS:
    def __init__(self, silent=False):
        self.silent = silent
        self.calls = []

    def synthesize(self, text, path, rate, pitch):
        self.calls.append((text, rate, pitch))
        t = np.arange(8000) / 16000
        samples = np.zeros(8000) if self.silent else 0.2 * np.sin(2 * np.pi * 220 * t)
        with wave.open(path, "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes((samples * 32767).astype("<i2").tobytes())
        return path


def test_speech_timeline_expiry_eviction_and_silence():
    clock = [100]
    engine = WaveTTS(silent=True)
    service = SpeechService(engine, clock=lambda: clock[0], ttl=10, max_items=1)
    first = service.synthesize({"text": "你好", "rate": "-10%", "pitch": "-5Hz"})
    assert first["duration"] == 0.5 and first["warning"] is None
    assert first["frames"] and all(f["mouth_open"] == 0 for f in first["frames"])
    assert engine.calls == [("你好", "-10%", "-5Hz")]
    assert service.read(first["audio_id"])[1] == "audio/wav"
    second = service.synthesize({"text": "第二条"})
    with pytest.raises(OperationError) as exc:
        service.read(first["audio_id"])
    assert exc.value.status == 404
    clock[0] += 11
    with pytest.raises(OperationError):
        service.read(second["audio_id"])


@pytest.mark.parametrize("data", [{"text": ""}, {"text": "x" * 2001},
    {"text": "x", "rate": "+99%"}, {"text": "x", "pitch": []},
    {"text": "x", "mouth_intensity": float("nan")}, {"text": "x", "path": "/etc/passwd"}])
def test_speech_rejects_invalid_input(data):
    with pytest.raises(OperationError) as exc:
        SpeechService(WaveTTS()).synthesize(data)
    assert exc.value.status == 422


def test_failed_generation_can_be_retried_and_does_not_leak_error():
    class Broken:
        def synthesize(self, *args):
            raise RuntimeError("secret upstream details")
    service = SpeechService(Broken())
    for _ in range(2):
        with pytest.raises(OperationError) as exc:
            service.synthesize({"text": "你好"})
        assert exc.value.status == 503 and "secret" not in exc.value.message
    service.engine = WaveTTS()
    assert service.synthesize({"text": "恢复"})["frames"]


def test_slow_generation_rejects_duplicate_without_blocking_audio_reads():
    service = SpeechService(WaveTTS())
    first = service.synthesize({"text": "已有语音"})
    entered, release = threading.Event(), threading.Event()
    original = service.engine.synthesize
    def slow(*args):
        entered.set()
        release.wait(3)
        return original(*args)
    service.engine.synthesize = slow
    thread = threading.Thread(target=lambda: service.synthesize({"text": "慢语音"}))
    thread.start()
    assert entered.wait(2)
    try:
        with pytest.raises(OperationError) as exc:
            service.synthesize({"text": "重复"})
        assert exc.value.status == 429
        assert service.read(first["audio_id"])[0].startswith(b"RIFF")
    finally:
        release.set()
        thread.join(3)


def test_audio_http_requires_header_token_and_never_returns_local_path(tmp_path):
    server = create_server(str(tmp_path / "speech.db"), port=0, speech_engine=WaveTTS())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    def request(path, data=None, token=True):
        req = urllib.request.Request(base + path,
            data=None if data is None else json.dumps(data).encode(),
            headers={"Content-Type": "application/json", **({"X-Avatar-Token": server.token} if token else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, r.read(), r.headers
        except urllib.error.HTTPError as r:
            return r.code, r.read(), r.headers
    try:
        code, raw, _ = request("/api/v1/speech", {"text": "你好"})
        metadata = json.loads(raw)["data"]
        assert code == 201 and "path" not in raw.decode()
        path = "/api/v1/speech/audio/" + metadata["audio_id"]
        assert request(path, token=False)[0] == 403
        code, audio, headers = request(path)
        assert code == 200 and audio[:4] == b"RIFF"
        assert headers["Content-Type"] == "audio/wav"
        assert headers["Cache-Control"] == "no-store"
        assert "media-src 'self' blob:" in headers["Content-Security-Policy"]
        assert request("/api/v1/speech/audio/missing")[0] == 404
        assert request("/api/v1/chat", {"text": "你好"})[0] == 200
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

import io
import json
from pathlib import Path
import threading
import urllib.request
import urllib.error
import wave

import pytest

from avatar.brain.operations import OperationError
from avatar.transcription import TranscriptionService
from avatar.web import create_server


def wav_bytes(seconds=0.2, width=2, sr=16000):
    output = io.BytesIO()
    with wave.open(output, "wb") as stream:
        stream.setparams((1, width, sr, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0" * int(sr * seconds) * width)
    return output.getvalue()


class FakeASR:
    def transcribe(self, path):
        self.path = path
        assert Path(path).read_bytes().startswith(b"RIFF")
        return "  识别结果，需要用户确认。  "


def test_transcription_is_opt_in_and_cleans_temporary_audio():
    with pytest.raises(OperationError) as exc:
        TranscriptionService().transcribe(wav_bytes())
    assert exc.value.code == "asr_disabled"
    engine = FakeASR()
    service = TranscriptionService(engine)
    assert service.transcribe(wav_bytes()) == {"transcript": "识别结果，需要用户确认。"}
    assert not Path(engine.path).exists()


@pytest.mark.parametrize("audio", [b"invalid", wav_bytes(width=1), wav_bytes(sr=4000),
    wav_bytes(seconds=61), wav_bytes()[:-10]])
def test_invalid_or_truncated_audio_never_reaches_asr(audio):
    engine = FakeASR()
    with pytest.raises(OperationError) as exc:
        TranscriptionService(engine).transcribe(audio)
    assert exc.value.status == 422 and not hasattr(engine, "path")


def test_empty_transcript_is_clear_and_does_not_poison_next_request():
    engine = FakeASR()
    engine.transcribe = lambda _: ""
    service = TranscriptionService(engine)
    with pytest.raises(OperationError) as exc:
        service.transcribe(wav_bytes())
    assert exc.value.code == "empty_transcript"
    service.engine = FakeASR()
    assert service.transcribe(wav_bytes())["transcript"]


def test_wav_upload_is_authenticated_and_only_transcribes(tmp_path):
    server = create_server(str(tmp_path / "input.db"), port=0, asr_engine=FakeASR())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    def request(path, body=None, token=True, content_type="audio/wav"):
        req = urllib.request.Request(base + path, data=body,
            headers={"Content-Type": content_type, **({"X-Avatar-Token": server.token} if token else {})})
        try:
            with urllib.request.urlopen(req) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as response:
            return response.code, json.loads(response.read())
    try:
        assert request("/api/v1/speech/capabilities")[1]["data"]["asr_enabled"]
        endpoint = "/api/v1/speech/transcribe"
        assert request(endpoint, wav_bytes(), token=False)[0] == 403
        assert request(endpoint, wav_bytes(), content_type="audio/mpeg")[0] == 422
        code, value = request(endpoint, wav_bytes())
        assert code == 200 and "识别结果" in value["data"]["transcript"]
        assert request("/api/v1/memory")[1]["data"] == []
        from avatar.brain.memory import MemoryStore
        memory = MemoryStore(server.db_path)
        try:
            assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages").fetchone()[0] == 0
        finally:
            memory.close()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

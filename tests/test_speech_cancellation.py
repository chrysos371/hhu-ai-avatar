import asyncio
import threading
import time

import httpx
import pytest

from avatar.brain.operations import OperationError
from avatar.lab.transport_fixture import controlled_provider
from avatar.mouth.tts import EdgeTTSEngine
from avatar.speech import SpeechService


def test_cancel_speech_closes_pending_network_and_releases_slot(monkeypatch):
    with controlled_provider() as (server, url):
        class Communication:
            def __init__(self, *args, **kwargs):
                pass
            async def save(self, path):
                async with httpx.AsyncClient() as client:
                    await client.post(url + '/chat/completions', json={'messages': [{'content': 'delay-headers'}]})
        monkeypatch.setattr('avatar.mouth.tts.edge_tts.Communicate', Communication)
        service = SpeechService(EdgeTTSEngine())
        request_id = 'cancel_speech_request_123456'
        outcome = []
        def worker():
            try:
                service.synthesize({'text': '测试', 'request_id': request_id})
            except OperationError as exc:
                outcome.append(exc.code)
        thread = threading.Thread(target=worker)
        thread.start()
        assert server.started.wait(3)
        start = time.perf_counter()
        service.cancel(request_id)
        thread.join(2)
        assert outcome == ['speech_cancelled']
        assert time.perf_counter() - start < 1
        assert server.disconnected.wait(2)
        assert not service._audio and not service._active
        assert service._busy.acquire(blocking=False)
        service._busy.release()


def test_cancel_before_synthesis_does_not_start_engine():
    class Never:
        def synthesize(self, *args):
            pytest.fail('cancelled request reached TTS')
    service = SpeechService(Never())
    request_id = 'cancel_before_start_123456'
    service.cancel(request_id)
    with pytest.raises(OperationError) as exc:
        service.synthesize({'text': '测试', 'request_id': request_id})
    assert exc.value.code == 'speech_cancelled'

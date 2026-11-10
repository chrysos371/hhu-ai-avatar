import json
import threading
import urllib.error
import urllib.request
import wave

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.turns import TurnCoordinator
from avatar.web import create_server


@pytest.mark.parametrize('external', [False, True])
def test_forget_erases_http_job_audio_and_request_fingerprints(tmp_path, monkeypatch, external):
    from avatar.config import config
    monkeypatch.setattr(config.llm, 'api_key', '')
    class Voice:
        def synthesize(self, text, path, rate, pitch):
            with wave.open(path, 'wb') as stream:
                stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                stream.writeframes(b'\0' * 6400)
            return path
    server = create_server(str(tmp_path/'erase.db'), port=0, speech_engine=Voice())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def request(path, data=None):
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
            data=None if data is None else json.dumps(data).encode(),
            headers={'X-Avatar-Token':server.token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as response:
            return response.code, response.read()
    try:
        data = {'request_id':'privacy_request_1234567890','text':'我叫隐私测试甲'}
        assert request('/api/v1/turns',data)[0] == 202
        assert request('/api/v1/turns/'+data['request_id']+'/events')[0] == 200
        code, raw = request('/api/v1/speech', {'text':'隐私测试甲'})
        assert code == 201
        audio = json.loads(raw)['data']['audio_id']
        _, raw = request('/api/v1/memory')
        fid = next(r['id'] for r in json.loads(raw)['data'] if '隐私测试甲' in r['content'])
        if external:
            memory = MemoryStore(server.db_path)
            memory.forget(fid)
            memory.close()
        else:
            assert request('/api/forget',{'id':fid})[0] == 200
        # Audio may be read before any job endpoint after an external CLI deletion.
        assert request('/api/v1/speech/audio/'+audio)[0] == 404
        assert request('/api/v1/turns/'+data['request_id'])[0] == 404
        assert request('/api/v1/turns/'+data['request_id']+'/events')[0] == 404
        assert request('/api/v1/turns',data)[0] == 410
        memory = MemoryStore(server.db_path)
        try:
            assert memory._conn.execute('SELECT fingerprint FROM runtime_turn_ledger').fetchone()[0] == ''
        finally:
            memory.close()
    finally:
        server.shutdown();thread.join();server.server_close()


def test_external_erasure_prevents_late_worker_from_repopulating_job(tmp_path):
    path = str(tmp_path/'external.db')
    memory = MemoryStore(path)
    fid = memory.remember_user('名字','被删除的数据')
    entered, release = threading.Event(), threading.Event()
    def late(job):
        entered.set()
        release.wait(3)
        return {'reply':'被删除的数据'}
    coordinator = TurnCoordinator(path,late)
    job = coordinator.submit({'request_id':'external_request_123456789','text':'被删除的数据'})
    assert entered.wait(2)
    memory.forget(fid)
    coordinator.refresh_privacy()
    release.set()
    coordinator._thread.join(3)
    assert job.redacted and job.result is None and job.text == '' and job.events == []
    with pytest.raises(OperationError):
        coordinator.get(job.id)
    coordinator.close();memory.close()

import json
import threading
import urllib.error
import urllib.request

import pytest

from avatar.brain.operations import OperationError
from avatar.turns import TurnCoordinator
from avatar.web import create_server


def test_repeated_job_is_executed_once_and_remains_deduplicated_after_restart(tmp_path):
    path = str(tmp_path / 'jobs.db')
    entered, release = threading.Event(), threading.Event()
    calls = []
    def runner(job):
        calls.append(job.text)
        entered.set()
        release.wait(3)
        return {'reply': '完成'}
    coordinator = TurnCoordinator(path, runner)
    data = {'request_id': 'unique_request_1234567890', 'text': '用户消息'}
    job = coordinator.submit(data)
    assert entered.wait(2)
    for _ in range(20):
        assert coordinator.submit(data) is job
    with pytest.raises(OperationError) as exc:
        coordinator.submit(data | {'text': '不同消息'})
    assert exc.value.status == 409
    release.set()
    with job.changed:
        job.changed.wait_for(lambda: job.status == 'completed', timeout=3)
    assert job.status == 'completed' and calls == ['用户消息']
    coordinator.close()
    restarted = TurnCoordinator(path, lambda job: pytest.fail('must not replay'))
    with pytest.raises(OperationError) as exc:
        restarted.submit(data)
    assert exc.value.status == 410
    restarted.close()


def test_cancellation_releases_capacity_before_terminal_event(tmp_path):
    entered = threading.Event()
    def runner(job):
        entered.set()
        job.token._event.wait(3)
        job.token.checkpoint()
    coordinator = TurnCoordinator(str(tmp_path / 'cancel.db'), runner)
    job = coordinator.submit({'request_id': 'cancel_request_123456789', 'text': '取消'})
    assert entered.wait(2)
    coordinator.cancel(job.id)
    with job.changed:
        job.changed.wait_for(lambda: job.status == 'cancelled', timeout=3)
    assert job.status == 'cancelled'
    # No transient busy error after the client sees a terminal event.
    next_job = coordinator.submit({'request_id': 'another_request_123456789', 'text': '下一轮'})
    coordinator.cancel(next_job.id)
    coordinator.close()


def test_turn_http_stream_and_dedup_do_not_duplicate_memory(tmp_path, monkeypatch):
    from avatar.config import config
    from avatar.brain.memory import MemoryStore
    monkeypatch.setattr(config.llm, 'api_key', '')
    monkeypatch.setattr(config.embedding, 'model', '')
    server = create_server(str(tmp_path / 'http.db'), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def request(path, data=None, token=True):
        req = urllib.request.Request(base + path, data=None if data is None else json.dumps(data).encode(),
            headers={'Content-Type': 'application/json', **({'X-Avatar-Token': server.token} if token else {})})
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, response.read(), response.headers
        except urllib.error.HTTPError as response:
            return response.code, response.read(), response.headers
    try:
        data = {'request_id': 'http_request_123456789012', 'text': '我叫小林'}
        assert request('/api/v1/turns', data, token=False)[0] == 403
        code, body, _ = request('/api/v1/turns', data)
        assert code == 202
        job_id = json.loads(body)['data']['job_id']
        path = f'/api/v1/turns/{job_id}/events'
        assert request(path, token=False)[0] == 403
        code, stream, headers = request(path)
        assert code == 200 and headers['Content-Type'].startswith('text/event-stream')
        assert b'event: result\n' in stream
        result = [json.loads(line[6:]) for line in stream.decode().splitlines() if line.startswith('data: ')][-1]
        assert result['reply'] and result['trace']['recalled_memories']
        assert request('/api/v1/turns', data)[0] == 202
        memory = MemoryStore(server.db_path)
        try:
            assert memory._conn.execute('SELECT COUNT(*) FROM memory_messages').fetchone()[0] == 2
        finally:
            memory.close()
        assert request('/api/v1/turns', data | {'use_web': 'yes'})[0] == 422
    finally:
        server.shutdown()
        thread.join()
        server.server_close()

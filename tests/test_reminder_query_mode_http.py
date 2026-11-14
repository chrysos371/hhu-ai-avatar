"""Actual token-authenticated HTTP/SSE and durable mode-aware deduplication."""
from contextlib import closing
import hashlib
import json
import sqlite3
import urllib.request

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.turns import TurnCoordinator
from test_reminder_query_flow import seed, projection
from test_web_api_v1 import api_v1


@pytest.mark.parametrize('text,route', [
    ('提醒编号1状态？', 'read_state'),
    ('提醒编号1能通过短信送给我吗？', 'read_policy'),
    ('这条提醒取消了吗？', 'clarify_reference'),
    ('提醒编号1状态和程序运行条件是什么？', 'clarify_intent'),
    ('请取消提醒编号1', 'no_read'),
])
def test_actual_sync_and_sse_deliver_typed_mode_and_persist_original_metadata(api_v1, text, route):
    request, server = api_v1
    with closing(MemoryStore(server.db_path)) as memory:
        seed(memory); before = projection(memory)
    code, body = request('/api/v1/chat', {'text': text, 'mode': 'reminder_query'})
    assert code == 200 and body['data']['reminder_query']['route'] == route
    ident = 'query_mode_http_request_123456789'
    data = {'request_id': ident, 'text': text, 'mode': 'reminder_query'}
    assert request('/api/v1/turns', data)[0] == 202
    req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/turns/{ident}/events',
                                 headers={'X-Avatar-Token': server.token})
    with urllib.request.urlopen(req, timeout=10) as response:
        raw = response.read().decode()
    results = [json.loads(line[6:]) for block in raw.split('\n\n') if 'event: result\n' in block
        for line in block.splitlines() if line.startswith('data: ')]
    assert len(results) == 1 and results[0]['reminder_query']['route'] == route
    assert results[0]['reminder_query']['mode'] == 'reminder_query'
    assert not results[0]['due_reminders'] and not results[0]['tool_calls']
    assert request('/api/v1/turns', data)[0] == 202
    assert request('/api/v1/turns', data | {'mode': 'chat'})[0] == 409
    with closing(MemoryStore(server.db_path)) as memory:
        assert projection(memory) == before
        assert memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='user'").fetchone()[0] == 2
    history = request('/api/v1/conversation')[1]['data']['items']
    assert [r['result']['reminder_query']['route'] for r in history if r['role'] == 'assistant'] == [route, route]


@pytest.mark.parametrize('bad', [
    {'mode': None}, {'mode': True}, {'mode': []}, {'mode': 'unknown'},
    {'mode': 'reminder_query', 'use_web': True},
    {'mode': 'reminder_query', 'text': '字'*2001},
])
def test_invalid_mode_http_rejected_before_source_or_job_creation(api_v1, bad):
    request, server = api_v1
    data = {'text': '提醒编号1状态？'} | bad
    assert request('/api/v1/chat', data)[0] == 422
    assert request('/api/v1/turns', data | {'request_id': 'invalid_query_mode_request_12345'})[0] == 422
    with closing(MemoryStore(server.db_path)) as memory:
        assert memory._conn.execute('SELECT count(*) FROM memory_messages').fetchone()[0] == 0
    assert not server.turns._jobs


@pytest.mark.parametrize('mode', ['chat', 'reminder_query'])
def test_mode_fingerprint_survives_restart_and_legacy_chat_bytes_remain_unchanged(tmp_path, mode):
    path = str(tmp_path/'mode-jobs.db')
    coordinator = TurnCoordinator(path, lambda job: {'reply': job.mode})
    data = {'request_id': 'durable_query_mode_request_12345', 'text': '提醒编号1状态？', 'mode': mode}
    try:
        job = coordinator.submit(data)
        with job.changed:
            assert job.changed.wait_for(lambda: job.status == 'completed', timeout=3)
        parts = [data['text'], False] + ([{'mode': mode}] if mode != 'chat' else [])
        with sqlite3.connect(path) as conn:
            assert conn.execute('SELECT fingerprint FROM runtime_turn_ledger').fetchone()[0] == hashlib.sha256(
                json.dumps(parts, ensure_ascii=False).encode()).hexdigest()
    finally:
        coordinator.close()
    restarted = TurnCoordinator(path, lambda job: pytest.fail('must not replay'))
    try:
        with pytest.raises(OperationError) as error: restarted.submit(data)
        assert error.value.status == 410
        with pytest.raises(OperationError) as error:
            restarted.submit(data | {'mode': 'reminder_query' if mode == 'chat' else 'chat'})
        assert error.value.status == 409
    finally:
        restarted.close()

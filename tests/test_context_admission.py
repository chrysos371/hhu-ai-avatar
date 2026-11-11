from contextlib import closing
import hashlib
import json
import sqlite3
import threading

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.brain.speaker_context import SpeakerContextStore
from avatar.turns import TurnCoordinator
from test_web_api_v1 import api_v1


def snapshot(request):
    data = request('/api/v1/conversation/speaker')[1]['data']
    return {key: data[key] for key in ('instance_id', 'revision', 'context_cursor')}


def wait(server, ident):
    job = server.turns.get(ident)
    with job.changed:
        assert job.changed.wait_for(lambda: job.status in ('completed', 'failed', 'cancelled'), timeout=3)
    return job


def submit(request, server, expected, text='我叫许照。', ident='admission_http_request_123456'):
    status, _ = request('/api/v1/turns', {'request_id': ident, 'text': text, 'expected_context': expected})
    assert status == 202
    return wait(server, ident)


@pytest.mark.parametrize('role', [False, True])
def test_matching_context_commits_once_and_duplicate_does_not_recheck_own_cursor(api_v1, role):
    request, server = api_v1
    if role: request('/api/v1/chat', {'text': '我来扮演一个虚构角色。'})
    expected = snapshot(request)
    job = submit(request, server, expected)
    assert job.status == 'completed'
    assert submit(request, server, expected) is job
    with closing(MemoryStore(server.db_path)) as memory:
        assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='user' AND content='我叫许照。'").fetchone()[0] == 1
        assert memory.get_user_profile().get('名字') == (None if role else '许照')
    changed = expected | {'context_cursor': expected['context_cursor']+1}
    assert request('/api/v1/turns', {'request_id': job.id, 'text': '我叫许照。', 'expected_context': changed})[0] == 409


@pytest.mark.parametrize('change', ['user', 'revision', 'namespace'])
def test_stale_context_never_commits_source_shortterm_fact_or_reminder(api_v1, monkeypatch, change):
    request, server = api_v1
    expected = snapshot(request)
    if change == 'namespace': expected['instance_id'] = 'old-instance'
    else:
        with closing(MemoryStore(server.db_path)) as memory:
            if change == 'user': memory.add_message('user', '其他写入方', 'external')
            else: memory.forget(memory.remember('版本变化'))
    def forbidden(*args, **kwargs): pytest.fail('rejected admission must not analyze')
    from avatar.main import Avatar
    monkeypatch.setattr(Avatar, '_analyze', forbidden)
    text = '提醒我明天下午3点去码头'
    job = submit(request, server, expected, text=text)
    assert job.status == 'failed' and job.events[-1]['data']['code'] == 'speaker_context_changed'
    assert not any(row['content'] == text for row in server.short_term)
    with closing(MemoryStore(server.db_path)) as memory:
        assert not memory._conn.execute('SELECT 1 FROM memory_messages WHERE content=?', (text,)).fetchone()
        assert not memory._conn.execute('SELECT 1 FROM memory_reminders').fetchone()
        assert not memory.get_user_profile()


def test_assistant_only_write_does_not_change_admission(api_v1):
    request, server = api_v1
    expected = snapshot(request)
    with closing(MemoryStore(server.db_path)) as memory: memory.add_message('assistant', '其他回复', 'other')
    assert submit(request, server, expected).status == 'completed'


def test_cancel_before_admission_has_no_source(api_v1):
    request, server = api_v1
    expected = snapshot(request); ident = 'admission_pre_cancel_123456'
    with server.state_lock:
        assert request('/api/v1/turns', {'request_id': ident, 'text': '我叫许照。', 'expected_context': expected})[0] == 202
        assert request('/api/v1/turns/'+ident+'/cancel', {})[0] == 200
    assert wait(server, ident).status == 'cancelled'
    with closing(MemoryStore(server.db_path)) as memory:
        assert not memory._conn.execute('SELECT 1 FROM memory_messages').fetchone()
    assert not server.short_term


@pytest.mark.parametrize('context', [None, {}, {'instance_id': 'a', 'revision': True, 'context_cursor': 0},
    {'instance_id': 'a', 'revision': 0, 'context_cursor': -1},
    {'instance_id': 'a', 'revision': 0, 'context_cursor': 2**53},
    {'instance_id': '../bad', 'revision': 0, 'context_cursor': 0},
    {'instance_id': 'a', 'revision': 0, 'context_cursor': 0, 'scope': 'current_user'}])
def test_malformed_context_rejected_without_creating_job(context):
    with pytest.raises(OperationError) as error:
        TurnCoordinator.validate({'request_id': 'validation_context_12345', 'text': 'text', 'expected_context': context})
    assert error.value.status == 422


def test_context_check_requires_transaction_and_rejected_shortterm_rolls_back():
    with closing(MemoryStore(':memory:')) as memory:
        store = SpeakerContextStore(memory)
        expected = {'instance_id': 'a', 'revision': 0, 'context_cursor': 0}
        with pytest.raises(RuntimeError): store.require_context(expected, 'a')
        memory.add_short_term('assistant', 'existing')
        with pytest.raises(OperationError):
            with memory.transaction():
                store.require_context(expected | {'context_cursor': 1}, 'a')
                memory.add_short_term('user', 'must not appear')
        assert memory.get_short_term() == [{'role': 'assistant', 'content': 'existing'}]


def test_two_connections_cannot_both_admit_same_cursor(tmp_path):
    path = str(tmp_path/'atomic.db')
    barrier = threading.Barrier(2); results = []; failures = []
    def writer(name):
        try:
            with closing(MemoryStore(path)) as memory:
                barrier.wait(timeout=3)
                try:
                    with memory.transaction():
                        SpeakerContextStore(memory).require_context(
                            {'instance_id': 'same-instance', 'revision': 0, 'context_cursor': 0}, 'same-instance')
                        memory.add_message('user', name, 's')
                    results.append('admitted')
                except OperationError as error: results.append(error.code)
        except Exception as error: failures.append(repr(error))
    # Initialize schema before competing writers; barriers synchronize admission only.
    with closing(MemoryStore(path)): pass
    threads = [threading.Thread(target=writer, args=(name,)) for name in ('first', 'second')]
    for thread in threads: thread.start()
    for thread in threads: thread.join(5)
    assert all(not thread.is_alive() for thread in threads) and not failures
    assert sorted(results) == ['admitted', 'speaker_context_changed']
    with closing(MemoryStore(path)) as memory:
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_messages').fetchone()[0] == 1


def test_bound_durable_fingerprint_is_order_independent_and_never_replays_after_restart(tmp_path):
    path = str(tmp_path/'bound-ledger.db')
    expected = {'instance_id': 'a', 'revision': 0, 'context_cursor': 0}
    data = {'request_id': 'durable_bound_admission_12345', 'text': 'hello', 'expected_context': expected}
    original = TurnCoordinator(path, lambda job: {'reply': 'done'})
    job = original.submit(data)
    with job.changed: assert job.changed.wait_for(lambda: job.status == 'completed', timeout=3)
    # Caller mutation cannot change the retained admission or dedup identity.
    expected['revision'] = 99
    assert job.expected_context['revision'] == 0
    original.close()
    restarted = TurnCoordinator(path, lambda job: pytest.fail('must not replay'))
    try:
        reordered = {'context_cursor': 0, 'revision': 0, 'instance_id': 'a'}
        with pytest.raises(OperationError) as error: restarted.submit(data | {'expected_context': reordered})
        assert error.value.code == 'turn_expired'
        with pytest.raises(OperationError) as error: restarted.submit(data)
        assert error.value.code == 'request_id_conflict'
    finally: restarted.close()


def test_preexisting_legacy_fingerprint_remains_compatible(tmp_path):
    path = str(tmp_path/'legacy-ledger.db')
    ident = 'preexisting_legacy_admission_12345'
    fingerprint = hashlib.sha256(json.dumps(['你好', False], ensure_ascii=False).encode()).hexdigest()
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE runtime_turn_ledger (request_id TEXT PRIMARY KEY, fingerprint TEXT, status TEXT, created_at REAL)')
        conn.execute('INSERT INTO runtime_turn_ledger VALUES (?,?,?,?)', (ident, fingerprint, 'completed', 0))
    coordinator = TurnCoordinator(path, lambda job: pytest.fail('legacy request must not replay'))
    try:
        with pytest.raises(OperationError) as error: coordinator.submit({'request_id': ident, 'text': '你好'})
        assert error.value.code == 'turn_expired'
    finally: coordinator.close()

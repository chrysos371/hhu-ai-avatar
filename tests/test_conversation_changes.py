import http.client
from contextlib import closing
import json
import sqlite3
import threading
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.conversation_changes import ConversationChanges, WatchDisconnected
from test_web_api_v1 import api_v1


def active(watch, count):
    for _ in range(400):
        if watch.active_count == count:
            return
        time.sleep(.005)
    pytest.fail(f'watcher count did not reach {count}')


def initialized(tmp_path, **options):
    path = str(tmp_path/'watch.db')
    memory = MemoryStore(path); memory.close()
    return path, ConversationChanges(path, 'instance', **options)


def waiter(watch, *, disconnected=lambda: False):
    result = []
    def run():
        try:
            result.append(watch.wait('instance', 0, disconnected=disconnected))
        except Exception as error:
            result.append(error)
    thread = threading.Thread(target=run); thread.start()
    return thread, result


def test_metadata_never_contains_fact_text_and_initial_unknown_namespace_is_immediate(tmp_path):
    path, watch = initialized(tmp_path)
    memory = MemoryStore(path); memory.remember_user('名字', 'private-watch-marker'); memory.close()
    try:
        result = watch.wait('old-instance', 0)
        assert result == {'instance_id': 'instance', 'revision': 0}
        assert 'private-watch-marker' not in json.dumps(result)
        assert watch.active_count == 0 and watch._thread is None
    finally:
        watch.close()


def test_monotonic_publication_rejects_late_lower_checks(tmp_path):
    _, watch = initialized(tmp_path)
    try:
        watch.publish(3); watch.publish(1)
        assert watch.wait('old', 0)['revision'] == 3
        for value in [-1, True, .5]:
            with pytest.raises(ValueError): watch.publish(value)
    finally:
        watch.close()


def test_external_connection_change_wakes_one_shared_monitor(tmp_path):
    path, watch = initialized(tmp_path, poll_interval=.01)
    threads, results = [], []
    try:
        for _ in range(3):
            thread, result = waiter(watch); threads.append(thread); results.append(result)
        active(watch, 3)
        with closing(MemoryStore(path)) as memory:
            fact = memory.remember_user('名字', 'external-secret')
            memory.forget(fact)
        for thread in threads: thread.join(2); assert not thread.is_alive()
        assert results == [[{'instance_id': 'instance', 'revision': 1}]] * 3
        assert watch.active_count == 0 and watch._thread.is_alive()
    finally:
        watch.close()
        for thread in threads: thread.join(2)


def test_heartbeat_releases_slot_and_idle_monitor_stops_querying(tmp_path):
    _, watch = initialized(tmp_path, heartbeat=.02, poll_interval=.01)
    try:
        assert watch.wait('instance', 0) == {'instance_id': 'instance', 'revision': 0}
        assert watch.active_count == 0
        time.sleep(.03); checks = watch.monitor_checks; time.sleep(.03)
        assert checks == watch.monitor_checks
    finally:
        watch.close()
    assert not watch._thread.is_alive()


def test_capacity_preserves_immediate_metadata_and_close_releases_waiters(tmp_path):
    _, watch = initialized(tmp_path, limit=2, poll_interval=.01)
    threads, results = [], []
    try:
        for _ in range(2):
            thread, result = waiter(watch); threads.append(thread); results.append(result)
        active(watch, 2)
        with pytest.raises(OperationError) as error: watch.wait('instance', 0)
        assert error.value.status == 429
        assert watch.wait('different', 0)['revision'] == 0
        watch.close()
        for thread in threads: thread.join(2); assert not thread.is_alive()
        assert all(isinstance(result[0], OperationError) and result[0].status == 503 for result in results)
        assert watch.active_count == 0
    finally:
        watch.close()


def test_disconnected_peer_releases_only_its_own_watch_slot(tmp_path):
    _, watch = initialized(tmp_path, poll_interval=.01)
    gone = threading.Event(); thread, result = waiter(watch, disconnected=gone.is_set)
    try:
        active(watch, 1); gone.set(); thread.join(2)
        assert isinstance(result[0], WatchDisconnected) and watch.active_count == 0
    finally:
        watch.close(); thread.join(2)


def test_read_failure_is_not_an_old_success_and_recovers(tmp_path, monkeypatch):
    _, watch = initialized(tmp_path)
    original = watch._read_revision
    try:
        def failed(): raise sqlite3.DatabaseError('private path must not be public')
        monkeypatch.setattr(watch, '_read_revision', failed)
        with pytest.raises(OperationError) as error: watch.wait('instance', 0)
        assert error.value.status == 503 and 'private path' not in str(error.value)
        monkeypatch.setattr(watch, '_read_revision', original)
        assert watch.wait('different', 0)['revision'] == 0
    finally:
        watch.close()


def test_http_heartbeat_and_peer_close_reclaim_capacity(api_v1):
    request, server = api_v1
    request('/api/v1/system')
    watch = server.conversation_changes; watch.heartbeat = .02
    path = '/api/v1/conversation/changes?instance_id=' + server.session_id + '&revision=0'
    assert request(path)[1]['data'] == {'instance_id': server.session_id, 'revision': 0}
    watch.heartbeat = 10
    conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
    conn.request('GET', path, headers={'X-Avatar-Token': server.token})
    active(watch, 1); conn.close(); active(watch, 0)
    assert request('/api/v1/system')[0] == 200


def test_api_commit_notifies_held_metadata_without_waiting_for_monitor(api_v1):
    request, server = api_v1
    request('/api/v1/system'); watch = server.conversation_changes
    watch.poll_interval = 30  # API acknowledgement must do its own committed check.
    memory = MemoryStore(server.db_path); fact = memory.remember_user('名字', 'erase-api'); memory.close()
    results = []
    def read():
        results.append(request('/api/v1/conversation/changes?instance_id='+server.session_id+'&revision=0'))
    thread = threading.Thread(target=read); thread.start(); active(watch, 1)
    draft = request('/api/v1/memory/batch-draft', {'actions': [{'action': 'forget', 'id': fact}]})[1]['data']
    assert request('/api/v1/operations/'+str(draft['draft_id'])+'/confirm', {'confirmation_token': draft['confirmation_token']})[0] == 200
    thread.join(2); assert not thread.is_alive()
    assert results[0][1]['data'] == {'instance_id': server.session_id, 'revision': 1}


def test_metadata_disconnect_does_not_cancel_an_unrelated_running_turn(api_v1):
    request, server = api_v1
    request('/api/v1/system'); release, entered = threading.Event(), threading.Event()
    def runner(job): entered.set(); release.wait(); return {'reply': 'done'}
    server.turns.runner = runner
    job = server.turns.submit({'request_id': 'metadata_disconnect_job_12345', 'text': 'normal input'})
    conn = http.client.HTTPConnection('127.0.0.1', server.server_port)
    try:
        assert entered.wait(2) and job.status == 'running'
        conn.request('GET', '/api/v1/conversation/changes?instance_id='+server.session_id+'&revision=0', headers={'X-Avatar-Token': server.token})
        active(server.conversation_changes, 1); conn.close(); active(server.conversation_changes, 0)
        assert job.status == 'running'
        job.token.checkpoint()
    finally:
        release.set(); conn.close()

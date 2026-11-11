from contextlib import closing
import json
import sqlite3
import threading
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.conversation_changes import ConversationChanges
from test_conversation_changes import active
from test_web_api_v1 import api_v1


def watch_at(tmp_path, **kwargs):
    path = str(tmp_path/'context.db'); MemoryStore(path).close()
    return path, ConversationChanges(path, 'instance', **kwargs)


def wait_thread(watch, cursor=None):
    result = []
    def run():
        try: result.append(watch.wait('instance', 0, context_cursor=cursor))
        except Exception as error: result.append(error)
    thread = threading.Thread(target=run); thread.start()
    return thread, result


def test_ordinary_user_wakes_only_opted_in_wait_without_privacy_change(tmp_path):
    path, watch = watch_at(tmp_path, poll_interval=.01)
    old, old_result = wait_thread(watch)
    new, new_result = wait_thread(watch, 0)
    try:
        active(watch, 2); monitor = watch._thread
        with closing(MemoryStore(path)) as memory:
            ident = memory.add_message('user', 'private-context-marker', 'foreign')
        new.join(2); assert not new.is_alive()
        assert new_result == [{'instance_id': 'instance', 'revision': 0, 'context_cursor': ident}]
        assert old.is_alive() and old_result == []
        assert watch._thread is monitor and watch.active_count == 1
        assert 'private-context-marker' not in json.dumps(new_result)
    finally:
        watch.close(); old.join(2); new.join(2)


def test_extended_and_legacy_waits_share_capacity_and_shutdown(tmp_path):
    _, watch = watch_at(tmp_path, limit=2, poll_interval=.01)
    threads, results = [], []
    try:
        for cursor in [None, 0]:
            thread, result = wait_thread(watch, cursor); threads.append(thread); results.append(result)
        active(watch, 2)
        with pytest.raises(OperationError) as error: watch.wait('instance', 0, context_cursor=0)
        assert error.value.status == 429
        assert watch.wait('other', 0, context_cursor=0) == {'instance_id': 'instance', 'revision': 0, 'context_cursor': 0}
        watch.close()
        for thread in threads: thread.join(2)
        assert all(isinstance(r[0], OperationError) and r[0].status == 503 for r in results)
    finally:
        watch.close()
        for thread in threads: thread.join(2)


def test_context_heartbeat_goes_idle_and_source_cursor_never_rolls_back(tmp_path):
    _, watch = watch_at(tmp_path, heartbeat=.02, poll_interval=.01)
    try:
        assert watch.wait('instance', 0, context_cursor=0)['context_cursor'] == 0
        time.sleep(.03); checks = watch.monitor_checks; time.sleep(.03)
        assert watch.monitor_checks == checks
        watch.publish(0, context_cursor=3); watch.publish(0, context_cursor=1)
        assert watch.wait('other', 0, context_cursor=0)['context_cursor'] == 3
        assert set(watch.wait('other', 0)) == {'instance_id', 'revision'}
    finally: watch.close()


def test_context_read_error_never_returns_cached_metadata_and_fresh_read_recovers(tmp_path, monkeypatch):
    _, watch = watch_at(tmp_path)
    try:
        assert watch.wait('other', 0, context_cursor=0)['context_cursor'] == 0
        original = watch._read_state
        def failed(): raise sqlite3.DatabaseError('private filesystem marker')
        monkeypatch.setattr(watch, '_read_state', failed)
        with pytest.raises(OperationError) as error: watch.wait('other', 0, context_cursor=0)
        assert error.value.status == 503 and 'private filesystem' not in str(error.value)
        monkeypatch.setattr(watch, '_read_state', original)
        assert watch.wait('other', 0, context_cursor=0)['context_cursor'] == 0
    finally: watch.close()


@pytest.mark.parametrize('cursor', [-1, True, .5])
def test_invalid_internal_cursor_cannot_acquire_wait_or_enable_monitor(tmp_path, cursor):
    _, watch = watch_at(tmp_path)
    try:
        with pytest.raises(ValueError): watch.wait('other', 0, context_cursor=cursor)
        assert watch.active_count == 0 and watch._thread is None
    finally: watch.close()


def test_http_opt_in_metadata_and_legacy_contract_with_actual_user_source(api_v1):
    request, server = api_v1
    result = request('/api/v1/chat', {'text': '我来扮演一个虚构角色。'})[1]['data']
    route = '/api/v1/conversation/changes?instance_id=other&revision=0'
    extended = request(route+'&context_cursor=0')[1]['data']
    assert extended == {'instance_id': server.session_id, 'revision': 0,
        'context_cursor': result['conversation']['user_message_id']}
    assert request(route)[1]['data'] == {'instance_id': server.session_id, 'revision': 0}
    assert request(route+'&context_cursor=0', token=False)[0] == 403


@pytest.mark.parametrize('raw', ['', '-1', '1.5', 'true', '9223372036854775808', '0&context_cursor=1'])
def test_http_rejects_invalid_or_duplicate_context_cursor(api_v1, raw):
    request, _ = api_v1
    status, body = request('/api/v1/conversation/changes?instance_id=other&revision=0&context_cursor='+raw)
    assert status == 422 and body['error']['code'] == 'invalid_watch_cursor'

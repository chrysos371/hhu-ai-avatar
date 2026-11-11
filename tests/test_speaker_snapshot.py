from contextlib import closing
import json
import threading

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.speaker_context import SpeakerContextStore
from avatar.brain.operations import OperationError
from avatar.main import Avatar
from test_web_api_v1 import api_v1

FIELDS = {'instance_id', 'revision', 'context_cursor', 'scope', 'profile_writes_for_new_turn',
    'real_actions_for_new_turn', 'general_coreference_verified', 'version'}


def test_fresh_read_is_metadata_only_and_does_not_create_control_or_write():
    with closing(MemoryStore(':memory:')) as memory:
        before = memory._conn.total_changes
        data = SpeakerContextStore(memory).read('instance')
        assert set(data) == FIELDS
        assert data['scope'] == 'current_user' and data['context_cursor'] == 0
        assert data['profile_writes_for_new_turn'] and data['real_actions_for_new_turn']
        assert data['general_coreference_verified'] is False
        assert memory._conn.total_changes == before
        assert not memory._conn.execute('SELECT 1 FROM memory_web_speaker_state').fetchone()


@pytest.mark.parametrize('invalid', [-1, 'corrupt', None])
def test_invalid_version_never_returns_permission_metadata(invalid):
    with closing(MemoryStore(':memory:')) as memory:
        if invalid is None: memory._conn.execute('DELETE FROM memory_context_revision')
        else: memory._conn.execute('UPDATE memory_context_revision SET revision=?', (invalid,))
        memory._conn.commit()
        with pytest.raises(OperationError) as error: SpeakerContextStore(memory).read('instance')
        assert error.value.status == 503


@pytest.mark.parametrize('declaration,expected', [
    ('我来扮演一个虚构角色。', 'fictional_character'),
    ('我想要扮演医生。', 'unverified'),
    ('回到现实。', 'current_user'),
])
def test_http_scope_is_authoritative_but_contains_no_user_text(api_v1, declaration, expected):
    request, server = api_v1
    result = request('/api/v1/chat', {'text': declaration})[1]['data']
    status, body = request('/api/v1/conversation/speaker')
    assert status == 200
    data = body['data']; assert set(data) == FIELDS
    assert data['scope'] == expected and data['instance_id'] == server.session_id
    assert data['context_cursor'] == result['conversation']['user_message_id']
    assert data['profile_writes_for_new_turn'] == data['real_actions_for_new_turn'] == (expected == 'current_user')
    assert declaration not in json.dumps(data, ensure_ascii=False)
    assert request('/api/v1/conversation/speaker?source=private')[0] == 422
    assert request('/api/v1/conversation/speaker', token=False)[0] == 403


def test_untracked_external_user_and_privacy_are_not_hidden_by_server_memory(api_v1):
    request, server = api_v1
    request('/api/v1/chat', {'text': '今天聊点日常。'})
    assert server.speaker_scope.scope == 'current_user'
    with closing(MemoryStore(server.db_path)) as writer:
        writer.add_message('user', '接下来我扮演剧中的旅行者。', 'other')
        before = dict(writer._conn.execute('SELECT * FROM memory_web_speaker_state').fetchone())
    data = request('/api/v1/conversation/speaker')[1]['data']
    assert data['scope'] == 'unverified' and not data['real_actions_for_new_turn']
    with closing(MemoryStore(server.db_path)) as writer:
        assert dict(writer._conn.execute('SELECT * FROM memory_web_speaker_state').fetchone()) == before
    result = request('/api/v1/chat', {'text': '我来扮演一个虚构角色。'})[1]['data']
    with closing(MemoryStore(server.db_path)) as writer:
        fact = writer.remember('受控来源', source_message_id=result['conversation']['user_message_id'])
        writer.forget(fact)
    data = request('/api/v1/conversation/speaker')[1]['data']
    assert data['scope'] == 'unverified' and data['revision'] == 1


def test_cancel_after_source_commit_keeps_actual_scope_without_assistant(api_v1, monkeypatch):
    request, server = api_v1
    entered, release = threading.Event(), threading.Event()
    original = Avatar._analyze
    def paused(self, text):
        entered.set(); release.wait(); return original(self, text)
    monkeypatch.setattr(Avatar, '_analyze', paused)
    ident = 'context_committed_cancel_12345'
    try:
        request('/api/v1/turns', {'request_id': ident, 'text': '我来扮演一个虚构角色。'})
        assert entered.wait(2)
        # The server copies in-memory scope only in run_chat's finally block.
        assert server.speaker_scope.scope == 'current_user'
        assert request('/api/v1/conversation/speaker')[1]['data']['scope'] == 'fictional_character'
        assert request('/api/v1/turns/'+ident+'/cancel', {})[0] == 200
    finally: release.set()
    job = server.turns.get(ident)
    with job.changed:
        assert job.changed.wait_for(lambda: job.status in ('cancelled', 'completed', 'failed'), timeout=2)
    assert job.status == 'cancelled'
    assert request('/api/v1/conversation/speaker')[1]['data']['scope'] == 'fictional_character'
    with closing(MemoryStore(server.db_path)) as memory:
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()


def test_read_snapshot_cannot_mix_new_privacy_state_with_old_revision(tmp_path):
    path = str(tmp_path/'atomic.db')
    with closing(MemoryStore(path)) as memory:
        store = SpeakerContextStore(memory)
        text = '我来扮演一个虚构角色。'
        with memory.transaction():
            root = memory.add_message('user', text, 's')
            store.observe(text, 0, root)
        original = store._restore
        ready, go, written = threading.Event(), threading.Event(), threading.Event(); failures = []
        def writer():
            try:
                with closing(MemoryStore(path)) as other:
                    ready.set(); go.wait()
                    with other.transaction():
                        fact = other.remember('受控根', source_message_id=root); other.forget(fact)
                        written.set()
            except Exception as error: failures.append(repr(error)); ready.set(); written.set()
        thread = threading.Thread(target=writer)
        thread.start(); assert ready.wait(2) and not failures
        def interleaved(revision, current):
            go.set(); assert written.wait(2)
            return original(revision, current)
        store._restore = interleaved
        changes = memory._conn.total_changes
        try: data = store.read('instance')
        finally: go.set(); thread.join(2)
        assert not thread.is_alive() and not failures
        assert data['revision'] == 0 and data['scope'] == 'fictional_character'
        assert memory._conn.total_changes == changes
        store._restore = original
        after = store.read('instance')
        assert after['revision'] == 1 and after['scope'] == 'unverified'

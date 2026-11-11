import json
import threading

import pytest

from avatar.brain.conversations import ConversationStore
from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.cancellation import Cancelled


def pair(memory, text='input', reply='reply', session='one', *, context_ids=(), prior=()):
    user = memory.add_message('user', text, session)
    assistant = memory.add_message('assistant', reply, session, context_ids=context_ids, source_message_ids=[user, *prior])
    result = {'reply': reply, 'trace': {'recalled_memories': [{'content': text}]},
              'conversation': {'session_id': session, 'revision': memory.context_revision,
                               'user_message_id': user, 'assistant_message_id': assistant}}
    ConversationStore(memory).record_result(result)
    return user, assistant, result


def test_pages_are_ordered_complete_and_do_not_invent_legacy_provenance(tmp_path):
    memory = MemoryStore(str(tmp_path/'pages.db'))
    try:
        legacy = memory.add_message('assistant', 'legacy reply', 'old')
        memory.add_message('system', 'private system prompt', 'old')
        _, assistant, result = pair(memory, session='new')
        read = ConversationStore(memory)
        newest = read.read('server', limit=2)
        assert [m['role'] for m in newest['items']] == ['user', 'assistant']
        assert newest['items'][-1]['result'] == result and newest['has_more']
        older = read.read('server', limit=2, before_id=newest['next_before_id'], revision=newest['revision'])
        assert older['items'] == [{'id': legacy, 'role': 'assistant', 'session_id': 'old',
                                   'created_at': older['items'][0]['created_at'], 'text': 'legacy reply', 'redacted': False}]
        assert not older['has_more'] and older['next_before_id'] is None
        assert newest['items'][-1]['id'] == assistant
        assert 'private system prompt' not in json.dumps([newest, older])
    finally:
        memory.close()


def test_unpaired_cancelled_user_has_no_restored_assistant_draft(tmp_path):
    memory = MemoryStore(str(tmp_path/'cancel.db'))
    try:
        user = memory.add_message('user', 'cancelled input', 'one')
        page = ConversationStore(memory).read('server')
        assert [(m['id'], m['role'], m['text']) for m in page['items']] == [(user, 'user', 'cancelled input')]
    finally:
        memory.close()


def test_forget_redacts_sources_and_transitive_replies_and_atomically_scrubs_traces(tmp_path):
    memory = MemoryStore(str(tmp_path/'privacy.db'))
    try:
        user = memory.add_message('user', 'secret-marker-11', 'one')
        fact = memory.remember_user('名字', 'secret-marker-11', source_message_id=user)
        assistant = memory.add_message('assistant', 'reply secret-marker-11', 'one', context_ids=[fact], source_message_ids=[user])
        result = {'reply': 'reply secret-marker-11', 'trace': {'content': 'secret-marker-11'},
                  'conversation': {'session_id': 'one', 'revision': 0, 'user_message_id': user, 'assistant_message_id': assistant}}
        store = ConversationStore(memory); store.record_result(result)
        pair(memory, 'followup', 'continued secret-marker-11', prior=[assistant])
        assert memory._conn.execute('SELECT count(*) FROM memory_chat_results').fetchone()[0] == 2
        memory.forget(fact)
        page = store.read('server')
        assert page['revision'] > 0 and 'secret-marker-11' not in json.dumps(page)
        assert memory._conn.execute('SELECT count(*) FROM memory_chat_results').fetchone()[0] == 0
        assert all('result' not in row for row in page['items'])
        assert [row['redacted'] for row in page['items']] == [True, True, False, True]
        with pytest.raises(OperationError) as error:
            store.read('server', revision=0)
        assert error.value.status == 409
        with pytest.raises(Cancelled):
            store.record_result(result)
    finally:
        memory.close()


def test_external_revision_prevents_late_result_storage(tmp_path):
    path = str(tmp_path/'external.db'); one, two = MemoryStore(path), MemoryStore(path)
    try:
        user, _, result = pair(one, 'erased')
        fact = two.remember_user('名字', 'erased', source_message_id=user)
        two.forget(fact)
        with pytest.raises(Cancelled):
            ConversationStore(one).record_result(result)
        assert one._conn.execute('SELECT count(*) FROM memory_chat_results').fetchone()[0] == 0
    finally:
        one.close(); two.close()


def test_original_trace_survives_connection_restart_but_bad_json_is_not_replayed(tmp_path):
    path = str(tmp_path/'restart.db'); memory = MemoryStore(path)
    _, assistant, result = pair(memory)
    memory.close(); memory = MemoryStore(path)
    try:
        assert ConversationStore(memory).read('new-server')['items'][-1]['result'] == result
        memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?', ('{broken', assistant))
        memory._conn.commit()
        item = ConversationStore(memory).read('new-server')['items'][-1]
        assert item['text'] == 'reply' and 'result' not in item
    finally:
        memory.close()


@pytest.mark.parametrize('change', ['session', 'reply', 'user_role'])
def test_result_cannot_bind_to_mismatching_source_rows(tmp_path, change):
    memory = MemoryStore(str(tmp_path/'mismatch.db'))
    try:
        user, assistant, result = pair(memory)
        memory._conn.execute('DELETE FROM memory_chat_results'); memory._conn.commit()
        if change == 'session': result['conversation']['session_id'] = 'another'
        elif change == 'reply': result['reply'] = 'different'
        else: result['conversation']['user_message_id'] = assistant
        with pytest.raises(Cancelled): ConversationStore(memory).record_result(result)
        assert memory._conn.execute('SELECT count(*) FROM memory_chat_results').fetchone()[0] == 0
    finally:
        memory.close()


def test_read_snapshot_remains_internally_consistent_during_concurrent_delete(tmp_path):
    path = str(tmp_path/'snapshot.db'); writer = MemoryStore(path)
    user, _, _ = pair(writer, 'snapshot-secret')
    fact = writer.remember_user('名字', 'snapshot-secret', source_message_id=user)
    pinned, staged = threading.Event(), threading.Event(); observed = []; failures = []

    def reader():
        memory = MemoryStore(path)
        class View:
            _conn = memory._conn
            @property
            def context_revision(self):
                revision = memory.context_revision
                pinned.set(); staged.wait()
                return revision
        try:
            observed.append(ConversationStore(View()).read('server'))
        except BaseException as error:
            failures.append(error)
        finally:
            memory.close()

    thread = threading.Thread(target=reader); thread.start(); pinned.wait()
    try:
        with writer.transaction():
            writer.forget(fact); staged.set(); thread.join()
        assert not failures and observed[0]['revision'] == 0
        assert observed[0]['items'][0]['text'] == 'snapshot-secret'
        current = ConversationStore(writer).read('server')
        assert current['revision'] > 0 and 'snapshot-secret' not in json.dumps(current)
    finally:
        staged.set(); writer.close()

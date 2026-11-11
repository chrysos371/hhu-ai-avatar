from contextlib import closing
import threading

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled, CancellationToken
from avatar.main import Avatar
from avatar.web import create_server, run_chat


class Offline:
    available = False
    def close(self): pass


@pytest.fixture
def servers(tmp_path, monkeypatch):
    import avatar.main as module
    monkeypatch.setattr(module, 'LLMEngine', Offline)
    path = str(tmp_path/'shared.db')
    owned = []
    def create():
        server = create_server(path, port=0); owned.append(server); return server
    yield path, create
    for server in owned: server.server_close()


@pytest.mark.parametrize('error', [Cancelled('cancelled after source commit'), RuntimeError('failed analysis')])
def test_interrupted_analysis_preserves_control_source_for_next_server(servers, monkeypatch, error):
    path, create = servers
    first = create()
    with monkeypatch.context() as patch:
        def interrupted(*_): raise error
        patch.setattr(Avatar, '_analyze', interrupted)
        with pytest.raises(type(error)): run_chat(first, '我来扮演小说角色。')
    second = create()
    result = run_chat(second, '提醒我明天9点带伞。')
    assert result['speaker_attribution']['scope'] == 'fictional_character'
    assert result['speaker_tool_blocked'] and result['reminder'] is None
    with closing(MemoryStore(path)) as memory:
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0] == 0
        assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='user'").fetchone()[0] == 2


def test_pre_cancel_does_not_persist_a_new_source_or_change_control(servers):
    path, create = servers
    server = create(); run_chat(server, '我来扮演小说角色。')
    token = CancellationToken(); token.cancel()
    class Job:
        def emit(self, *_): pass
    job = Job(); job.token = token
    with pytest.raises(Cancelled): run_chat(server, '回到现实。', job=job)
    result = run_chat(create(), '我叫林悦。')
    assert result['speaker_attribution']['scope'] == 'fictional_character'
    with closing(MemoryStore(path)) as memory:
        assert memory.get_user_profile() == {}
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE content='回到现实。'").fetchone()


def test_two_servers_do_not_overwrite_newer_control_when_earlier_analysis_finishes(servers, monkeypatch):
    path, create = servers
    first, second = create(), create()
    entered, release = threading.Event(), threading.Event()
    original = Avatar._analyze
    def slow(self, text):
        if text == '我来扮演小说角色。':
            entered.set(); release.wait()
        return original(self, text)
    monkeypatch.setattr(Avatar, '_analyze', slow)
    errors = []
    def run_first():
        try: run_chat(first, '我来扮演小说角色。')
        except Exception as error: errors.append(error)
    thread = threading.Thread(target=run_first); thread.start()
    try:
        assert entered.wait(2)
        result = run_chat(second, '提醒我明天9点带伞。')
        assert result['speaker_tool_blocked'] and result['reminder'] is None
    finally:
        release.set(); thread.join(2)
    assert not thread.is_alive() and errors == []
    result = run_chat(first, '我叫林悦。')
    assert result['speaker_attribution']['scope'] == 'fictional_character'
    with closing(MemoryStore(path)) as memory:
        assert memory.get_user_profile() == {}


def test_legacy_context_explains_confirmation_and_does_not_claim_due_reminders(servers):
    import time
    from avatar.brain.reminders import ReminderStore
    path, create = servers
    with closing(MemoryStore(path)) as memory:
        memory.add_message('user', '旧库没有可核验控制状态。', 'legacy')
        reminder = ReminderStore(memory).create('提醒我明天9点带伞。')
        memory._conn.execute('UPDATE memory_reminders SET due_at=? WHERE id=?', (time.time()-1, reminder['id']))
        memory._conn.commit()
    server = create()
    result = run_chat(server, '我叫新名。')
    assert result['speaker_attribution']['scope'] == 'unverified'
    assert '单独发送“回到现实”' in result['reply']
    assert result['due_reminders'] == []
    with closing(MemoryStore(path)) as memory:
        assert memory.get_user_profile() == {}
        assert ReminderStore(memory).list()[0]['notified_at'] is None
    run_chat(server, '回到现实。')
    result = run_chat(server, '我叫陈宁。')
    assert result['due_reminders'][0]['id'] == reminder['id']
    with closing(MemoryStore(path)) as memory:
        assert memory.get_user_profile() == {'名字': '陈宁'}

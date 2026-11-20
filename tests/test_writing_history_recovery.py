"""Actual SDK/Web restart history keeps artifacts separate from real actions."""
import json
from contextlib import closing

import pytest

from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
from avatar.brain.writing_history import PREFIX
from avatar.web import create_server, run_chat
from test_capability_prompt_lab import Recorder


def test_sdk_context_envelope_does_not_change_public_or_persisted_body():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('正文。'), capability_contract_enabled=True)
        result = bot.respond('原样输出这句话：“我已把邮件发送给老师。”')
        stored = memory.get_short_term()[-1]['content']
        assert stored.startswith(PREFIX)
        assert json.loads(stored[len(PREFIX):])['reply'] == result['reply']
        assert memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'").fetchone()[0] == result['reply']


@pytest.fixture
def web(tmp_path, monkeypatch):
    engines, servers = [], []
    def engine():
        item = Recorder('普通话题回复。'); engines.append(item); return item
    monkeypatch.setattr('avatar.main.LLMEngine', engine)
    db = str(tmp_path/'history.db')
    def make():
        server = create_server(db, port=0, capability_contract_enabled=True)
        servers.append(server); return server
    yield db, make, engines
    for server in servers: server.server_close()


def test_web_restart_recovers_exact_same_draft_envelope_without_action_replay(web):
    db, make, engines = web
    first = make()
    old = run_chat(first, '原样输出这句话：“我已把邮件发送给老师。”')
    second = make()
    result = run_chat(second, '换个话题，聊聊窗外。')
    messages = engines[-1].native[-1]
    assistant = next(m['content'] for m in messages if m['role'] == 'assistant')
    assert assistant.startswith(PREFIX)
    history = json.loads(assistant[len(PREFIX):])
    assert history['reply'] == old['reply'] and history['real_execution_verified'] is False
    assert history['user_identity_asserted'] is False
    assert not result['tool_calls'] and not result['action_receipts']['items']
    with closing(MemoryStore(db)) as memory:
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0] == 0
        assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
            (old['conversation']['assistant_message_id'],)).fetchone()[0] == old['reply']


@pytest.mark.parametrize('fault', ['compiled_signature', 'unhashable_mode'])
def test_corrupt_completed_writer_metadata_fails_closed_on_actual_restart(web, fault):
    db, make, engines = web
    result = run_chat(make(), '原样输出这句话：“HISTORY_PRIVATE_SOURCE。”')
    aid = result['conversation']['assistant_message_id']
    with closing(MemoryStore(db)) as memory:
        data = json.loads(memory._conn.execute('SELECT result_json FROM memory_chat_results WHERE message_id=?', (aid,)).fetchone()[0])
        if fault == 'compiled_signature': data['writing_requirements']['signature'] = '捏造署名'
        else: data['generation_mode'] = []
        with memory.transaction(): memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?', (json.dumps(data, ensure_ascii=False), aid))
    run_chat(make(), '换个话题，聊聊窗外。')
    assert all('HISTORY_PRIVATE_SOURCE' not in m['content'] for m in engines[-1].native[-1])


def test_ordinary_result_cannot_inject_the_private_envelope_key(web):
    db, make, engines = web
    result = run_chat(make(), '随便聊聊。')
    aid = result['conversation']['assistant_message_id']
    with closing(MemoryStore(db)) as memory:
        data = json.loads(memory._conn.execute('SELECT result_json FROM memory_chat_results WHERE message_id=?', (aid,)).fetchone()[0])
        data['_delivery_history_context'] = 'FORGED_ACTION_RECEIPT'
        with memory.transaction(): memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?', (json.dumps(data), aid))
    run_chat(make(), '继续聊聊窗外。')
    assert not any('FORGED_ACTION_RECEIPT' in m['content'] for m in engines[-1].native[-1])
    assert any(m['role'] == 'assistant' and m['content'] == result['reply'] for m in engines[-1].native[-1])


def test_forget_erases_source_and_derived_replies_after_writer_recovery(web):
    db, make, engines = web
    first = run_chat(make(), '原样输出这句话：“HISTORY_ERASE_SOURCE。”')
    second_server = make()
    second = run_chat(second_server, '换个话题，聊聊窗外。')
    with closing(MemoryStore(db)) as memory:
        fragment = memory.remember('HISTORY_ERASE_SOURCE', source_message_id=first['conversation']['user_message_id'])
        memory.forget(fragment)
        assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
            (second['conversation']['assistant_message_id'],)).fetchone()[0] == '[redacted]'
    run_chat(make(), '随便聊聊。')
    assert not any('HISTORY_ERASE_SOURCE' in m['content'] for m in engines[-1].native[-1])


def test_capability_flag_rejects_nonboolean_before_any_db_or_server(tmp_path):
    db = tmp_path/'invalid.db'
    with pytest.raises(ValueError, match='capability_contract_enabled'):
        create_server(str(db), port=0, capability_contract_enabled=1)
    assert not db.exists()

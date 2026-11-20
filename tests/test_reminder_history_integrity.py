"""History-only semantics, source corruption, privacy and actual Web restart."""
from contextlib import closing
import copy
import json
import sqlite3

import pytest

from avatar.brain.conversation_context import ConversationContextStore
from avatar.brain.memory import MemoryStore
from avatar.brain.reminder_history import HistoryReader, PREFIX, public_observation, request_kind
from avatar.cancellation import Cancelled, CancellationToken
from avatar.main import Avatar
from avatar.web import create_server, run_chat
from test_capability_prompt_lab import Recorder
from test_reminder_query_flow import projection, seed


def ready(tmp_path):
    memory = MemoryStore(str(tmp_path/'history.db'))
    seed(memory, due=False)
    model = Recorder('错误的现在状态，不应作为历史解释。')
    bot = Avatar(memory=memory, llm=model, capability_contract_enabled=True, role_state_enabled=True)
    query = bot.respond('提醒编号1现在是什么状态？', mode='reminder_query')
    return memory, bot, query, model


@pytest.mark.parametrize('fault', ['state', 'ack', 'bool_id', 'planned_time', 'future_observation', 'reply', 'missing_dep', 'deleted_source'])
def test_corrupt_public_observation_never_becomes_a_verified_explanation(tmp_path, fault):
    memory, bot, old, model = ready(tmp_path)
    with closing(memory):
        data = copy.deepcopy(old); q = data['reminder_query']; aid = data['conversation']['assistant_message_id']
        if fault == 'state': q['state']['status'] = 'completed'
        elif fault == 'ack': q['state']['client_ack_recorded'] = 1
        elif fault == 'bool_id': q['state']['id'] = True
        elif fault == 'planned_time': q['state']['due_at'] += 3600
        elif fault == 'future_observation': q['observed_at'] = 253402300799
        elif fault == 'reply': data['reply'] = '我已读取当前记录并发短信。'
        with memory.transaction():
            if fault == 'reply': memory._conn.execute('UPDATE memory_messages SET content=? WHERE id=?', (data['reply'], aid))
            memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?', (json.dumps(data), aid))
            if fault == 'missing_dep': memory._conn.execute('DELETE FROM memory_response_context WHERE message_id=?', (aid,))
            if fault == 'deleted_source': memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (old['conversation']['user_message_id'],))
        result = bot.respond('刚才那次查询看到了什么？此刻仍然有效吗？')
        assert result['generation_mode'] != 'rules_reminder_history' and 'reminder_history' not in result


def test_hidden_claim_flag_cannot_change_explanation_and_business_tables_are_not_read(tmp_path):
    memory, bot, query, model = ready(tmp_path)
    with closing(memory):
        result = bot.respond('刚才查询的状态是什么？')
        assert result['generation_mode'] == 'rules_reminder_history'
        aid = query['conversation']['assistant_message_id']
        value = copy.deepcopy(query); value['reminder_query']['state']['service_claim_recorded'] = 'FORGED-SECRET-CLAIM'
        with memory.transaction():
            memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?', (json.dumps(value), aid))
        def authorize(action, table, *args):
            if action == sqlite3.SQLITE_READ and table in ('memory_reminders', 'memory_reminder_deliveries'):
                return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK
        memory._conn.set_authorizer(authorize)
        try:
            source = result['conversation']
            reader = HistoryReader(memory, text='刚才查询的状态是什么？', user_id=source['user_message_id'],
                session_id=source['session_id'], revision=source['revision'])
            assert reader.result.reply == result['reply']
            reader.ensure_current()
            assert 'FORGED' not in json.dumps(reader.result.metadata)
        finally: memory._conn.set_authorizer(None)


@pytest.mark.parametrize('kind', ['state', 'missing', 'policy'])
def test_ack_is_three_valued_and_due_time_not_creation_time(tmp_path, kind):
    memory = MemoryStore(str(tmp_path/'ack.db'))
    with closing(memory):
        seed(memory, due=False)
        bot = Avatar(memory=memory, llm=Recorder('unused'), capability_contract_enabled=True, role_state_enabled=True)
        text = {'state':'提醒编号1状态？', 'missing':'提醒编号99状态？', 'policy':'程序退出后提醒还能发短信吗？'}[kind]
        query = bot.respond(text, mode='reminder_query')
        snapshot = public_observation(query['reply'], query['reminder_query'])
        assert snapshot['client_ack_recorded'] is (False if kind == 'state' else None)
        assert 'created_at' not in snapshot and 'service_claim_recorded' not in snapshot


@pytest.mark.parametrize('text', [
    '帮我写一句“刚才查询的状态是什么？”', '“刚才查询的状态是什么？”',
    '刚才查询后顺便帮我写论文。', '刚才提醒记录里我的名字是什么？',
    '刚才查询记录里有多少个字？', '不要解释上次查询状态。',
    '现在打电话通知我刚才那件事，告诉我电话拨出了吗。',
])
def test_quoted_writing_other_goals_and_execution_do_not_enter_history_renderer(text):
    assert request_kind(text) is None


@pytest.mark.parametrize('change', ['cancel', 'forget', 'source_content'])
def test_late_real_change_prevents_explanation_publication(tmp_path, monkeypatch, change):
    memory, bot, query, model = ready(tmp_path)
    with closing(memory):
        token, deltas = CancellationToken(), []
        fragment = memory.remember('查询来源保密控制', source_message_id=query['conversation']['user_message_id'])
        original = bot._analyze
        def changed(text):
            original(text)
            if change == 'cancel': token.cancel()
            else:
                with closing(MemoryStore(memory.db_path)) as actor:
                    if change == 'forget': actor.forget(fragment)
                    else:
                        with actor.transaction():
                            actor._conn.execute('UPDATE memory_messages SET content=? WHERE id=?',
                                ('另一个来源', query['conversation']['user_message_id']))
        monkeypatch.setattr(bot, '_analyze', changed)
        with pytest.raises(Cancelled): bot.respond('刚才查询的状态是什么？', cancel=token, on_delta=deltas.append)
        assert not deltas and not model.native
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_messages WHERE role="assistant" AND content LIKE "第1次保留%"').fetchone()[0] == 0


def test_current_cognition_remains_and_due_claim_is_skipped(tmp_path):
    memory, bot, query, model = ready(tmp_path)
    with closing(memory):
        with memory.transaction(): memory._conn.execute('UPDATE memory_reminders SET due_at=1 WHERE id=1')
        before = projection(memory)
        result = bot.respond('刚才查询的状态是什么？')
        assert len(model.analysis) == 1 and not model.native
        assert projection(memory) == before and not result['due_reminders']
        assert result['reminder_history']['observations'][0]['state'] == 'active'
        assert not result['reminder_history']['business_data_read']


def test_actual_web_restart_preserves_verified_explanation_and_original_public_sql(tmp_path, monkeypatch):
    engines = []
    def factory():
        engine = Recorder('普通回复'); engines.append(engine); return engine
    monkeypatch.setattr('avatar.main.LLMEngine', factory)
    db = str(tmp_path/'web.db')
    def make(): return create_server(db, port=0, capability_contract_enabled=True, role_state_enabled=True)
    first = make()
    try:
        with closing(MemoryStore(db)) as memory: seed(memory, due=False)
        query = run_chat(first, '提醒编号1现在是什么状态？', mode='reminder_query')
    finally: first.server_close()
    second = make()
    try:
        history = run_chat(second, '刚才查询的状态是什么？')
        assert history['generation_mode'] == 'rules_reminder_history'
        assert history['reminder_history']['source_query_user_ids'] == [query['conversation']['user_message_id']]
    finally: second.server_close()
    third = make()
    try:
        run_chat(third, '聊聊窗外。')
        payloads = [json.loads(m['content'][len(PREFIX):]) for m in engines[-1].native[-1]
            if m['role'] == 'assistant' and m['content'].startswith(PREFIX)]
        assert payloads[0]['reply'] == history['reply']
        with closing(MemoryStore(db)) as memory:
            assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
                (history['conversation']['assistant_message_id'],)).fetchone()[0] == history['reply']
    finally: third.server_close()

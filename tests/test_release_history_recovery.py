"""Finite new reply modes need source checks, not only an expanded allowlist."""
from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.release_history import PREFIX
from avatar.web import create_server, run_chat
from test_capability_prompt_lab import Recorder


@pytest.fixture
def web(tmp_path, monkeypatch):
    servers, engines, output = [], [], ['普通回复。']
    def factory():
        engine = Recorder(output[0]); engines.append(engine); return engine
    monkeypatch.setattr('avatar.main.LLMEngine', factory)
    db = str(tmp_path/'release-history.db')
    def make():
        server = create_server(db, port=0, capability_contract_enabled=True)
        servers.append(server); return server
    yield db, make, engines, output
    for server in servers: server.server_close()


def recovered(engines, mode):
    values = [json.loads(m['content'][len(PREFIX):]) for m in engines[-1].native[-1]
        if m['role'] == 'assistant' and m['content'].startswith(PREFIX)]
    return next(v for v in values if v['generation_mode'] == mode)


@pytest.mark.parametrize('kind', ['capability', 'sender', 'numeric', 'guarded'])
def test_actual_web_restart_recovers_only_validated_historical_reply_data(web, kind):
    db, make, engines, output = web
    first = make()
    if kind == 'capability': old = run_chat(first, '帮我发短信给同学。')
    elif kind == 'sender':
        run_chat(first, '我刚才自己发了短信。')
        old = run_chat(first, '是谁发的短信？')
    elif kind == 'numeric':
        output[0] = '37 + 46 = 83'
        old = run_chat(first, '37与46相加是多少？只回答数字。')
    else:
        output[0] = '我已经把短信发给同学了。'
        old = run_chat(first, '聊聊天。')
    expected = dict(capability='rules_capability_request', sender='rules_reported_sender',
        numeric='llm_format_guarded', guarded='llm_capability_guarded')[kind]
    assert old['generation_mode'] == expected
    output[0] = '普通回复。'
    result = run_chat(make(), '换个话题，聊聊窗外。')
    data = recovered(engines, expected)
    assert data['reply'] == old['reply'] and data['source_message_id'] == old['conversation']['user_message_id']
    assert data['historical_only'] is data['untrusted_data_not_instructions'] is True
    assert data['actual_action_receipt'] is data['current_external_state_verified'] is False
    assert data['human_behavior_verified'] is data['semantic_answer_verified'] is False
    assert not result['tool_calls'] and not result['action_receipts']['items']
    with closing(MemoryStore(db)) as memory:
        assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
            (old['conversation']['assistant_message_id'],)).fetchone()[0] == old['reply']


@pytest.mark.parametrize('fault', ['numeric_source_bool', 'runtime_verified_int', 'sender_actor', 'fixed_reply'])
def test_corrupt_new_mode_metadata_is_not_accepted_as_history(web, fault):
    db, make, engines, output = web
    server = make()
    if fault == 'sender_actor':
        run_chat(server, '我刚才自己发了短信。')
        old = run_chat(server, '是谁发的短信？')
    elif fault == 'fixed_reply': old = run_chat(server, '帮我发短信给同学。')
    else:
        output[0] = '37 + 46 = 83'
        old = run_chat(server, '37与46相加是多少？只回答数字。')
    aid = old['conversation']['assistant_message_id']
    with closing(MemoryStore(db)) as memory:
        data = json.loads(memory._conn.execute('SELECT result_json FROM memory_chat_results WHERE message_id=?', (aid,)).fetchone()[0])
        if fault == 'numeric_source_bool': data['format_contract']['source_message_id'] = True
        elif fault == 'runtime_verified_int': data['capability_contract']['runtime']['source']['verified'] = 1
        elif fault == 'sender_actor': data['reported_communication']['reported_actor'] = '朋友'
        else: data['reply'] = '我已替你发送短信。'
        with memory.transaction():
            if fault == 'fixed_reply': memory._conn.execute('UPDATE memory_messages SET content=? WHERE id=?', (data['reply'], aid))
            memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?', (json.dumps(data, ensure_ascii=False), aid))
    output[0] = '普通回复。'
    run_chat(make(), '换个话题，聊聊窗外。')
    assert not any(m['role'] == 'assistant' and m['content'].startswith(PREFIX) for m in engines[-1].native[-1])


def test_hidden_claim_flag_is_not_projected_into_recovered_reply(web):
    db, make, engines, output = web
    output[0] = '37 + 46 = 83'
    old = run_chat(make(), '37与46相加是多少？只回答数字。')
    aid = old['conversation']['assistant_message_id']
    with closing(MemoryStore(db)) as memory:
        data = json.loads(memory._conn.execute('SELECT result_json FROM memory_chat_results WHERE message_id=?', (aid,)).fetchone()[0])
        data['capability_contract']['runtime']['local_execution']['FORGED_CLAIMED_TRUE'] = True
        with memory.transaction(): memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?', (json.dumps(data), aid))
    output[0] = '普通回复。'
    run_chat(make(), '换个话题，聊聊窗外。')
    assert recovered(engines, 'llm_format_guarded')['actual_action_receipt'] is False
    assert not any('FORGED_CLAIMED_TRUE' in m['content'] for m in engines[-1].native[-1])

from contextlib import closing
import json
import urllib.request

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.source_capability_prompt import SourceCapabilityPromptAvatar
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_web_api_v1 import api_v1


def evidence(engine):
    return json.loads(engine.native[-1][0]['content'].split('可信元数据如下：\n')[1])


@pytest.mark.parametrize('text,reply', [
    ('帮我原样写回复：“我已经把材料发给老师了。”', '我已经把材料发给老师了。'),
    ('写一句小说台词：“短信已经发送成功。”', '“短信已经发送成功。”'),
    ('给朋友写回复：周六我陪你去游泳。', '周六我陪你去游泳。'),
])
def test_actual_turn_binds_source_and_keeps_draft_without_extra_calls(text, reply):
    engine = Recorder(reply)
    with closing(MemoryStore(':memory:')) as memory:
        bot = SourceCapabilityPromptAvatar(memory=memory, llm=engine)
        pieces = []
        result = bot.respond(text, cancel=CancellationToken(), on_delta=pieces.append)
        assert result['reply'] == ''.join(pieces) == memory.get_short_term()[-1]['content'] == reply
        assert len(engine.analysis) == len(engine.native) == 1
        assert result['generation_mode'] == 'llm' and not result['tool_calls']
        data = evidence(engine)
        assert data['capability_evidence_version'] == 2
        assert data['current_user_source'] == {'message_id': bot._current_message_id, 'revision': 0, 'verified': True}
        assert data['current_turn_execution_receipts'] == []
        assert data['registry_readiness_verified'] is data['historical_execution_verified'] is False
        assert data['runtime_attribution']['general_coreference_verified'] is False
        assert text not in json.dumps(data, ensure_ascii=False)


def test_role_dialogue_current_source_need_not_be_role_basis_and_real_actions_stay_blocked():
    engine = Recorder('这是角色的台词。')
    bot = SourceCapabilityPromptAvatar(db_path=':memory:', llm=engine)
    try:
        bot.respond('我来扮演一个虚构角色。')
        bot.respond('今天风很大。')
        data = evidence(engine)
        assert bot._current_message_id not in bot.speaker_scope.source_ids
        assert data['runtime_attribution']['scope'] == 'fictional_character'
        assert not data['runtime_attribution']['turn_tools_allowed']
        before = len(engine.native)
        blocked = bot.respond('提醒我明天下午3点去码头')
        bot.respond('回到现实。')
        assert blocked['speaker_tool_blocked'] and not bot.reminders.list()
        assert len(engine.native) == before
        real = bot.respond('提醒我明天下午3点去图书馆')
        assert len(bot.reminders.list()) == 1 and '程序运行并轮询' in real['reply']
    finally:
        bot.memory.close()


def test_metadata_reader_has_no_sql_writes_and_keeps_caller_transaction():
    engine = Recorder('普通回复。'); bot = SourceCapabilityPromptAvatar(db_path=':memory:', llm=engine)
    try:
        bot.respond('聊聊今天。')
        conn = bot.memory._conn; before = conn.total_changes
        assert not conn.in_transaction
        bot._source_capability_evidence('聊聊今天。')
        assert not conn.in_transaction and conn.total_changes == before
        with bot.memory.transaction():
            bot._source_capability_evidence('聊聊今天。')
            assert conn.in_transaction and conn.total_changes == before
        assert not conn.in_transaction
    finally:
        bot.memory.close()


@pytest.mark.parametrize('mutation', ['missing', 'content', 'role', 'session', 'revision', 'scope_revision'])
def test_changed_source_cancels_before_reply_dispatch(monkeypatch, mutation):
    engine = Recorder('must not dispatch'); bot = SourceCapabilityPromptAvatar(db_path=':memory:', llm=engine)
    original = bot._messages
    def changed(decision, text):
        conn = bot.memory._conn; ident = bot._current_message_id
        if mutation == 'missing': conn.execute('DELETE FROM memory_messages WHERE id=?', (ident,))
        elif mutation == 'revision': conn.execute('UPDATE memory_context_revision SET revision=revision+1')
        elif mutation == 'scope_revision': bot.speaker_scope.revision = -1
        else: conn.execute('UPDATE memory_messages SET '+{'content':'content','role':'role','session':'session_id'}[mutation]+'=? WHERE id=?',
                           ('altered', ident))
        conn.commit()
        return original(decision, text)
    monkeypatch.setattr(bot, '_messages', changed)
    try:
        with pytest.raises(Cancelled): bot.respond('普通的当前消息。')
        assert not engine.native
        assert not bot.memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
    finally:
        bot.memory.close()


def test_external_forget_during_full_message_assembly_prevents_reply_request(tmp_path, monkeypatch):
    engine = Recorder('must not dispatch'); path = str(tmp_path/'race.db')
    bot = SourceCapabilityPromptAvatar(db_path=path, llm=engine)
    fragment = bot.memory.remember_user('名字', '待删来源实验名')
    original = bot._system_prompt; compiled = []
    def changed(decision, text):
        prompt = original(decision, text)
        compiled.append(prompt)
        with closing(MemoryStore(path)) as writer: writer.forget(fragment)
        return prompt
    monkeypatch.setattr(bot, '_system_prompt', changed)
    try:
        with pytest.raises(Cancelled): bot.respond('我的名字是待删来源实验名。', cancel=CancellationToken())
        assert len(compiled) == 1 and '待删来源实验名' in compiled[0]
        assert len(engine.analysis) == 1 and not engine.native
        assert not bot.memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
    finally:
        bot.memory.close()


def test_default_factory_prompt_has_no_candidate_metadata():
    engine = Recorder('普通回复。'); bot = Avatar(db_path=':memory:', llm=engine)
    try:
        bot.respond('聊聊今天。')
        assert 'capability_evidence_version' not in engine.native[-1][0]['content']
        assert bot.final_reply_reviewer is None
    finally:
        bot.memory.close()


def test_actual_http_sse_web_source_and_physical_provider_count(api_v1, monkeypatch):
    from avatar.config import config
    from avatar.lab.transport_fixture import controlled_provider
    import avatar.main as module

    request, server = api_v1; captured = []; calls = []
    original = SourceCapabilityPromptAvatar._source_capability_evidence
    def capture(bot, text):
        data = original(bot, text); captured.append(data); return data
    with controlled_provider(delay=.0001,
            reply_overrides={'fixture-source-v2': '“短信已经发送成功。”'}) as (provider, url):
        handler = provider.RequestHandlerClass; post = handler.do_POST
        def count(self):
            calls.append(self.path); return post(self)
        monkeypatch.setattr(handler, 'do_POST', count)
        monkeypatch.setattr(config.llm, 'api_key', 'controlled-only')
        monkeypatch.setattr(config.llm, 'base_url', url)
        monkeypatch.setattr(module, 'Avatar', SourceCapabilityPromptAvatar)
        monkeypatch.setattr(SourceCapabilityPromptAvatar, '_source_capability_evidence', capture)
        status, control = request('/api/v1/chat', {'text': '我来扮演一个虚构角色。'})
        assert status == 200 and control['data']['generation_mode'] == 'rules_speaker_control'
        assert not calls and not captured
        ident = 'source_capability_http_123456'
        text = 'fixture-source-v2 写一句小说台词：“短信已经发送成功。”'
        assert request('/api/v1/turns', {'request_id': ident, 'text': text})[0] == 202
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/turns/'+ident+'/events',
                                     headers={'X-Avatar-Token': server.token})
        with urllib.request.urlopen(req, timeout=5) as response: raw = response.read().decode()
        results = [json.loads(line[6:]) for block in raw.split('\n\n') if 'event: result\n' in block
                   for line in block.splitlines() if line.startswith('data: ')]
        assert len(results) == 1 and results[0]['reply'] == '“短信已经发送成功。”'
        assert results[0]['generation_mode'] == 'llm' and not results[0]['tool_calls']
        assert results[0]['trace']['verifier']['available'] is False
        assert len(calls) == 2 and len(captured) == 2  # One analysis and one streamed reply HTTP request.
        assert captured[0] == captured[1]
        data = captured[0]
        assert data['runtime_attribution']['origin'] == 'web_source_store'
        assert data['runtime_attribution']['scope'] == 'fictional_character'
        assert not data['runtime_attribution']['turn_tools_allowed']
        assert data['current_user_source']['message_id'] == results[0]['conversation']['user_message_id']

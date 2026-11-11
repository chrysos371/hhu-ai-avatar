import json
from types import SimpleNamespace
import urllib.request

import pytest

from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.capability_prompt import CapabilityPromptAvatar, capability_evidence
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar
from test_web_api_v1 import api_v1


class Recorder:
    available = True
    def __init__(self, reply): self.reply = reply; self.native = []; self.analysis = []
    def chat_analysis(self, messages, **kwargs):
        self.analysis.append(messages)
        return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
    def chat(self, messages, **kwargs):
        self.native.append(messages)
        return self.reply
    def stream_chat(self, messages, *, on_delta=None, cancel=None, **kwargs):
        self.native.append(messages)
        if cancel: cancel.checkpoint()
        if on_delta: on_delta(self.reply)
        return self.reply


def test_metadata_is_bounded_actual_registry_without_private_context_or_execution():
    data = capability_evidence()
    assert data['declared_model_tool_names'] == ['get_weather', 'list_reminders', 'read_webpage', 'search_documents', 'web_search']
    assert data['current_turn_execution_receipts'] == [] and data['semantic_verifier'] is False
    assert set(data) == {'capability_evidence_version', 'branch', 'declared_model_tool_names',
        'current_turn_execution_receipts', 'unsupported_actions', 'local_reminder_writes', 'semantic_verifier'}


@pytest.mark.parametrize('names', [{'send_sms'}, {'send_email'}, {'place_call'}, {'bad\ninstruction'}, {'a'*65}])
def test_changed_or_unbounded_registry_requires_new_experimental_validation(names):
    with pytest.raises(ValueError): capability_evidence(SimpleNamespace(names=names))


def test_production_prompt_is_unchanged_and_candidate_only_appends_metadata():
    base = Avatar(db_path=':memory:', session_id='same')
    candidate = CapabilityPromptAvatar(db_path=':memory:', session_id='same')
    try:
        decision = base.emotion.decide('普通草稿')
        original = base._system_prompt(decision, '普通草稿')
        text = candidate._system_prompt(decision, '普通草稿')
        assert 'capability_evidence_version' not in original
        assert text.startswith(original) and 'capability_evidence_version' in text
        assert base.final_reply_reviewer is candidate.final_reply_reviewer is None
    finally: base.memory.close(); candidate.memory.close()


@pytest.mark.parametrize('input_text,reply', [
    ('帮我原样写一句回复，不实际发送：“我已经把材料发给老师了。”', '我已经把材料发给老师了。'),
    ('写一句小说台词：“短信已经发送成功。”', '“短信已经发送成功。”'),
    ('给朋友写回复：周六我陪你去游泳。', '周六我陪你去游泳。'),
])
def test_candidate_does_not_edit_model_supplied_drafts_or_add_calls(input_text, reply):
    engine = Recorder(reply); bot = CapabilityPromptAvatar(db_path=':memory:', llm=engine)
    try:
        pieces = []; result = bot.respond(input_text, cancel=CancellationToken(), on_delta=pieces.append)
        assert result['reply'] == ''.join(pieces) == bot.memory.get_short_term()[-1]['content'] == reply
        assert result['generation_mode'] == 'llm' and len(engine.native) == len(engine.analysis) == 1
        assert not result['tool_calls'] and not bot.reminders.list()
    finally: bot.memory.close()


def test_local_real_reminder_receipt_and_blocked_role_exit_do_not_replay():
    engine = Recorder('只是普通回复。'); bot = CapabilityPromptAvatar(db_path=':memory:', llm=engine)
    try:
        receipt = bot.respond('提醒我明天下午3点去图书馆')
        assert receipt['reminder']['title'] == '去图书馆' and len(bot.reminders.list()) == 1
        assert not engine.native and '程序运行并轮询' in receipt['reply']
        bot.respond('我来扮演一个虚构角色。')
        blocked = bot.respond('提醒我明天下午3点去码头')
        assert blocked['speaker_tool_blocked'] and len(bot.reminders.list()) == 1
        bot.respond('回到现实。')
        assert len(bot.reminders.list()) == 1 and bot.reminders.list()[0]['title'] == '去图书馆'
    finally: bot.memory.close()


def test_cancel_before_candidate_turn_has_no_source_or_model_call():
    engine = Recorder('unused'); bot = CapabilityPromptAvatar(db_path=':memory:', llm=engine)
    token = CancellationToken(); token.cancel()
    try:
        with pytest.raises(Cancelled): bot.respond('请发短信', cancel=token)
        assert not engine.native and not engine.analysis
        assert not bot.memory._conn.execute('SELECT 1 FROM memory_messages').fetchone()
        assert not bot.memory.get_short_term()
    finally: bot.memory.close()


def test_privacy_forget_does_not_copy_deleted_context_into_capability_metadata():
    engine = Recorder('普通回复。'); bot = CapabilityPromptAvatar(db_path=':memory:', llm=engine)
    try:
        ident = bot.memory.remember_user('名字', '待删实验名')
        bot.respond('我的名字是待删实验名。', cancel=CancellationToken())
        assert '待删实验名' in json.dumps(engine.native[-1], ensure_ascii=False)
        bot.forget_memory(ident)
        bot.respond('回到现实。', cancel=CancellationToken())
        assert '待删实验名' not in json.dumps(engine.native[-1], ensure_ascii=False)
        assert 'capability_evidence_version' in engine.native[-1][0]['content']
    finally: bot.memory.close()


def test_actual_http_sse_candidate_preserves_quote_with_no_final_reviewer(api_v1, monkeypatch):
    request, server = api_v1
    from avatar.config import config
    import avatar.main as module
    text = 'fixture-capability 引用“短信已经发送成功。”'
    with controlled_provider(delay=.0001, reply_overrides={'fixture-capability': '“短信已经发送成功。”'}) as (_, url):
        monkeypatch.setattr(config.llm, 'api_key', 'controlled-only')
        monkeypatch.setattr(config.llm, 'base_url', url)
        monkeypatch.setattr(module, 'Avatar', CapabilityPromptAvatar)
        ident = 'capability_prompt_http_123456'
        assert request('/api/v1/turns', {'request_id': ident, 'text': text})[0] == 202
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/turns/'+ident+'/events',
            headers={'X-Avatar-Token': server.token})
        with urllib.request.urlopen(req, timeout=5) as response: raw = response.read().decode()
        blocks = [block for block in raw.split('\n\n') if 'event: result\n' in block]
        assert len(blocks) == 1
        result = json.loads(next(line[6:] for line in blocks[0].splitlines() if line.startswith('data: ')))
        assert result['reply'] == '“短信已经发送成功。”' and result['generation_mode'] == 'llm'
        assert result['trace']['verifier']['available'] is False

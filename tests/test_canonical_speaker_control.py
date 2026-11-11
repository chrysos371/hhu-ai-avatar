import json

import pytest

from avatar.cancellation import CancellationToken
from avatar.main import Avatar


class Spy:
    available = True
    def __init__(self): self.analysis_calls = 0; self.reply_calls = 0
    def chat_analysis(self, *args, **kwargs):
        self.analysis_calls += 1
        return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
    def chat(self, *args, **kwargs):
        self.reply_calls += 1
        return '我已记录下你的提醒：明天下午3点去码头。'
    def stream_chat(self, *args, on_delta=None, **kwargs):
        value = self.chat(*args, **kwargs)
        if on_delta: on_delta(value)
        return value


@pytest.mark.parametrize('text,scope', [
    ('我来扮演一个虚构角色。', 'fictional_character'),
    ('我来扮演一个虚构角色', 'fictional_character'),
    ('回到现实。', 'current_user'), ('回到现实', 'current_user'),
    ('  回到现实。\n', 'current_user'),
])
def test_canonical_control_never_asks_model_to_confirm_action_state(text, scope):
    engine = Spy(); bot = Avatar(db_path=':memory:', llm=engine)
    try:
        result = bot.respond(text, cancel=CancellationToken())
        assert result['generation_mode'] == 'rules_speaker_control'
        assert result['analysis_mode'] == 'rules_speaker_control'
        assert engine.analysis_calls == engine.reply_calls == 0
        assert result['speaker_attribution']['scope'] == scope
        assert result['speaker_control']['source_message_id'] == result['conversation']['user_message_id']
        assert result['speaker_control']['scope'] == scope
        assert not result['tool_calls'] and not bot.reminders.list()
        assert '已记录' not in result['reply'] and '已设置' not in result['reply']
        assert bot.memory.get_short_term()[-1]['content'] == result['reply']
    finally: bot.memory.close()


@pytest.mark.parametrize('text', [
    '“我来扮演一个虚构角色。”', '“回到现实。”', '请原样写“回到现实。”',
    '回到现实吗？', '如果回到现实。', '回到现实。我的名字是陈原。',
    '我来扮演一个虚构角色。我叫许照。', '停止扮演。', '今天聊点日常。',
])
def test_new_shortcut_does_not_consume_quotes_writing_aliases_or_compound_turns(text):
    engine = Spy(); bot = Avatar(db_path=':memory:', llm=engine)
    try:
        result = bot.respond(text)
        assert result['generation_mode'] != 'rules_speaker_control'
        assert 'speaker_control' not in result
        if '我的名字是陈原' in text: assert bot.memory.get_user_profile().get('名字') == '陈原'
    finally: bot.memory.close()


def test_reality_control_does_not_confirm_or_replay_blocked_old_reminder():
    engine = Spy(); bot = Avatar(db_path=':memory:', llm=engine)
    try:
        bot.respond('我来扮演一个虚构角色。')
        blocked = bot.respond('提醒我明天下午3点去码头')
        assert blocked['speaker_tool_blocked'] and not bot.reminders.list()
        before = (engine.analysis_calls, engine.reply_calls)
        result = bot.respond('回到现实。')
        assert result['generation_mode'] == 'rules_speaker_control'
        assert (engine.analysis_calls, engine.reply_calls) == before
        assert '码头' not in result['reply'] and not bot.reminders.list()
        real = bot.respond('提醒我明天下午3点去图书馆')
        assert real['reminder']['title'] == '去图书馆' and len(bot.reminders.list()) == 1
    finally: bot.memory.close()


def test_control_use_web_true_cannot_run_agent():
    class Forbidden:
        def run(self, *args, **kwargs): pytest.fail('canonical control must not invoke web agent')
    engine = Spy(); bot = Avatar(db_path=':memory:', llm=engine); bot.web_agent = Forbidden()
    try:
        result = bot.respond('回到现实。', use_web=True)
        assert result['generation_mode'] == 'rules_speaker_control'
        assert engine.analysis_calls == engine.reply_calls == 0
        assert not result['tool_calls'] and not bot.reminders.list()
    finally: bot.memory.close()

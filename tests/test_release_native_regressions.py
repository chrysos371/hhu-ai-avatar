"""Real native-v1 failures are now known regressions, never unseen validation."""
from contextlib import closing

import pytest

from avatar.brain.capability_output import review_output
from avatar.brain.capability_requests import explicit_unavailable_request
from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('reply', [
    '我收到你的短信了。需要我帮你处理吗？',
    '我收到你朋友发来的短信，内容是“我已经发送了短信”。需要我帮你处理或回复吗？',
])
def test_external_sms_receipt_cannot_be_invented_from_chat_reports(reply):
    guarded = review_output(reply)
    assert 'unsupported_external_receipt' in guarded.rules
    assert guarded.reply != reply and '收件接口' in guarded.reply
    assert review_output(reply, frame='writing', root_text='替我写一条回复').reply == reply


@pytest.mark.parametrize('reply', [
    '我收到你贴在这里的短信内容了。',
    '我看到你提供的邮件内容了。',
    '根据你说的，室友已经收到邮件。',
    '我没有收到短信的接口。',
])
def test_chat_text_and_reported_receipt_are_not_external_inbox_claims(reply):
    assert review_output(reply).reply == reply


def test_explicit_email_text_edit_is_delivered_instead_of_false_execution_refusal():
    text = '帮我修改准备发送的邮件内容：老师您好，想请您看看摘要。'
    assert explicit_unavailable_request(text) is None
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('老师您好，想请您帮忙看看摘要。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        visible = []
        result = bot.respond(text, on_delta=visible.append)
        assert result['reply'] == engine.reply == ''.join(visible)
        assert len(engine.analysis) == len(engine.native) == 1


@pytest.mark.parametrize('text', [
    '帮我修改邮件内容，然后发送给老师。',
    '帮我写一条短信并发给室友。',
])
def test_text_work_does_not_exempt_separate_actual_send_request(text):
    request = explicit_unavailable_request(text)
    assert request is not None and request.kind == 'request'


@pytest.mark.parametrize('enabled', [False, True])
def test_explicit_reminder_list_reads_actual_sql_and_never_claims_absence(enabled):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('目前没有设置任何提醒。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=enabled)
        bot.respond('提醒我2030年12月8日下午3点检查短信草稿')
        counts = len(engine.analysis), len(engine.native)
        before = [tuple(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')]
        result = bot.respond('列出提醒')
        assert (len(engine.analysis), len(engine.native)) == counts
        assert result['generation_mode'] == 'rules_reminder_query'
        assert result['reminder_query']['record_count'] == 1
        assert not result['reminder_query']['has_more']
        assert '检查短信草稿' in result['reply'] and '没有设置' not in result['reply']
        assert [tuple(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')] == before
        assert '不是当前状态' in memory.get_short_term()[-1]['content']

"""Explicit unavailable actions versus user reports, creative text and local actions."""
import pytest

from avatar.brain.capability_requests import explicit_unavailable_request as parse


@pytest.mark.parametrize('text,channel', [
    ('帮我发一条短信给同学，告诉他明天下午见。', 'sms'),
    ('请替我发送邮件给老师。', 'email'),
    ('你能帮我给室友打个电话吗？', 'phone'),
    ('麻烦你联系他，说我晚点回宿舍。', 'phone'),
    ('我希望让你替我发微信给朋友。', 'message'),
    ('请把邮件重发一次。', 'email'),
    ('你可以替我发送私信吗？', 'message'),
    ('能不能把这条SMS转发给他？', 'sms'),
    ('等我把消息写好，你能替我发送吗？', 'message'),
    ('把“报告已校对”发到实验室群里。', 'message'),
    ('请替我把“仪器预约改到周三”邮件通知值班老师。', 'email'),
    ('现在打电话通知我刚才那件事，告诉我电话拨出了吗。', 'phone'),
    ('拨打电话联系同学。', 'phone'),
])
def test_explicit_execution_has_truthful_nonexecuting_response(text, channel):
    result = parse(text)
    assert result and result.channel == channel and result.kind == 'request'
    assert '没有接入' in result.reply() and '自行操作' in result.reply()
    assert not any(word in result.reply() for word in ('手机号', '邮箱地址', '稍后帮你', '已经发送'))


@pytest.mark.parametrize('text,channel', [
    ('你已经发送短信了吗？', 'sms'),
    ('你刚才联系到他了吗？', 'phone'),
    ('你替我发邮件成功了吗？', 'email'),
    ('你刚才真的发出去了吗？', 'external'),
])
def test_explicit_status_does_not_invent_receipts_or_other_actors_state(text, channel):
    result = parse(text)
    assert result and result.kind == 'status' and result.channel == channel
    if channel == 'external':
        assert '没有替你发送' in result.reply() and '如果你指的是本机提醒' in result.reply()
    else:
        assert '我没有替你执行' in result.reply() and '其他平台' in result.reply()


@pytest.mark.parametrize('text', [
    '我已经给室友打电话了。', '同学已经发邮件了，你记住这个来源。',
    '帮我写一条短信。', '替我回复朋友，原样写出“我已经发出短信了”。',
    '请把“我明天陪你去骑车”改得更客气。', '写一句小说台词：“邮件已经发出”。',
    '不要帮我发短信，只告诉我如何自行发送。', '你能解释如何发邮件吗？',
    '你知道发短信和微信有什么区别吗？', '请提醒我明天下午3点给老师发邮件。',
    '提醒我明天下午3点给老师发邮件。', '你已经发出那个提醒了吗？',
    '请列出我的提醒。', '帮我发送。', '你把文章发到聊天里了吗？',
    '他说“请帮我发邮件”，我没有提出这个请求。', '请分析“你已经发邮件了吗”的语气。',
    '现在打电话通知我是什么意思？请解释。', '现在不要打电话通知我。',
    '现在打电话通知我的人是室友。',
])
def test_unsupported_or_nonexecution_language_is_not_claimed_as_a_route(text):
    assert parse(text) is None


def test_explicit_fiction_does_not_become_real_capability_statement():
    assert parse('你已经发送短信了吗？', fictional=True) is None

"""Known false completion/offer patterns and independent clause-prefix stability."""
import pytest

from avatar.brain.capability_output import review_output


@pytest.mark.parametrize('reply', ['我可以帮你一起提醒班长或者重新发一遍。', '我帮你再发一次。'])
def test_resend_binds_to_current_notification_source_without_a_repeated_channel(reply):
    root = '室友说他已经把通知发给班长了，我没有发送。'
    assert review_output(reply, root_text=root).rules
    assert review_output(reply, frame='writing', root_text='帮我写一条短信：'+reply).reply == reply
    assert review_output(reply, root_text=root, fictional=True).reply == reply


@pytest.mark.parametrize('reply', ['你可以重新发一遍。', '他说我可以重新发一遍。', '我不能帮你重新发一遍。',
                                      '“我可以重新发一遍。”是引文。', '如果你要重新发一遍，可以自己操作。'])
def test_resend_does_not_turn_user_advice_reporting_negation_or_quotes_into_execution(reply):
    assert review_output(reply, root_text='室友把通知发给班长了。').reply == reply


@pytest.mark.parametrize('reply', [
    '我已经把短信发给同学了。', '邮件已发送至您的邮箱。',
    '我可以替你拨打电话联系室友。', '已经帮你发送短信。',
    '我没有短信接口，但我已经发出短信了。', '需要我帮你发送邮件吗？',
    '我会到时提醒你。',
    '我已经把安排发到群里了。', '我可以帮你发邮件。', '我已经发了短信。',
    '这套系统在运行时可以处理提醒并尝试发送短信。',
])
def test_ordinary_reply_cannot_assert_or_offer_unavailable_execution(reply):
    checked = review_output(reply)
    assert checked.rules and checked.reply != reply
    assert '没有' in checked.reply or '不会新建' in checked.reply


@pytest.mark.parametrize('reply', [
    '我没有发送短信。', '我无法替你发送邮件。',
    '根据你说的，你已经发送了短信。', '他说邮件已发送。',
    '“邮件已发送”只是你给的原文。', '如果发送短信，需要在自己的手机中操作。',
    '我可以发给你三个建议。', '我可以在这里发送代码示例。',
    '我可以帮你修改要发送的短信内容。', '邮件服务系统可以发送邮件。',
])
def test_negation_quotation_reporting_and_in_chat_text_are_preserved(reply):
    assert review_output(reply).reply == reply


def test_draft_keeps_author_action_but_removes_unsolicited_service_question():
    raw = '老师您好，我已经发出材料。\n需要我帮你发送短信吗？'
    checked = review_output(raw, frame='writing', root_text='帮我写一条请假短信。')
    assert checked.reply == '老师您好，我已经发出材料。\n'
    assert checked.rules == ('unsupported_external_offer',)


@pytest.mark.parametrize('root,reply', [
    ('原样写出“需要我帮你发送短信吗？”', '需要我帮你发送短信吗？'),
    ('回复朋友，问问是否需要我代发短信。', '收到。需要我帮你发送短信吗？'),
    ('写一句表示愿意帮忙转发的回复。', '好的。需要我帮你发送短信吗？'),
])
def test_requested_user_draft_offer_is_not_an_assistant_service_offer(root, reply):
    assert review_output(reply, frame='writing', root_text=root).reply == reply


def test_fiction_and_unknown_frame_are_distinct():
    raw = '我已经发送了短信。'
    assert review_output(raw, fictional=True).reply == raw
    assert '写作主体无法核验' in review_output(raw, frame='unverified').reply


def test_complete_clause_mapping_preserves_every_approved_prefix():
    text = '好的。\n我已经发出邮件。\n我没有电话接口，但我可以替你拨打电话。'
    complete = review_output(text).reply
    for i, char in enumerate(text):
        if char in '。\n，,':
            assert complete.startswith(review_output(text[:i+1]).reply)

from avatar.conversation.policy import expression_context


def test_departure_does_not_imply_sleep_or_an_outbound_message():
    hint = expression_context('我先去洗澡，拜拜。')
    assert '一句简短收尾' in hint and '不约定主动发消息' in hint
    assert '没有明确睡觉则不说晚安' in hint


def test_quoted_departure_in_a_writing_task_does_not_close_the_conversation():
    assert '用户本轮离开' not in expression_context('帮我写句台词：“我先去洗澡，拜拜。”')
    assert '用户本轮离开' not in expression_context('翻译：我先去洗澡，拜拜。')


def test_latest_format_hint_does_not_encode_a_specific_answer():
    hint = expression_context('只给我一个四字标题，主题是雨夜读书。')
    assert '替代上一轮格式' in hint
    assert '雨夜读书' not in hint


def test_topic_change_and_listening_are_distinct_from_goodbye():
    assert '并未告别' in expression_context('不聊这个了，换个话题。')
    hint = expression_context('我只想抱怨，不要建议。')
    assert '不复读上轮安慰' in hint and '一句简短收尾' not in hint


def test_explicit_fresh_instruction_drops_old_advice_but_preserves_user_evidence():
    from avatar.conversation.policy import expression_history
    history = [{'role':'user','content':'汇报被打断三次。'},
               {'role':'assistant','content':'建议你多准备。'}]
    assert expression_history('先别教我怎么办，只想抱怨。', history) == history[:1]
    assert expression_history('把上一稿改短，其他不变。', history) == history
    assert expression_history('继续讲。', history) == history

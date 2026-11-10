import pytest
from avatar.brain.facts import rule_facts, supported_fact
from avatar.main import Avatar


@pytest.mark.parametrize('text,expected',[
    ('我朋友喜欢唱歌，而我喜欢摄影。',['喜欢摄影']),
    ('室友喜欢足球，但我喜欢网球。',['喜欢网球']),
    ('我现在不喜欢可乐了，更喜欢豆浆。',['不喜欢可乐','喜欢豆浆']),
    ('她喜欢读书，不过我喜欢散步。',['喜欢散步']),
])
def test_explicit_self_connectives_preserve_original_evidence(text,expected):
    facts=rule_facts(text)
    assert [fact['content'] for fact in facts]==expected
    for fact in facts:
        assert fact['evidence'] in text and supported_fact(text,fact) is not None


@pytest.mark.parametrize('text',[
    '如果我朋友喜欢唱歌，而我喜欢摄影。',
    '我朋友喜欢唱歌，而我喜欢摄影吗？',
    '朋友不喜欢可乐，更喜欢豆浆。',
    '我不喜欢可乐，他更喜欢豆浆。',
    '朋友说“而我喜欢摄影，更喜欢豆浆。”',
])
def test_connectives_cannot_create_other_or_hypothetical_self_preferences(text):
    facts=rule_facts(text)
    assert not any(fact['content'] in ['喜欢摄影','喜欢豆浆'] for fact in facts)


def test_connective_fact_is_durable_across_sessions_and_retains_source(tmp_path):
    class Offline:
        available=False
    path=str(tmp_path/'connective.db')
    first=Avatar(db_path=path,llm=Offline(),session_id='one')
    first.respond('我的室友喜欢唱歌，而我喜欢摄影。')
    assert '摄影' in first.memory.get_user_profile()['偏好']
    first.memory.close()
    second=Avatar(db_path=path,llm=Offline(),session_id='two')
    try:
        assert second.memory.get_user_profile()['偏好']=='喜欢摄影'
        rows=second.memory.list_memories()
        row=next(row for row in rows if '摄影' in row['content'])
        inspected=second.memory.inspect(row['id'])
        assert inspected is not None
        assert '唱歌' not in second.memory.get_user_profile()['偏好']
    finally:second.memory.close()

import pytest
from avatar.brain.facts import rule_facts, supported_fact
from avatar.main import Avatar


@pytest.mark.parametrize('text,expected',[
    ('朋友说“我喜欢游泳”，而我喜欢跑步。',['喜欢跑步']),
    ('朋友说：“我喜欢香菜。”，但我喜欢薄荷。',['喜欢薄荷']),
    ('朋友说“我喜欢游泳”，我喜欢咖啡，但现在不喜欢了。',['不喜欢咖啡']),
    ('朋友问“我喜欢什么？”，不过我喜欢散步。',['喜欢散步']),
])
def test_only_contiguous_explicit_self_suffix_after_closed_quote_is_supported(text,expected):
    facts=rule_facts(text)
    assert [fact['content'] for fact in facts]==expected
    for fact in facts:
        assert fact['evidence'] in text
        assert supported_fact(text,fact) is not None
    quoted={'type':'偏好','content':'喜欢游泳','evidence':'我喜欢游泳',
        'subject':'self','modality':'asserted','temporal':'current'}
    assert supported_fact(text,quoted) is None


@pytest.mark.parametrize('text',[
    '朋友说“我喜欢游泳，而我喜欢跑步。”',
    '如果朋友说“我喜欢游泳”，我喜欢跑步。',
    '朋友说“我喜欢游泳”，我喜欢跑步吗？',
    '朋友说“我喜欢游泳”，他以为我喜欢跑步。',
    '朋友说“我喜欢游泳，而我喜欢跑步。',
    '朋友说“她说‘我喜欢爬山’，我喜欢网球。”',
    '我喜欢咖啡，朋友说“我喜欢游泳”，但现在不喜欢了。',
    '朋友说：我喜欢游泳，但我喜欢跑步。',
    '朋友说“我喜欢游泳”，我朋友喜欢跑步。',
])
def test_quoted_suffix_does_not_relax_outer_scope_or_implicit_subject(text):
    assert rule_facts(text)==[]


def test_quoted_self_suffix_is_stored_with_original_source_across_sessions(tmp_path):
    class Offline:
        available=False
    path=str(tmp_path/'quote.db')
    original='朋友说“我喜欢游泳”，而我喜欢跑步。'
    first=Avatar(db_path=path,llm=Offline(),session_id='one')
    first.respond(original)
    first.memory.close()
    second=Avatar(db_path=path,llm=Offline(),session_id='two')
    try:
        assert second.memory.get_user_profile()['偏好']=='喜欢跑步'
        assert not any('喜欢游泳' in row['content'] for row in second.memory.list_memories())
        message=second.memory._conn.execute("SELECT content FROM memory_messages WHERE role='user'").fetchone()
        assert message[0]==original
    finally:second.memory.close()

import pytest

from avatar.brain.facts import rule_facts, supported_fact


def test_inherited_self_with_explicit_same_object_reverses_current_preference():
    text = '我以前喜欢喝咖啡，现在不喜欢喝咖啡了。'
    facts = rule_facts(text)
    assert [f['content'] for f in facts] == ['不喜欢喝咖啡']
    assert supported_fact(text, facts[0]) is not None


@pytest.mark.parametrize('text', [
    '朋友以前喜欢喝咖啡，现在不喜欢喝咖啡了。',
    '我以前喜欢喝咖啡，朋友说不喜欢，现在不喜欢喝咖啡了。',
    '假如我以前喜欢喝咖啡，现在不喜欢喝咖啡了。',
])
def test_explicit_object_inheritance_cannot_cross_subject_or_hypothesis(text):
    assert rule_facts(text) == []


@pytest.mark.parametrize('text,expected', [
    ('我以前喜欢喝咖啡，现在已经不喜欢了，我讨厌香菜。', {'不喜欢喝咖啡', '讨厌香菜'}),
    ('我喜欢咖啡，但是现在不喜欢了', {'不喜欢咖啡'}),
    ('我以前讨厌香菜，现在喜欢了。', {'喜欢香菜'}),
])
def test_same_sentence_changes_resolve_only_explicit_object(text, expected):
    facts = rule_facts(text)
    assert {fact['content'] for fact in facts} == expected
    assert all(fact['evidence'] in text for fact in facts)


def test_immediate_unique_preference_can_resolve_cross_turn_ellipsis():
    facts = rule_facts('我现在不喜欢了', context=['我喜欢喝咖啡。'])
    assert [fact['content'] for fact in facts] == ['不喜欢喝咖啡']
    assert facts[0]['evidence'] == '我现在不喜欢了'
    assert supported_fact('我现在不喜欢了', facts[0], context=['我喜欢喝咖啡。'])


@pytest.mark.parametrize('context', [[], ['我喜欢咖啡，我喜欢茶。'], ['我喜欢咖啡。', '我刚买了新衣服。']])
def test_ambiguous_or_changed_topic_does_not_resolve_ellipsis(context):
    assert rule_facts('我现在不喜欢了', context=context) == []


@pytest.mark.parametrize('text', [
    '假如我以前喜欢咖啡，现在不喜欢了',
    '朋友说：“我以前喜欢咖啡，现在不喜欢了。”',
    '我以前喜欢咖啡，现在不喜欢了吗？',
    '我朋友以前喜欢咖啡，现在不喜欢了',
])
def test_temporal_resolution_preserves_source_guards(text):
    assert rule_facts(text) == []


def test_reference_candidate_cannot_switch_object_or_polarity():
    fact = dict(type='偏好', content='喜欢香菜', evidence='我现在不喜欢了',
                subject='self', modality='asserted', temporal='current')
    assert supported_fact('我现在不喜欢了', fact, context=['我喜欢咖啡']) is None

@pytest.mark.parametrize('text', [
    '我朋友以前喜欢茶，现在不喜欢了',
    '同事目前喜欢可乐，现在不喜欢了',
    '今天买了新衣服，现在不喜欢了',
    '我喜欢咖啡，我现在喜欢茶，现在不喜欢了',
    '我喜欢咖啡，朋友去买面包，现在不喜欢了',
])
def test_changed_subject_or_topic_cannot_reuse_self_reference(text):
    facts = rule_facts(text, context=['我喜欢咖啡'])
    assert '不喜欢咖啡' not in {f['content'] for f in facts}
    candidate = dict(type='偏好', content='不喜欢咖啡', evidence=text,
                     subject='self', modality='asserted', temporal='current')
    assert supported_fact(text, candidate, context=['我喜欢咖啡']) is None

@pytest.mark.parametrize('text,expected,old,evidence', [
    ('我喜欢咖啡，我现在不再喜欢咖啡', '不喜欢咖啡', '喜欢咖啡', '我喜欢咖啡'),
    ('我不喜欢咖啡，我现在喜欢咖啡', '喜欢咖啡', '不喜欢咖啡', '我不喜欢咖啡'),
    ('我讨厌咖啡，我现在爱咖啡', '爱咖啡', '讨厌咖啡', '我讨厌咖啡'),
    ('我不喜欢咖啡，现在喜欢了', '喜欢咖啡', '不喜欢咖啡', '我不喜欢咖啡'),
    ('我喜欢咖啡。我现在不再喜欢咖啡。', '不喜欢咖啡', '喜欢咖啡', '我喜欢咖啡'),
])
def test_last_same_object_assertion_is_only_current_fact(text, expected, old, evidence):
    assert [f['content'] for f in rule_facts(text)] == [expected]
    candidate = dict(type='偏好', content=old, evidence=evidence,
                     subject='self', modality='asserted', temporal='current')
    assert supported_fact(text, candidate) is None

@pytest.mark.parametrize('text', [
    '我以前喜欢咖啡，朋友说“茶”，现在不喜欢了',
    '我以前喜欢咖啡，“茶”，现在不喜欢了',
    '我以前喜欢咖啡，「我朋友喜欢茶」，现在不喜欢了',
])
def test_quote_mask_never_becomes_evidence_or_reference(text):
    facts = rule_facts(text, context=['我喜欢咖啡'])
    assert all(f['evidence'] in text for f in facts)
    assert not any(f['content'] == '不喜欢咖啡' for f in facts)


def test_safe_sentence_after_quoted_sentence_keeps_literal_evidence():
    text = '朋友说“我喜欢茶”。我喜欢咖啡。'
    facts = rule_facts(text)
    assert [(f['content'], f['evidence']) for f in facts] == [('喜欢咖啡', '我喜欢咖啡')]

@pytest.mark.parametrize('text', [
    '朋友现在喜欢茶。现在不喜欢了',
    '朋友说“茶”。现在不喜欢了',
    '今天买了衣服。我现在不喜欢了',
])
def test_intervening_sentence_invalidates_cross_turn_reference(text):
    assert rule_facts(text, context=['我喜欢咖啡']) == []

@pytest.mark.parametrize('previous', [
    '我喜欢咖啡，朋友喜欢茶',
    '我喜欢咖啡，今天买了新衣服',
    '我喜欢咖啡。朋友说“茶”。',
])
def test_changed_topic_at_end_of_previous_message_cannot_supply_reference(previous):
    assert rule_facts('现在不喜欢了', context=[previous]) == []

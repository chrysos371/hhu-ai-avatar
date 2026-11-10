import pytest
from avatar.lab.checks import check_dialogue_turns


def test_final_answer_success_cannot_hide_intermediate_identity_failure():
    replies = ['真巧，我也喜欢喝花茶呢！', '你喜欢喝花茶。']
    result = check_dialogue_turns(replies, [
        {'none': ['我也喜欢喝花茶']}, {'all': ['你喜欢喝花茶']}])
    assert result['turns'][-1]['all'] is True
    assert result['passed'] is False
    assert result['semantic_approved'] is False


@pytest.mark.parametrize('rules', [[], [{}], [{}, {}, {}]])
def test_incomplete_turn_coverage_is_protocol_error(rules):
    with pytest.raises(ValueError, match='Every reply'):
        check_dialogue_turns(['第一轮', '第二轮'], rules)


def test_unknown_rule_does_not_silently_pass():
    with pytest.raises(ValueError):
        check_dialogue_turns(['答案'], [{'non': ['错误']}])

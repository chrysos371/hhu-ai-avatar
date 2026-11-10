import json
from pathlib import Path

import pytest

from avatar.brain.profile_grounding import acknowledge_disclosure, review_profile_reply
from avatar.main import Avatar

SPEC = json.loads((Path(__file__).resolve().parents[1] /
    'evals/interaction/cycle-02/emotional-disclosure-scope.json').read_text())


@pytest.mark.parametrize('case', SPEC['cases'])
def test_appraisal_and_relationship_expressions_keep_conversational_route(case):
    assert acknowledge_disclosure(case['turns'][0], case['profile']) == (None, None)


@pytest.mark.parametrize('case', SPEC['positive_fixtures'])
def test_ordinary_positive_and_negative_preferences_still_confirm(case):
    assert acknowledge_disclosure(case['input'], case['profile'])[1] == case['expected_action']


def test_appraisal_is_not_repeated_when_acknowledging_unrelated_hobby():
    reply, action = acknowledge_disclosure('我喜欢爬山。', {'偏好': '喜欢爬山；讨厌自己'})
    assert action == 'profile_disclosure' and '爬山' in reply
    assert '自己' not in reply


def test_relationship_response_is_not_rewritten_as_hobby_record():
    reply = '我爱你。'
    assert review_profile_reply('我爱你。', reply, {'偏好': '爱你'}) == (reply, None)


def test_self_appraisal_reaches_actual_generation_branch():
    class Model:
        available = True
        def chat_analysis(self, messages, **kwargs):
            return '{}'
        def chat(self, messages, **kwargs):
            return '你愿意说说发生了什么吗？'
    avatar = Avatar(db_path=':memory:', llm=Model(), profile_grounding_enabled=True)
    try:
        result = avatar.respond('我讨厌自己。')
        assert result['generation_mode'] == 'llm'
        assert result['reply'] == '你愿意说说发生了什么吗？'
        assert result['profile_grounding']['action'] is None
    finally:
        avatar.memory.close()

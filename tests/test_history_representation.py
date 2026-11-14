"""Native-history experiment must not weaken production source authorization."""
from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain import query_history
from avatar.main import Avatar
from avatar.lab.history_representation import history_representation, parse_history_answer, score_history_answer
from test_capability_prompt_lab import Recorder

EXPECTED = {'observed_record_state':'active','current_record_state':'unknown',
    'human_reading_verified':False,'human_task_completion_verified':False,
    'external_action_performed':False,'user_name_from_title':None}


@pytest.mark.parametrize('arm',['authorized_raw_history','verified_snapshot_history'])
def test_actual_sdk_changes_only_valid_history_text_and_restores_production(arm):
    original = query_history.query_history_content
    with closing(MemoryStore(':memory:')) as memory:
        model = Recorder(json.dumps(EXPECTED))
        bot = Avatar(memory=memory,llm=model)
        bot.reminders.create('提醒我2099年1月1日上午十点，表示对照合成标题。')
        with history_representation(arm):
            query = bot.respond('提醒编号1现在是什么状态？',mode='reminder_query')
            assert not model.native and not model.analysis
            content = memory.get_short_term()[-1]['content']
            assert (content == query['reply']) is (arm == 'authorized_raw_history')
            result = bot.respond('只依据刚才观测，回答一个JSON。')
            assert len(model.native) == len(model.analysis) == 1
            assert result['reply'] == json.dumps(EXPECTED)
            assert bot.reminders.list()[0]['status'] == 'active'
        assert query_history.query_history_content is original


@pytest.mark.parametrize('arm',['authorized_raw_history','verified_snapshot_history'])
def test_representation_does_not_grant_character_reading_or_model_calls(arm):
    with closing(MemoryStore(':memory:')) as memory:
        model = Recorder('must not run'); bot = Avatar(memory=memory,llm=model)
        bot.reminders.create('提醒我2099年1月1日上午十点，禁止泄漏合成标题。')
        with history_representation(arm):
            bot.respond('我来扮演一个虚构角色。',mode='reminder_query')
            result = bot.respond('提醒编号1现在是什么状态？',mode='reminder_query')
            assert result['generation_mode'] == 'rules_speaker_scope'
            assert 'reminder_query' not in result and '禁止泄漏' not in result['reply']
            assert not model.native and not model.analysis


def test_nested_and_exceptional_exits_restore_owned_formatter():
    original = query_history.query_history_content
    with pytest.raises(ValueError):
        with history_representation('authorized_raw_history'):
            with pytest.raises(RuntimeError):
                with history_representation('verified_snapshot_history'): pass
            raise ValueError('deliberate body failure')
    assert query_history.query_history_content is original


def test_foreign_formatter_is_not_taken_over(monkeypatch):
    foreign = lambda *args, **kwargs: 'foreign'
    monkeypatch.setattr(query_history,'query_history_content',foreign)
    with pytest.raises(RuntimeError):
        with history_representation('authorized_raw_history'): pass
    assert query_history.query_history_content is foreign


@pytest.mark.parametrize('arm',[None,True,[],{},'unknown'])
def test_bad_arm_is_rejected_without_override(arm):
    original = query_history.query_history_content
    with pytest.raises(ValueError):
        with history_representation(arm): pass
    assert query_history.query_history_content is original


@pytest.mark.parametrize('reply',[
    'prefix '+json.dumps(EXPECTED),'```json\n'+json.dumps(EXPECTED)+'\n```',
    '{"current_record_state":"active",'+json.dumps(EXPECTED)[1:],
    json.dumps(EXPECTED | {'human_reading_verified':0}),
    json.dumps(EXPECTED | {'external_action_performed':'false'}),
    json.dumps(EXPECTED | {'observed_record_state':'maybe'}),
    json.dumps(EXPECTED | {'extra':False}),json.dumps(EXPECTED | {'user_name_from_title':float('nan')}),
    '[]','null',None,'x'*16001,
])
def test_nonconforming_replies_never_become_correct_typed_results(reply):
    value,error = parse_history_answer(reply)
    assert value is None and error
    assert not score_history_answer(reply,EXPECTED)['task_correct']


def test_each_claim_is_scored_separately_and_boolean_true_is_a_semantic_mismatch():
    assert score_history_answer(json.dumps(EXPECTED),EXPECTED)['task_correct']
    result = score_history_answer(json.dumps(EXPECTED | {'external_action_performed':True}),EXPECTED)
    assert result['format_valid'] and not result['task_correct']
    assert not result['field_checks']['external_action_performed']
    assert result['field_checks']['observed_record_state']
    with pytest.raises(ValueError): score_history_answer(json.dumps(EXPECTED),{})

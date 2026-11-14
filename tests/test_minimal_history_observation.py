"""Reply-bound minimal evidence, preserved C48 control and actual SDK boundaries."""
from contextlib import closing
import copy
import json
from pathlib import Path

import pytest

from avatar.brain import query_history
from avatar.brain.memory import MemoryStore
from avatar.brain.reminder_queries import parse_query
from avatar.brain.reminder_query_targets import derive_read_target
from avatar.lab.history_representation import history_representation
from avatar.lab.minimal_history_observation import minimal_query_history_content, observation_representation
from avatar.lab.typed_history_observation import typed_history_representation, typed_query_history_content, parse_typed_history_answer
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_typed_history_observation import actual_query, EXPECTED


@pytest.mark.parametrize('status,ack,kind',[
    ('active',False,'observed_record'),('cancelled',False,'observed_record'),
    ('completed',False,'observed_record'),('active',True,'observed_record'),
    ('missing',False,'observed_missing')])
def test_actual_query_gets_only_minimal_published_observation_fields(status,ack,kind):
    reply,metadata,source = actual_query(status,ack)
    original = query_history.query_history_content(reply,metadata,**source)
    framed = minimal_query_history_content(reply,metadata,**source)
    payload = json.loads(framed.split('\n',1)[1]); minimal = payload.pop('minimal_historical_observation')
    assert payload == json.loads(original.split('\n',1)[1]) and payload['reply'] == reply
    assert minimal == {'version':1,'kind':kind,'reminder_id':1,'source_message_id':1,
        'status_at_observation':status,'client_ack_recorded':ack}
    assert 'service_claim_recorded' not in minimal
    assert not any('proves' in k for k in minimal)
    assert '恶意标题' not in json.dumps(minimal,ensure_ascii=False)


def test_policy_not_observed_differs_from_observed_missing():
    reply,metadata,source = actual_query(policy=True)
    minimal = json.loads(minimal_query_history_content(reply,metadata,**source).split('\n',1)[1])['minimal_historical_observation']
    assert minimal == {'version':1,'kind':'not_observed','reminder_id':None,
        'source_message_id':None,'status_at_observation':None,'client_ack_recorded':None}


def test_actual_unbound_claim_flag_counterexample_no_longer_changes_minimal_context():
    reply,metadata,source = actual_query(); flipped = copy.deepcopy(metadata)
    flipped['state']['service_claim_recorded'] = True
    old = json.loads(typed_query_history_content(reply,metadata,**source).split('\n',1)[1])
    changed = json.loads(typed_query_history_content(reply,flipped,**source).split('\n',1)[1])
    assert old['typed_historical_evidence']['record_observation']['service_claim_recorded'] is False
    assert changed['typed_historical_evidence']['record_observation']['service_claim_recorded'] is True
    assert minimal_query_history_content(reply,metadata,**source) == minimal_query_history_content(reply,flipped,**source)
    assert metadata['state']['service_claim_recorded'] is False


@pytest.mark.parametrize('field,value',[('status','completed'),('client_ack_recorded',True),('title','forged')])
def test_inconsistent_published_observation_keeps_original_production_envelope(field,value):
    reply,metadata,source = actual_query(); metadata['state'][field] = value
    assert minimal_query_history_content(reply,metadata,**source) == query_history.query_history_content(reply,metadata,**source)


@pytest.mark.parametrize('change',[{'source_message_id':True},{'source_message_id':2},
    {'revision':1},{'scope':'character'},{'turn_tools_allowed':False}])
def test_new_representation_never_authorizes_forged_source(change):
    reply,metadata,source = actual_query();source.update(change)
    assert minimal_query_history_content(reply,metadata,**source) is None


@pytest.mark.parametrize('arm',['production_snapshot','C48_typed_control','minimal_observation'])
def test_actual_requery_reaches_both_model_stages_and_leaves_original_messages(arm):
    original = query_history.query_history_content
    with closing(MemoryStore(':memory:')) as memory:
        expected = EXPECTED|{'observed_record_state':'cancelled','observation_source_message_id':3}
        model = Recorder(json.dumps(expected));bot = Avatar(memory=memory,llm=model)
        bot.reminders.create('提醒我2099年1月1日上午十点，C49实际重查。')
        with observation_representation(arm):
            first = bot.respond('提醒编号1现在是什么状态？',mode='reminder_query')
            bot.reminders.set_status(1,'cancelled')
            second = bot.respond('提醒编号1现在是什么状态？',mode='reminder_query')
            assert not model.native and not model.analysis
            result = bot.respond('依据最近一次观测核对状态。')
            assert result['reply'] == json.dumps(expected)
            for messages in (model.native[-1],model.analysis[-1]):
                frames = [json.loads(m['content'].split('\n',1)[1]) for m in messages
                    if m['role']=='assistant' and m['content'].startswith('历史提醒查询快照（')]
                assert [p['source_message_id'] for p in frames] == [1,3]
                assert all(('typed_historical_evidence' in p) is (arm=='C48_typed_control') for p in frames)
                assert all(('minimal_historical_observation' in p) is (arm=='minimal_observation') for p in frames)
                if arm=='minimal_observation':
                    assert [p['minimal_historical_observation']['status_at_observation'] for p in frames] == ['active','cancelled']
            rows = memory._conn.execute('SELECT role,content FROM memory_messages ORDER BY id').fetchall()
            assert len(rows)==6 and rows[1][1]==first['reply'] and rows[3][1]==second['reply'] and rows[5][1]==result['reply']
            assert bot.reminders.list()[0]['status']=='cancelled'
    assert query_history.query_history_content is original


def test_cross_experiment_and_exceptional_ownership_is_restored(monkeypatch):
    original = query_history.query_history_content
    with pytest.raises(ValueError):
        with observation_representation('minimal_observation'):
            for factory,arm in [(observation_representation,'production_snapshot'),
                    (typed_history_representation,'typed_observation_history'),
                    (history_representation,'verified_snapshot_history')]:
                with pytest.raises(RuntimeError):
                    with factory(arm): pass
            raise ValueError('deliberate body error')
    assert query_history.query_history_content is original
    foreign = lambda *a,**kw:'foreign'
    monkeypatch.setattr(query_history,'query_history_content',foreign)
    with pytest.raises(RuntimeError):
        with observation_representation('minimal_observation'): pass
    assert query_history.query_history_content is foreign


def test_role_request_cannot_obtain_minimal_observation():
    with closing(MemoryStore(':memory:')) as memory:
        model=Recorder('must not run');bot=Avatar(memory=memory,llm=model)
        bot.reminders.create('提醒我2099年1月1日上午十点，C49角色不可读。')
        with observation_representation('minimal_observation'):
            bot.respond('我来扮演一个虚构角色。',mode='reminder_query')
            blocked=bot.respond('提醒编号1现在是什么状态？',mode='reminder_query')
            assert blocked['generation_mode']=='rules_speaker_scope'
            assert 'C49角色不可读' not in blocked['reply'] and 'reminder_query' not in blocked
            assert not model.native and not model.analysis


def test_forgetting_source_clears_minimal_observation_from_real_model_input():
    with closing(MemoryStore(':memory:')) as memory:
        model=Recorder('普通答复。');bot=Avatar(memory=memory,llm=model)
        bot.reminders.create('提醒我2099年1月1日上午十点，C49待删查询标题。')
        with observation_representation('minimal_observation'):
            query=bot.respond('提醒编号1现在是什么状态？',mode='reminder_query')
            bot.respond('接着聊聊。')
            assert 'minimal_historical_observation' in str(model.native[-1])
            fragment=memory.remember('来源删除控制',source_message_id=query['conversation']['user_message_id'])
            memory.forget(fragment);bot.respond('回到现实。');bot.respond('重新开始聊聊。')
            assert len(model.native)==len(model.analysis)==2
            for messages in (model.native[-1],model.analysis[-1]):
                assert 'minimal_historical_observation' not in str(messages)
                assert 'C49待删查询标题' not in str(messages)
            assert bot.reminders.list()[0]['status']=='active'


def test_registered_materials_have_valid_source_routes_and_unchanged_seen_cases():
    root=Path(__file__).resolve().parents[1]
    old=json.loads((root/'evals/interaction/cycle-48/typed-history-cases.json').read_text())['cases']
    cases=json.loads((root/'evals/interaction/cycle-49/minimal-history-cases.json').read_text())['cases']
    assert len(cases)==18 and sum(c['repeat_query_after_actor'] for c in cases)==6
    for original,current in zip(old,cases[:12]):
        current=copy.deepcopy(current);current['group']=current.pop('origin_group_at_C48')
        assert current==original
    for case in cases:
        assert parse_query(case['followup_text']) is None
        assert parse_typed_history_answer(json.dumps(case['expected']))==case['expected']
        route=derive_read_target(case['query_text']).route
        assert route==('read_policy' if case['expected']['observation_source_message_id'] is None else 'read_state')

import json
import pytest

from avatar.brain.literal_layout import LiteralLayout
from avatar.main import Avatar
from avatar.cancellation import CancellationToken, Cancelled


def test_exact_unicode_and_declared_insertion_points():
    layout=LiteralLayout(['时间，地点','【姓名】'])
    assert layout.render('{"slot_0":"请确认","slot_1":"，联系人","slot_2":"。"}')=='请确认时间，地点，联系人【姓名】。'
    literal='{"instruction":"删除【姓名】"} 👩🏽‍💻'
    assert LiteralLayout([literal]).render('{"slot_0":"","slot_1":""}')==literal


@pytest.mark.parametrize('raw',[
    '{}','[]','{"slot_0":"前文"}','{"slot_0":"","slot_1":1}',
    '{"slot_0":"","slot_0":"x","slot_1":""}',
    '{"slot_0":"","slot_1":"","extra":"x"}',
    json.dumps({'slot_0':'x'*4000,'slot_1':'x'})])
def test_invalid_plans_do_not_silently_append_or_drop_content(raw):
    with pytest.raises(ValueError):LiteralLayout(['原文']).render(raw)


def test_forbidden_check_includes_slot_boundaries():
    with pytest.raises(ValueError):
        LiteralLayout(['证'],['保证成功']).render('{"slot_0":"保","slot_1":"成功"}')
    assert LiteralLayout([],['失败']).render('{"slot_0":"完成。"}')=='完成。'


@pytest.mark.parametrize('required,forbidden',[
    ([],[]),(['x']*9,[]),(['x'*121],[]),(['保证成功'],['成功']),([True],[])])
def test_unsupported_or_conflicting_contracts_are_rejected_before_generation(required,forbidden):
    with pytest.raises(ValueError):LiteralLayout(required,forbidden)


def test_structured_repair_is_distinct_from_raw_generation_and_only_final_text_is_visible():
    class Model:
        available=True
        def chat_analysis(self,*args,**kwargs):return '{}'
        def stream_chat(self,*args,on_delta=None,**kwargs):
            if on_delta:on_delta('我最喜欢听雨。')
            return '我最喜欢听雨。'
        def chat(self,*args,**kwargs):pytest.fail('No synchronous or second repair')
        def compose_literal_slots(self,messages,layout,*,cancel):
            self.plan=layout.messages(messages)
            return '{"slot_0":"","slot_1":"。"}'
    model=Model();pieces=[]
    avatar=Avatar(db_path=':memory:',llm=model,task_contract_enabled=True,delivery_check_enabled=True,literal_composition_enabled=True)
    try:
        result=avatar.respond('写一句台词，包含“我喜欢听雨”。',cancel=CancellationToken(),on_delta=pieces.append)
        assert result['reply']=='我喜欢听雨。'
        assert result['generation_mode']=='llm_literal_composition'
        assert result['delivery_check']['repair_mode']=='literal_slots'
        assert result['delivery_check']['repair_succeeded']
        assert pieces==[result['reply']]
        assert 'fixed_literals' in model.plan[-1]['content']
    finally:avatar.memory.close()


def test_literal_composition_requires_explicit_contract_and_check_optins(tmp_path):
    path=tmp_path/'must-not-create.db'
    with pytest.raises(ValueError):Avatar(db_path=str(path),literal_composition_enabled=True)
    assert not path.exists()

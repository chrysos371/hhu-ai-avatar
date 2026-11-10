import json
import pytest
from avatar.brain.literal_layout import LiteralTemplate
from avatar.main import Avatar
from avatar.cancellation import CancellationToken


def test_source_only_plan_omits_bad_draft_profile_and_assistant_guesses():
    plan=LiteralTemplate(['时间，地点'],source='写消息，保留“时间，地点”。')
    messages=plan.messages([{'role':'assistant','content':'今晚七点，市中心咖啡馆。'}, {'role':'user','content':'请修正'}])
    payload=json.loads(messages[-1]['content'])
    assert 'task_source' in payload
    assert all('市中心咖啡馆' not in row['content'] for row in messages)
    assert all('今晚七点' not in row['content'] for row in messages)


def test_single_pass_preserves_marker_text_inside_protected_literal():
    plan=LiteralTemplate(['{{L1}}','尾文'],source='写一句话。')
    assert plan.render('{"text":"{{L0}}/{{L1}}"}')=='{{L1}}/尾文'


@pytest.mark.parametrize('text',['没有标记','{{L0}}{{L0}}','{{L1}}','{{L0}}原文','原文{{L0}}','{{L00}}'])
def test_missing_unknown_duplicated_or_repeated_literal_is_rejected(text):
    with pytest.raises(ValueError):
        LiteralTemplate(['原文'],source='写句话。').render(json.dumps({'text':text}))


def test_forbidden_check_covers_boundaries_after_substitution():
    with pytest.raises(ValueError):
        LiteralTemplate(['证'],['保证成功'],source='写句话。').render('{"text":"保{{L0}}成功"}')


def test_valid_template_builds_fluent_surroundings_without_forcing_literal_order():
    plan=LiteralTemplate(['时间','地点'],source='给老师写消息。',recipient='老师')
    assert plan.render('{"text":"老师您好，想请您确认{{L0}}和{{L1}}。"}')=='老师您好，想请您确认时间和地点。'
    assert plan.render('{"text":"想确认{{L1}}与{{L0}}。"}')=='想确认地点与时间。'


def test_full_pipeline_marks_source_only_template_and_emits_only_rendered_text():
    class Model:
        available=True
        def chat_analysis(self,*args,**kwargs):return '{}'
        def chat(self,*args,**kwargs):return '今晚七点，市中心咖啡馆。'
        def stream_chat(self,*args,**kwargs):return self.chat()
        def compose_literal_plan(self,messages,layout,**kwargs):
            self.source=layout.messages(messages)
            return '{"text":"请确认{{L0}}。"}'
    model=Model();pieces=[]
    avatar=Avatar(db_path=':memory:',llm=model,task_contract_enabled=True,delivery_check_enabled=True,literal_composition_enabled=True)
    try:
        result=avatar.respond('写一条消息，原样保留“时间，地点”。',cancel=CancellationToken(),on_delta=pieces.append)
        assert result['reply']=='请确认时间，地点。'
        assert result['delivery_check']['repair_mode']=='literal_template'
        assert result['generation_mode']=='llm_literal_composition'
        assert pieces==[result['reply']]
        assert all('今晚七点' not in message['content'] for message in model.source)
    finally:avatar.memory.close()

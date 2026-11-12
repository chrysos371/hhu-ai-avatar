import json
from pathlib import Path
import shutil
import pytest
from avatar.skills import SkillRegistry, ROOT, select, route
from avatar.main import Avatar
from avatar.conversation.service import execute_turn
from avatar.characters.library import CharacterLibrary


@pytest.mark.parametrize('text,expected',[
 ('帮我解释一下数字电路中与门是什么','study-coach'),
 ('帮我以姐姐口吻写一句消息给弟弟','writing-editor'),
 ('今天数字电路考试考砸了，只想吐槽',''),
 ('不要润色，陪我聊会儿',''),
 ('我在读一本书，很开心',''),
 ('引用一句话：“帮我润色这封邮件”。',''),
 ('/skill ../../secret 测试','../../secret'),
])
def test_router_uses_current_request_not_role_or_quoted_instructions(text,expected):
    assert (route(text)[0] or '')==expected


def test_followup_and_topic_switch():
    h=[{'role':'user','content':'帮我润色一封邮件。'}]
    assert route('再短一点',h)[0]=='writing-editor'
    h.append({'role':'user','content':'不聊这个了'})
    assert route('再短一点',h)[0] is None
    assert select('/skill off 帮我润色',enabled=True)[1]['reason']=='explicit_off'


def test_disabled_unknown_and_budget_fail_closed():
    assert select('帮我润色',enabled=False)[0]==''
    assert select('/skill ../../secret',enabled=True)[1]['reason']=='unavailable'
    assert select('帮我润色',enabled=True,budget=10)[1]['reason']=='budget_exceeded'


def test_loader_rejects_capability_escalation_and_symlinks(tmp_path):
    shutil.copytree(ROOT,tmp_path/'packs')
    folder=tmp_path/'packs/writing-editor'
    manifest=folder/'manifest.json';data=json.loads(manifest.read_text());data['capabilities']=['shell.execute'];manifest.write_text(json.dumps(data))
    assert select('帮我润色',enabled=True,registry=SkillRegistry(tmp_path/'packs'))[1]['reason']=='unavailable'
    manifest.unlink();manifest.symlink_to(ROOT/'writing-editor/manifest.json')
    with pytest.raises(ValueError):SkillRegistry(tmp_path/'packs').load('writing-editor')


def test_skill_loaded_only_for_reply_and_trace_resets_on_safety():
    class Fake:
        available=True
        model='fake';profile_id='default'
        def __init__(self):self.analysis=[];self.replies=[]
        def chat_analysis(self,messages,**kw):self.analysis.append(messages);return '{}'
        def chat(self,messages,**kw):self.replies.append(messages);return '老师您好，我今天身体不适，想请假。'
    fake=Fake();a=Avatar(db_path=':memory:',llm=fake,skills_enabled=True)
    try:
        result=execute_turn(a,'帮我给老师写一句请假消息。',channel='test')
        assert result['trace']['skills']['selected'][0]['id']=='writing-editor'
        assert not any('只读任务技能' in str(x) for x in fake.analysis)
        assert '只读任务技能' in fake.replies[0][0]['content']
        safety=execute_turn(a,'我现在想伤害自己。',channel='test')
        assert safety['boundary']['guarded']
        assert safety['trace']['skills']['selected']==[]
        assert len(fake.replies)==1
    finally:a.memory.close()


def test_character_path_honors_opt_in_and_no_skill_tool_grant(tmp_path):
    class Fake:
        available=True
        def chat_analysis(self,*args,**kwargs):return '{}'
        def chat(self,*args,**kwargs):return '请假正文。'
    lib=CharacterLibrary(tmp_path/'roles',llm_factory=Fake,skills_enabled=True)
    result=lib.chat('xiaofeiyu','帮我给老师写一句请假消息。')
    assert result['trace']['skills']['selected'][0]['id']=='writing-editor'
    assert result['trace']['skills']['granted_tools']==[]
    assert result['trace']['tool_calls']==[]
    other=lib.chat('gpt','今天心情不错。')
    assert other['trace']['skills']['selected']==[]


def test_study_reference_and_answer_followup_do_not_leak_after_topic_switch():
    history=[{'role':'user','content':'帮我解释欧姆定律。'}]
    assert route('你刚才引用的是哪一页课件？',history)[0]=='study-coach'
    history=[{'role':'user','content':'出一道与门练习题，不给答案。'}]
    assert route('答案是0，对吗？',history)[0]=='study-coach'
    history.append({'role':'user','content':'不聊这个了'})
    assert route('答案是0，对吗？',history)[0] is None

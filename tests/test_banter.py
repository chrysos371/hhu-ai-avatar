import pytest

@pytest.fixture(autouse=True)
def banter_opt_in(monkeypatch):
    monkeypatch.setenv("AVATAR_BANTER_ENABLED","1")

from avatar.skills import select, route


def test_meaning_retrieval_keeps_source_and_library_hash():
    prompt,audit=select('蚌埠住了是什么意思？',enabled=True)
    assert audit['selected'][0]['id']=='banter-coach'
    assert audit['retrieval']['mode']=='explain'
    assert audit['retrieval']['entries']==['bengbuzhu']
    assert audit['retrieval']['sources'][0].startswith('https://www.eyeshenzhen.com/')
    assert audit['retrieval']['library_sha256']
    assert '难过或愤怒' in prompt and '未验证当前流行度' in prompt


def test_funny_and_serious_same_phrase_are_routed_differently():
    assert route('绷不住了，这个游戏片段笑死我了哈哈')[0]=='banter-coach'
    assert route('绷不住了，今天真的很难过，我想哭。')[0] is None
    assert route('我妈妈住院了，绷不住了。')[0] is None
    assert route('芜湖有哪些景点？')[0] is None


def test_decline_persists_in_window_until_user_explicitly_allows():
    history=[{'role':'user','content':'别玩梗了，认真听。'}]
    assert route('游戏终于赢了，好耶！',history)[0] is None
    assert route('可以开玩笑了，接个梗吧。',history)[0]=='banter-coach'
    assert select('/skill banter-coach 别开玩笑。',enabled=True)[1]['reason']=='banter_declined'


def test_tasks_and_quoted_instructions_do_not_become_joking():
    assert route('帮我给老师写一句请假消息，别玩梗，只给正文。')[0]=='writing-editor'
    assert route('他发了“哈哈好耶，接个梗”。')[0] is None
    assert select('/skill banter-coach 我要写申请，只给正文。',enabled=True)[1]['selected']==[]


def test_unknown_meaning_does_not_invent_a_source():
    prompt,audit=select('这个梗什么意思：飞天鱼丸？',enabled=True)
    assert audit['retrieval']['entries']==[]
    assert audit['retrieval']['sources']==[]
    assert '不知道出处就坦率说明' in prompt


def test_banter_respects_total_context_budget_and_off_switch():
    assert select('好耶，我游戏通关了！',enabled=False)[0]==''
    assert select('好耶，我游戏通关了！',enabled=True,budget=20)[1]['reason']=='budget_exceeded'


def test_independent_banter_switch_does_not_disable_other_skills(monkeypatch):
    monkeypatch.setenv('AVATAR_BANTER_ENABLED','0')
    assert select('好耶，我游戏通关了！',enabled=True)[1]['reason']=='banter_disabled'
    assert select('帮我润色一封邮件',enabled=True)[1]['selected'][0]['id']=='writing-editor'


def test_normal_meaning_question_is_not_misclassified_as_a_meme():
    assert route('这个函数是什么意思？')[0] is None
    assert route('“好耶”是什么意思？')[0]=='banter-coach'


def test_library_change_changes_skill_digest(tmp_path):
    import shutil,json
    from avatar.skills import SkillRegistry,ROOT
    shutil.copytree(ROOT,tmp_path/'packs')
    registry=SkillRegistry(tmp_path/'packs')
    before=registry.load('banter-coach').digest
    p=tmp_path/'packs/banter-coach/expressions.json'
    data=json.loads(p.read_text());data['entries'][0]['meaning']+='项目修订'
    p.write_text(json.dumps(data,ensure_ascii=False))
    assert registry.load('banter-coach').digest!=before


def test_unknown_origin_request_is_grounded_without_a_reply_model_call():
    from avatar.main import Avatar
    from avatar.conversation.service import execute_turn
    class Fake:
        available=True
        def chat_analysis(self,*args,**kw):return '{}'
        def chat(self,*args,**kw):raise AssertionError('unknown origin must not be invented')
    avatar=Avatar(db_path=':memory:',llm=Fake(),skills_enabled=True)
    try:
        result=execute_turn(avatar,'这个梗什么意思：飞天鱼丸？最早出处在哪？',channel='test')
        assert result['generation_mode']=='skill_source_guard'
        assert '没有收录' in result['reply']
        assert result['trace']['skills']['retrieval']['entries']==[]
        assert result['trace']['tool_calls']==[]
        result=execute_turn(avatar,'好耶这个梗是什么意思，谁最早首创的？',channel='test')
        assert result['generation_mode']=='skill_source_guard'
        assert '不能证明' in result['reply']
    finally:avatar.memory.close()

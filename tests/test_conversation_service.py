import json
from types import SimpleNamespace
import pytest
from avatar.characters.library import CharacterLibrary
from avatar.characters.api import handle
from avatar.conversation.shared_memory import SharedFacts
from avatar.conversation.models import ModelProfile
from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.brain.admin_store import AdminStore, initial_persona

@pytest.fixture
def setup(tmp_path):
    path=tmp_path/'admin.db'
    with_memory=MemoryStore(str(path));AdminStore(with_memory).migrate(initial_persona());with_memory.close()
    calls=[]
    class Fake:
        available=True
        model='fake-visible'
        profile_id='test'
        def chat_analysis(self,*args,**kwargs):return '{}'
        def chat(self,messages,**kwargs):
            calls.append(messages)
            return '你喜欢荔枝。' if '荔枝' in messages[0]['content'] else '普通回复'
    lib=CharacterLibrary(tmp_path/'characters',management_db=path,llm_factory=Fake)
    server=SimpleNamespace(character_root=lib.root,db_path=str(path),character_llm_factory=Fake)
    return lib,calls,server


def test_shared_fact_grants_revoke_and_undo_do_not_cross_owner(tmp_path):
    facts=SharedFacts(tmp_path/'shared.db')
    fid=facts.update('owner-a',key='diet',value='不吃花生',characters=['gpt'])
    assert facts.visible('owner-a','gpt')[0]['value']=='不吃花生'
    assert facts.visible('owner-a','deepseek')==facts.visible('owner-b','gpt')==[]
    with pytest.raises(ValueError):facts.update('owner-b',fact_id=fid,revoke=True)
    with pytest.raises(ValueError):facts.undo('owner-b',fid)
    facts.update('owner-a',fact_id=fid,key='diet',value='不吃海鲜',characters=['deepseek'])
    assert facts.visible('owner-a','gpt')==[]
    facts.undo('owner-a',fid)
    assert facts.visible('owner-a','gpt')[0]['value']=='不吃花生'
    facts.update('owner-a',fact_id=fid,revoke=True)
    assert facts.visible('owner-a','gpt')==[]
    facts.undo('owner-a',fid)
    assert facts.visible('owner-a','gpt')[0]['value']=='不吃花生'
    assert facts.revision('owner-a')==5


def test_revoke_removes_prior_assistant_context_but_keeps_history(setup):
    lib,calls,_=setup
    fid=lib.shared_facts().update('local-owner',key='preference',value='喜欢荔枝',characters=['gpt'])
    result=lib.chat('gpt','你好')
    assert '荔枝' in calls[-1][0]['content']
    assert result['trace']['shared_fact_ids']==[fid]
    lib.chat('deepseek','你好')
    assert '荔枝' not in json.dumps(calls[-1],ensure_ascii=False)
    lib.shared_facts().update('local-owner',fact_id=fid,revoke=True)
    lib.chat('gpt','继续聊聊')
    assert '荔枝' not in json.dumps(calls[-1],ensure_ascii=False)
    assert any('荔枝' in r['content'] for r in lib.history('gpt'))
    trace=lib.traces('gpt')[0]
    assert trace['shared_fact_ids']==[]
    assert trace['model']=='fake-visible' and trace['channel']=='web-character'
    assert trace['character_id']=='gpt' and trace['schema_version']==1


def test_model_selection_changes_neither_persona_nor_memories(setup,monkeypatch,tmp_path):
    lib,_,server=setup
    lib.chat('gpt','我叫小晴')
    persona=lib.config_path('gpt').read_bytes()
    history=lib.history('gpt')
    path=tmp_path/'profiles.json';path.write_text(json.dumps([{'id':'candidate','model':'trial-14b','base_url':'http://127.0.0.1:18090/v1','api_key_env':'PRIVATE_KEY','structured_analysis':'none','tools':False}]))
    monkeypatch.setenv('AVATAR_MODEL_PROFILES',str(path));monkeypatch.setenv('PRIVATE_KEY','secret-value')
    status,result=handle(server,True,'/characters/gpt/model',{}, {'profile_id':'candidate'})
    assert status==200 and result['model']=='trial-14b'
    assert lib.model_profile('deepseek').id=='default'
    assert lib.config_path('gpt').read_bytes()==persona
    assert lib.history('gpt')==history
    assert 'secret-value' not in json.dumps(handle(server,False,'/characters/models',{},{}))


def test_profile_controls_protocol_without_replaying_requests(monkeypatch):
    monkeypatch.setenv('TEST_LOCAL_KEY','test-key')
    profile=ModelProfile('test','test-model','http://127.0.0.1:18090/v1',api_key_env='TEST_LOCAL_KEY',structured_analysis='none',tools=False,thinking=False)
    model=LLMEngine(profile=profile);requests=[]
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='<think>private reasoning</think>可见回复'))])
    model._client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    with pytest.raises(ValueError):model.chat_analysis([])
    with pytest.raises(ValueError):model.chat_tools([],tools=[{'type':'function'}])
    assert not requests
    assert model.chat([])=='可见回复'
    assert requests[0]['extra_body']['chat_template_kwargs']['enable_thinking'] is False
    assert len(requests)==1
    assert model.protocol_fallbacks==['structured_analysis_unsupported','native_tools_unsupported']


def test_shared_fact_api_strict_permissions_and_undo(setup):
    lib,_,server=setup
    def api(post,path,data):return handle(server,post,path,{},data)
    from avatar.brain.operations import OperationError
    for data in [{'key':'relationship','value':'永久爱我','characters':['gpt']},
                 {'key':'diet','value':'花生','characters':['unknown']},
                 {'key':'diet','value':'花生','characters':['gpt'],'owner':'another'}]:
        with pytest.raises(OperationError):api(True,'/characters/shared-facts',data)
    _,result=api(True,'/characters/shared-facts',{'key':'diet','value':'不吃花生','characters':[]})
    assert lib.shared_facts().visible('local-owner','gpt')==[]
    api(True,'/characters/shared-facts/undo',{'fact_id':result['fact_id']})
    assert api(False,'/characters/shared-facts',{})[1]['facts']==[]


def test_selected_profile_is_used_on_next_turn_and_keeps_local_facts(setup,monkeypatch,tmp_path):
    lib,calls,_=setup
    from avatar.conversation import models
    selected=[]
    class Fake:
        available=True
        def __init__(self,profile_id):self.model=profile_id;self.profile_id=profile_id
        def chat_analysis(self,*args,**kwargs):return '{}'
        def chat(self,messages,**kwargs):calls.append(messages);return '测试回复'
    def factory(profile_id):selected.append(profile_id);return Fake(profile_id)
    monkeypatch.setattr(models,'create_llm',factory)
    lib.llm_factory=None
    path=tmp_path/'models.json';path.write_text(json.dumps([{'id':'new-base','model':'other-model','base_url':'http://127.0.0.1:18090/v1'}]))
    monkeypatch.setenv('AVATAR_MODEL_PROFILES',str(path))
    lib.chat('gpt','我叫小晴')
    lib.select_model('gpt','new-base')
    result=lib.chat('gpt','我叫什么？')
    assert selected==['default','new-base']
    assert '小晴' in calls[-1][0]['content']
    assert result['trace']['model_profile']=='new-base'
    assert len(lib.history('gpt'))==4


def test_common_web_trace_is_persisted_without_prompts_or_secrets(tmp_path):
    from avatar.main import Avatar
    from avatar.conversation.service import execute_turn
    class Fake:
        available=True;model='test-model';api_key='private-secret'
        def chat_analysis(self,*args,**kwargs):raise ValueError('private failure text')
        def chat(self,*args,**kwargs):return '收到'
    avatar=Avatar(db_path=str(tmp_path/'web.db'),llm=Fake(),session_id='local-web')
    try:
        result=execute_turn(avatar,'你好',channel='web')
        trace=result['trace']
        assert trace['analysis_status']=='rule_fallback' and trace['reply_degraded'] is False
        saved=avatar.memory._conn.execute('SELECT data FROM conversation_turn_traces').fetchone()[0]
        assert json.loads(saved)==trace
        assert 'private-secret' not in saved and 'private failure text' not in saved and '你好' not in saved
    finally:avatar.memory.close()

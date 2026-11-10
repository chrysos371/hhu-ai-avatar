import json
from types import SimpleNamespace
import pytest
from avatar.characters.library import CharacterLibrary, CARDS
from avatar.characters.api import handle
from avatar.brain.memory import MemoryStore
from avatar.brain.admin_store import AdminStore, initial_persona
from avatar.brain.operations import OperationError


@pytest.fixture
def library(tmp_path):
    admin=tmp_path/'global.db'
    memory=MemoryStore(str(admin));store=AdminStore(memory);store.migrate(initial_persona());memory.remember('管理员私人秘密');memory.close()
    prompts=[]
    class Fake:
        available=True
        def chat_analysis(self,*args,**kwargs):return '{}'
        def chat(self,messages,**kwargs):prompts.append(messages);return '角色回复。'
    lib=CharacterLibrary(tmp_path/'characters',management_db=admin,llm_factory=Fake)
    return lib,prompts,Fake


def test_catalog_has_distinct_cards_and_actual_backend(library):
    lib,_,_=library
    rows=lib.catalog()
    assert len(rows)==14 and len({c['id'] for c in rows})==14
    assert len({c['persona']['core_identity'] for c in CARDS})==14
    assert all('backend_model' in c for c in rows)
    assert not (lib.root/'roles').exists()


def test_role_memories_and_personas_are_isolated_and_restore(library):
    lib,prompts,_=library
    lib.chat('deepseek','我叫小林')
    assert '鲸鱼娘' in prompts[-1][0]['content']
    lib.chat('gpt','你知道我叫什么吗？')
    assert '小林' not in json.dumps(prompts[-1],ensure_ascii=False)
    assert '白龙娘' in prompts[-1][0]['content']
    assert '管理员私人秘密' not in json.dumps(prompts[-1],ensure_ascii=False)
    lib.chat('deepseek','我叫什么？')
    assert '小林' in prompts[-1][0]['content']
    assert len(lib.history('deepseek'))==4 and len(lib.history('gpt'))==2
    assert lib.history('gemini')==[]


def test_role_persona_requires_confirmation_and_does_not_change_others(library):
    lib,prompts,factory=library
    server=SimpleNamespace(character_root=lib.root,db_path=str(lib.management_db),character_llm_factory=factory)
    def api(key,post,route,data=None):
        return handle(server,post,'/characters/'+key+route,{},data or {})[1]
    old=api('deepseek',False,'/config/persona')
    draft=api('deepseek',True,'/config/persona/draft',{'changes':{'name':'澄澄'}})
    assert api('deepseek',False,'/config/persona')==old
    with pytest.raises(OperationError):
        api('deepseek',True,f"/config/operations/{draft['draft_id']}/confirm",{'confirmation_token':'incorrect-token-value'})
    api('deepseek',True,f"/config/operations/{draft['draft_id']}/confirm",{'confirmation_token':draft['confirmation_token']})
    lib.chat('deepseek','你好')
    assert '你是澄澄' in prompts[-1][0]['content']
    assert api('gpt',False,'/config/persona')['data']['name']=='白龙娘'
    assert len(api('deepseek',False,'/config/audit'))==1
    with pytest.raises(OperationError):api('deepseek',True,'/config/operations/draft',{})


def test_no_path_traversal_or_portrait_file_escape(library):
    lib,_,_=library
    for key in ['../gpt','gpt/../../','unknown']:
        with pytest.raises(ValueError):lib.directory(key)
    lib.root.mkdir(parents=True,exist_ok=True)
    (lib.root/'art-index.json').write_text(json.dumps({'gpt':{'file':'../secret.jpg'}}))
    with pytest.raises(ValueError):lib.portrait('gpt')


def test_role_api_does_not_allow_shared_memory_or_unknown_payload(library):
    lib,_,factory=library
    server=SimpleNamespace(character_root=lib.root,db_path=str(lib.management_db),character_llm_factory=factory)
    for data in [{'text':'你好','persona':'override'},{'text':''},{'text':True}]:
        with pytest.raises(OperationError):handle(server,True,'/characters/gpt/chat',{},data)
    with pytest.raises(OperationError):handle(server,False,'/characters/gpt/config/memory',{}, {})

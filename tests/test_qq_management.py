import asyncio
import json
from types import SimpleNamespace
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.admin_store import AdminStore, initial_persona
from avatar.brain.operations import OperationService, OperationError
from avatar.channels.qq.engine import AvatarEngine
from avatar.channels.qq.protocol import Incoming
from avatar.channels.qq.management import Contexts, SharedConfiguration


@pytest.fixture
def admin(tmp_path):
    memory = MemoryStore(str(tmp_path/'admin.db'))
    store = AdminStore(memory);store.migrate(initial_persona())
    yield memory, store, OperationService(store)
    memory.close()


class FakeLLM:
    available = True
    def __init__(self):self.prompts=[]
    def chat_analysis(self, *args, **kwargs):return '{}'
    def chat(self, messages, **kwargs):
        self.prompts.append(messages)
        return '已根据已确认资料回复。'


def incoming(mid='one', text='河海开放时间', user='a'):
    return Incoming('onebot:12345','private',user,user,mid,text,1000000.)


def test_only_confirmed_persona_and_knowledge_reach_qq_no_admin_private_memory(tmp_path, admin):
    memory, store, ops = admin
    memory.remember('管理员的私人秘密不可共享')
    persona = ops.create_draft('persona.update', {'changes': {'name':'星澜'}})
    knowledge = ops.create_draft('knowledge.import', {'title':'河海开放时间', 'text':'河海开放时间：周二上午九点。'})
    llm = FakeLLM()
    engine = AvatarEngine(llm_factory=lambda:llm, management_db=tmp_path/'admin.db')
    directory=tmp_path/'qq'
    engine.respond(incoming(),directory)
    assert '星澜' not in llm.prompts[-1][0]['content']
    assert '周二上午九点' not in llm.prompts[-1][0]['content']
    ops.confirm(persona.draft_id,persona.confirmation_token)
    ops.confirm(knowledge.draft_id,knowledge.confirmation_token)
    engine.respond(incoming('two'),directory)
    prompt=llm.prompts[-1][0]['content']
    assert '星澜' in prompt and '周二上午九点' in prompt
    assert '管理员的私人秘密' not in prompt
    local=MemoryStore(str(directory/'memory.db'))
    try:
        assert not any('周二上午九点' in r['content'] for r in local.list_memories())
        row=local._conn.execute('SELECT data FROM qq_turn_traces ORDER BY created_at DESC LIMIT 1').fetchone()
        trace=json.loads(row[0])
        assert trace['persona_version']==store.current_persona()['id']
        assert trace['knowledge_sources'][0]['title']=='河海开放时间'
    finally:local.close()


def test_context_correction_confirmation_audit_and_next_turn_isolation(tmp_path, admin, monkeypatch):
    from avatar.channels.qq import admin_api
    root=tmp_path/'qq'
    contexts=Contexts(root)
    monkeypatch.setattr(admin_api,'Contexts',lambda:contexts)
    llm=FakeLLM();engine=AvatarEngine(llm_factory=lambda:llm, management_db=tmp_path/'admin.db')
    keys=[]
    for user in ['a','b']:
        message=incoming(user,'你好',user)
        directory=root/'contexts'/message.context_key
        engine.respond(message,directory)
        with contexts.memory(message.context_key) as m:m.remember('名字: 小林',memory_type='user_profile')
        keys.append(message.context_key)
    assert len(contexts.list())==2
    def api(key, post, route, data=None):
        return admin_api.handle(SimpleNamespace(),post,'/qq/contexts/'+key+route,{},data or {})[1]
    drafts=[]
    for key in keys:
        row=api(key,False,'/memory')[0]
        drafts.append(api(key,True,'/memory/batch-draft',{'actions':[{'action':'correct','id':row['id'],'content':'小周'}]}))
        assert api(key,False,'/memory')[0]['content']=='名字: 小林'
    with pytest.raises(OperationError):
        api(keys[1],True,f"/operations/{drafts[1]['draft_id']}/confirm",{'confirmation_token':drafts[0]['confirmation_token']})
    draft=drafts[0]
    api(keys[0],True,f"/operations/{draft['draft_id']}/confirm",{'confirmation_token':draft['confirmation_token']})
    assert len(api(keys[0],False,'/audit'))==1
    assert api(keys[1],False,'/audit')==[]
    engine.respond(incoming('next','我叫什么','a'),root/'contexts'/keys[0])
    assert '"名字": "小周"' in llm.prompts[-1][0]['content']
    assert api(keys[1],False,'/memory')[0]['content']=='名字: 小林'
    assert api(keys[0],False,'/traces')[0]['trace']['profile_keys'] == ['名字']
    with pytest.raises(OperationError):api(keys[0],True,'/persona/draft',{'changes':{'name':'越权'}})
    with pytest.raises(OperationError):api(keys[0],True,'/operations/draft',{'operation_type':'persona.update'})


def test_context_path_cannot_escape_or_create_databases(tmp_path):
    contexts=Contexts(tmp_path/'qq')
    for key in ['../admin','a'*64,'x'*64]:
        with pytest.raises(ValueError):contexts.path(key)
    key='b'*64
    directory=tmp_path/'qq/contexts'/key
    directory.mkdir(parents=True)
    outside=tmp_path/'other.db';outside.touch()
    (directory/'memory.db').symlink_to(outside)
    with pytest.raises(ValueError):contexts.path(key)


def test_readonly_docs_queries_only_approved_knowledge(tmp_path, admin):
    from avatar.channels.qq.tools import ReadOnlySession, tool_command
    memory,store,ops=admin
    memory.remember('管理员私人联系方式')
    draft=ops.create_draft('knowledge.import',{'title':'河海校历','text':'河海校历：周三开放。'})
    ops.confirm(draft.draft_id,draft.confirmation_token)
    session=ReadOnlySession(SharedConfiguration(tmp_path/'admin.db','河海'))
    assert tool_command('帮我查资料 河海校历')=='/docs 河海校历'
    async def run():
        result=await session.call_tool('search_documents',{'query':'河海校历'})
        assert result.structuredContent['results'][0]['title']=='河海校历'
        assert '管理员私人联系方式' not in json.dumps(result.structuredContent,ensure_ascii=False)
        for name in ['create_reminder','cancel_reminder','run_shell','persona.update']:
            with pytest.raises(ValueError):await session.call_tool(name,{})
    asyncio.run(run())


def test_qq_tool_route_preserves_boundary_and_trace(tmp_path, admin):
    calls=[]
    class Agent:
        def run(self,text,llm):
            calls.append(text)
            return {'reply':'这是查得的资料。','sources':[], 'tool_calls':[{'tool':'web_search','status':'ok'}]}
    engine=AvatarEngine(llm_factory=FakeLLM,management_db=tmp_path/'admin.db',web_agent_factory=lambda shared:Agent())
    engine.respond(incoming('lookup','/search 河海大学'),tmp_path/'context')
    assert calls==['/search 河海大学']
    db=MemoryStore(str(tmp_path/'context/memory.db'))
    try:
        trace=json.loads(db._conn.execute('SELECT data FROM qq_turn_traces').fetchone()[0])
        assert trace['tool_calls'][0]['tool']=='web_search'
        assert not db.list_memories()
    finally:db.close()


def test_tools_reject_model_write_calls_and_never_receive_personal_history():
    from contextlib import asynccontextmanager
    from avatar.tools.web_agent import WebAgent
    called=[]
    class Session:
        async def list_tools(self):return SimpleNamespace(tools=[SimpleNamespace(name=n) for n in ['web_search','read_webpage']])
        async def call_tool(self,name,arguments):called.append(name);raise AssertionError('write must not execute')
    @asynccontextmanager
    async def connect():yield Session()
    class Model:
        available=True
        def chat_tools(self,messages,tools):
            assert all(t['function']['name'] in ('web_search','read_webpage') for t in tools)
            return {'content':None,'tool_calls':[{'id':'bad','type':'function','function':{'name':'create_reminder','arguments':'{"text":"提醒我明天八点做事"}'}}]}
        def chat(self,*args,**kwargs):return '不会执行写入。'
    result=WebAgent(connect=connect,max_calls=1,allowed_tools={'web_search','read_webpage'}).run('测试只读权限',Model())
    assert not called and result['tool_calls'][0]['status']=='rejected'


def test_weather_and_document_requests_have_explicit_routes():
    from avatar.channels.qq.tools import tool_command
    assert tool_command('帮我查一下南京天气')=='/weather 南京'
    assert tool_command('请查询资料 河海校历')=='/docs 河海校历'
    assert tool_command('今天有点累，想聊聊天') is None


def test_qq_management_http_requires_owner_auth(tmp_path,monkeypatch):
    import threading,urllib.request,urllib.error
    from avatar.web import create_server
    from avatar.channels.qq import admin_api
    monkeypatch.setattr(admin_api,'Contexts',lambda:Contexts(tmp_path/'qq'))
    server=create_server(str(tmp_path/'admin-http.db'),port=0,legacy_writes=False)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/api/v1/qq/contexts'
    try:
        with pytest.raises(urllib.error.HTTPError) as error:urllib.request.urlopen(url)
        assert error.value.code==403
        req=urllib.request.Request(url,headers={'X-Avatar-Token':server.token})
        with urllib.request.urlopen(req) as response:
            assert json.load(response)['data']==[]
    finally:
        server.shutdown();thread.join();server.server_close()

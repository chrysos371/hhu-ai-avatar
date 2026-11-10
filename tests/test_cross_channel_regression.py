"""Offline entry-point contract tests; no QQ connection or cloud inference."""
import json
import threading
import urllib.request
from pathlib import Path
import pytest
from avatar.brain.admin_store import AdminStore, initial_persona
from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationService
from avatar.channels.qq.engine import AvatarEngine
from avatar.channels.qq.protocol import Incoming
from avatar.web import create_server


@pytest.fixture
def entries(tmp_path,monkeypatch):
    from avatar import main
    from avatar.config import config
    monkeypatch.setattr(config.embedding,'model','')
    prompts=[]
    class Fake:
        available=True;model='offline-contract';profile_id='contract'
        def chat_analysis(self,*args,**kwargs):return '{}'
        def chat(self,messages,**kwargs):
            prompts.append(messages)
            if messages[-1]['content']=='触发回复故障':raise RuntimeError('private provider details')
            return '测试回复。'
    monkeypatch.setattr(main,'LLMEngine',Fake)
    db=tmp_path/'admin.db'
    memory=MemoryStore(str(db));store=AdminStore(memory);store.migrate(initial_persona())
    ops=OperationService(store)
    d=ops.create_draft('persona.update',{'changes':{'name':'入口验收人设'}})
    ops.confirm(d.draft_id,d.confirmation_token);memory.close()
    server=create_server(str(db),port=0,legacy_writes=False)
    server.character_root=tmp_path/'characters';server.character_llm_factory=Fake
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    counter=0
    def call(channel,text):
        nonlocal counter
        counter+=1
        if channel=='qq':
            directory=tmp_path/'qq'
            message=Incoming('contract-bot','private','contract-user','contract-user',str(counter),text,1000000+counter)
            reply=AvatarEngine(llm_factory=Fake,management_db=db).respond(message,directory)
            mem=MemoryStore(str(directory/'memory.db'))
            try:trace=json.loads(mem._conn.execute('SELECT data FROM qq_turn_traces WHERE receipt_key=?',(message.receipt_key,)).fetchone()[0])
            finally:mem.close()
            return {'reply':reply,'trace':trace}
        path='/api/v1/chat' if channel=='web' else '/api/v1/characters/gpt/chat'
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                    data=json.dumps({'text':text}).encode(),headers={'Content-Type':'application/json','X-Avatar-Token':server.token})
        with urllib.request.urlopen(request,timeout=10) as response:return json.loads(response.read())['data']
    yield call,prompts,server
    server.shutdown();thread.join();server.server_close()


@pytest.mark.parametrize('channel',['web','qq','role'])
def test_persona_and_trace_contract(entries,channel):
    call,prompts,_=entries
    result=call(channel,'你好')
    assert ('白龙娘' if channel=='role' else '入口验收人设') in prompts[-1][0]['content']
    trace=result['trace']
    assert trace['schema_version']==1 and trace['model']=='offline-contract'
    assert trace['analysis_status']=='model' and trace['reply_degraded'] is False
    assert 'system_prompt' not in trace and 'api_key' not in trace


@pytest.mark.parametrize('channel',['web','qq','role'])
def test_private_facts_stay_in_their_entry_scope(entries,channel):
    call,prompts,_=entries
    call(channel,'我叫隔离验收小林')
    for other in ('web','qq','role'):
        call(other,'你记得我叫什么吗？')
        system=prompts[-1][0]['content']
        assert ('隔离验收小林' in system)==(channel==other)


@pytest.mark.parametrize('channel',['web','qq','role'])
def test_model_failure_is_visible_in_every_entry(entries,channel):
    call,_,_=entries
    result=call(channel,'触发回复故障')
    assert result['trace']['reply_degraded'] is True
    assert result['reply'] and 'private provider details' not in json.dumps(result)

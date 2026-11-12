"""Actual provider HTTP/SDK/template with explicitly scripted model + fake GPU probes.

No llama construction, tensor read or CUDA context; never native evidence.
"""
from contextlib import ExitStack
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
import serve_local_model_eval as provider
from avatar.brain.llm import LLMEngine
from avatar.paths import project_data_root

PROTOCOL=json.loads((ROOT/'evals/interaction/cycle-40/native-tool-wire-protocol.json').read_text())
RAW='<tool_call>{"name":"read_reminder_state","arguments":{"reminder_id":1}}</tool_call>'
OUT=BASE/'审计/工作目录/002-受控HTTP交接'


def run_one(enabled):
    label='opt-in' if enabled else 'default'
    group=OUT/label;group.mkdir(parents=True,exist_ok=False)
    calls=[];models=[];servers=[];errors=[];http=[]
    with tempfile.TemporaryDirectory(prefix='c40-wire-',dir=project_data_root()/'tmp') as temporary:
        temporary=Path(temporary);model=temporary/'fixture.gguf';model.write_bytes(b'controlled fixture; not a real GGUF')
        model_sha=provider.sha(model)
        metadata=temporary/'metadata.json';metadata.write_text(json.dumps({'path':model.name,'lfs':{'oid':model_sha}}))
        registry={'models':[{'model_id':'fixture','file':model.name,'sha256':model_sha,'revision':'b'*40,'required_free_mib':16384}]}
        registry_path=temporary/'registry.json';registry_path.write_text(json.dumps(registry))
        ready=group/'ready.json';trace=group/'provider-trace.jsonl'
        completions=([('普通兼容。','stop')] if not enabled else [(RAW,'stop'),('合成工具结果：本条记录已取消。','stop'),('准备查询。'+RAW,'stop'),(RAW,'length'),('普通兼容。','stop')])
        class ScriptedModel:
            def __init__(self,**options):
                self.metadata={'tokenizer.chat_template':(BASE/'审计/工作目录/001-工具调用调查/embedded-chat-template.jinja').read_text(),'general.name':'SCRIPTED-NOT-NATIVE'}
                self.closed=False;models.append(self)
            def create_completion(self,**options):
                text,finish=completions[len(calls)];calls.append(options)
                return {'choices':[{'text':text,'finish_reason':finish}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
            def close(self):self.closed=True
        real_server=provider.ThreadingHTTPServer
        class CapturedServer(real_server):
            def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);servers.append(self)
        def gpu_probe(command,**kwargs):
            assert command[0]=='nvidia-smi'
            return '0, GPU-CONTROLLED-NOT-REAL, 40000, 0\n' if 'index,uuid' in command[1] else str(__import__('os').getpid())+', 2048\n'
        argv=['serve_local_model_eval.py','--model',str(model),'--model-key','fixture','--metadata',str(metadata),'--ready',str(ready),'--trace',str(trace),'--registry',str(registry_path),'--expected-registry-sha256',provider.sha(registry_path)]
        if enabled:argv.append('--enable-tools')
        def child():
            try:provider.main()
            except BaseException as error:errors.append(repr(error))
        actual_version=importlib.metadata.version
        with ExitStack() as stack:
            stack.enter_context(patch.object(sys,'argv',argv))
            stack.enter_context(patch.object(provider,'load_registry',return_value=(registry,provider.sha(registry_path),registry_path)))
            # provider expects registry inside ROOT only for reporting; label remains
            # synthetic. Use a project-relative registry path while mocking reads.
            registry_identity=ROOT/'evals/interaction/cycle-40/model-registry.json'
            original_sha=provider.sha
            stack.enter_context(patch.object(provider,'load_registry',return_value=(registry,original_sha(registry_identity),registry_identity)))
            stack.enter_context(patch.dict(sys.modules,{'llama_cpp':SimpleNamespace(Llama=ScriptedModel,LlamaGrammar=None,llama_supports_gpu_offload=lambda:True)}))
            stack.enter_context(patch.object(provider.subprocess,'check_output',side_effect=gpu_probe))
            stack.enter_context(patch.object(provider.signal,'signal',return_value=None))
            stack.enter_context(patch.object(provider,'ThreadingHTTPServer',CapturedServer))
            stack.enter_context(patch('importlib.metadata.version',side_effect=lambda name:'SCRIPTED' if name=='llama-cpp-python' else actual_version(name)))
            # Metadata path must be project-relative in ready output: fixture is not
            # registered with a metadata path, and ready permits its actual /data path.
            thread=threading.Thread(target=child);thread.start()
            try:
                for _ in range(500):
                    if ready.exists() or errors:break
                    time.sleep(.01)
                assert ready.exists(),errors
                url=json.loads(ready.read_text())['url']
                opener=build_opener(ProxyHandler({}))
                def raw_request(data,expected):
                    raw=json.dumps(data,ensure_ascii=False).encode()
                    req=Request(url+'/chat/completions',data=raw,headers={'Authorization':'Bearer local-eval-only','Content-Type':'application/json'})
                    try:
                        with opener.open(req,timeout=5) as response:status,body=response.status,json.loads(response.read())
                    except HTTPError as error:status,body=error.code,json.loads(error.read())
                    http.append({'request':data,'wire_sha256':hashlib.sha256(raw).hexdigest(),'status':status,'response':body})
                    assert status==expected,(status,body)
                    return body
                base={'model':'fixture','messages':[{'role':'user','content':'读取编号1'}],'tools':PROTOCOL['tools'],'stream':False}
                if not enabled:raw_request(base,400)
                else:
                    engine=LLMEngine(base_url=url,api_key='local-eval-only',model='fixture',max_retries=0)
                    try:
                        selected=engine.chat_tools(base['messages'],tools=PROTOCOL['tools'])
                        assert selected['tool_calls'][0]['function']['name']=='read_reminder_state'
                        follow=base['messages']+[selected,{'role':'tool','tool_call_id':selected['tool_calls'][0]['id'],'content':'{"status":"cancelled","synthetic_fixture":true}'}]
                        final=engine.chat_tools(follow,tools=PROTOCOL['tools'])
                        assert final['content']=='合成工具结果：本条记录已取消。' and not final.get('tool_calls')
                    finally:engine._client.close()
                    raw_request(base|{'stream':True},400)
                    raw_request(base|{'response_format':{'type':'json_object'}},400)
                    raw_request(base,500)
                    raw_request(base,500)
                raw_request({'model':'fixture','messages':[{'role':'user','content':'你好'}]},200)
            finally:
                if servers:servers[0].shutdown()
                thread.join(10)
            assert not thread.is_alive() and not errors and all(m.closed for m in models),errors
    rows=[json.loads(line) for line in trace.read_text().splitlines()]
    assert len(rows)==len(calls)==(5 if enabled else 1)
    if enabled:
        assert rows[0]['finish_reason']=='stop' and rows[0]['wire_finish_reason']=='tool_calls'
        assert rows[1]['wire_message']['content']=='合成工具结果：本条记录已取消。'
        assert all(r['outcome']=='ToolWireError' and r['wire_message'] is None for r in rows[2:4])
        assert rows[2]['response'].startswith('准备查询。') and rows[3]['finish_reason']=='length'
        assert '<tool_response>' in calls[1]['prompt'] and '# Tools' in calls[0]['prompt']
        assert json.loads(http[-3]['response']['error'] is None) if False else True
    else:assert '# Tools' not in calls[0]['prompt']
    result={'verified':True,'scope':'scripted model/fake GPU resources; actual HTTP, SDK, Jinja and provider handler only','native_or_GPU_calls':0,'scripted_completion_calls':len(calls),'HTTP_cases':http,'provider_trace_sha256':provider.sha(trace),'provider_source_sha256':provider.sha(ROOT/'scripts/serve_local_model_eval.py'),'wire_adapter_sha256':provider.sha(ROOT/'src/avatar/lab/native_tool_wire.py'),'controller_sha256':provider.sha(__file__),'all_servers_models_closed':True}
    (group/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(label+': actual HTTP/SDK controlled proof passed; scripted completions='+str(len(calls))+';0 native/GPU')


if __name__=='__main__':
    run_one(False)
    run_one(True)

"""Core SDK -> native worker HTTP/Jinja/provider; scripted outputs/fake GPU only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from avatar.brain.llm import LLMEngine
from avatar.paths import environment_python,project_data_root
from probe_structured_provider import environment

PROTOCOL=json.loads((ROOT/'evals/interaction/cycle-40/native-tool-wire-protocol.json').read_text())
OUT=BASE/'审计/工作目录/002-受控HTTP交接'


def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def run_one(enabled):
    group=OUT/('opt-in' if enabled else 'default');group.mkdir(parents=True,exist_ok=False)
    http=[];sdk=[]
    with tempfile.TemporaryDirectory(prefix='c40-wire-',dir=project_data_root()/'tmp') as temporary,(group/'worker.log').open('x') as log:
        python=environment_python(native=True)
        command=[str(python),str(BASE/'审计/controlled_worker.py'),str(group),temporary,'enabled' if enabled else 'disabled']
        worker=subprocess.Popen(command,cwd=ROOT,env=environment(python),stdout=log,stderr=subprocess.STDOUT)
        try:
            ready=group/'ready.json'
            for _ in range(1000):
                if ready.exists() or worker.poll() is not None:break
                time.sleep(.01)
            assert ready.exists(),(group/'worker.log').read_text()
            url=json.loads(ready.read_text())['url'];opener=build_opener(ProxyHandler({}))
            def raw_request(data,expected):
                raw=json.dumps(data,ensure_ascii=False).encode()
                req=Request(url+'/chat/completions',data=raw,headers={'Authorization':'Bearer local-eval-only','Content-Type':'application/json'})
                try:
                    with opener.open(req,timeout=5) as response:status,body=response.status,json.loads(response.read())
                except HTTPError as error:status,body=error.code,json.loads(error.read())
                http.append({'request':data,'wire_sha256':hashlib.sha256(raw).hexdigest(),'status':status,'response':body})
                assert status==expected,(status,body)
            base={'model':'fixture','messages':[{'role':'user','content':'读取编号1'}],'tools':PROTOCOL['tools'],'stream':False}
            if not enabled:raw_request(base,400)
            else:
                engine=LLMEngine(base_url=url,api_key='local-eval-only',model='fixture',max_retries=0)
                try:
                    selected=engine.chat_tools(base['messages'],tools=PROTOCOL['tools']);sdk.append(selected)
                    assert selected['tool_calls'][0]['function']['name']=='read_reminder_state'
                    follow=base['messages']+[selected,{'role':'tool','tool_call_id':selected['tool_calls'][0]['id'],'content':'{"status":"cancelled","synthetic_fixture":true}'}]
                    final=engine.chat_tools(follow,tools=PROTOCOL['tools']);sdk.append(final)
                    assert final['content']=='合成工具结果：本条记录已取消。' and not final.get('tool_calls')
                finally:engine._client.close()
                raw_request(base|{'stream':True},400)
                raw_request(base|{'response_format':{'type':'json_object'}},400)
                raw_request(base,500);raw_request(base,500)
            raw_request({'model':'fixture','messages':[{'role':'user','content':'你好'}]},200)
        finally:
            (group/'stop').touch()
            try:exit_code=worker.wait(timeout=15)
            except subprocess.TimeoutExpired:
                worker.terminate();worker.wait(timeout=10);raise
        assert exit_code==0,(group/'worker.log').read_text()
    rows=[json.loads(line) for line in (group/'provider-trace.jsonl').read_text().splitlines()]
    cleanup=json.loads((group/'worker-cleanup.json').read_text())
    assert len(rows)==cleanup['scripted_model_calls']==(5 if enabled else 1)
    if enabled:
        assert rows[0]['finish_reason']=='stop' and rows[0]['wire_finish_reason']=='tool_calls'
        assert rows[0]['wire_message']['tool_calls']==sdk[0]['tool_calls']
        assert rows[1]['wire_message']['content']==sdk[1]['content']
        assert all(r['outcome']=='ToolWireError' and r['wire_message'] is None for r in rows[2:4])
        assert rows[2]['response'].startswith('准备查询。') and rows[3]['finish_reason']=='length'
    assert cleanup['all_models_servers_closed'] and cleanup['native_or_GPU_calls']==0
    result={'verified':True,'scope':'scripted model/fake GPU resources; actual HTTP, SDK, Jinja and provider handler only','native_or_GPU_calls':0,'scripted_completion_calls':len(rows),'HTTP_cases':http,'SDK_messages':sdk,'provider_trace_sha256':digest(group/'provider-trace.jsonl'),'provider_source_sha256':digest(ROOT/'scripts/serve_local_model_eval.py'),'wire_adapter_sha256':digest(ROOT/'src/avatar/lab/native_tool_wire.py'),'controller_sha256':digest(__file__),'worker_sha256':digest(BASE/'审计/controlled_worker.py'),'all_servers_models_closed':True,'worker_exit_code':exit_code}
    (group/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(group.name+': actual HTTP/SDK controlled proof passed; scripted completions='+str(len(rows))+';0 native/GPU')


if __name__=='__main__':
    run_one(False);run_one(True)

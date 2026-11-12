"""Frozen standalone 4B native tool wire diagnostic; synthetic tool fixtures only."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from native_common import ROOT, BASE, WORK, PROTOCOL, REGISTRY, RUNTIME, read, digest, verify_freeze, environment_python, environment


def write(path,data):
    temporary=path.with_suffix(path.suffix+'.part')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def processes():
    return subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def collect_sdk_stream(client,*,model,messages,max_tokens):
    """Use the same observed synchronous SDK client for SSE warmup only."""
    events=[];parts=[]
    with client.chat.completions.create(model=model,messages=messages,temperature=0,
            max_tokens=max_tokens,stream=True) as stream:
        for chunk in stream:
            events.append(chunk.model_dump())
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
    reasons=[c['finish_reason'] for e in events for c in e['choices'] if c['finish_reason'] is not None]
    if reasons!=['stop']:raise ValueError('SDK SSE warmup did not stop completely')
    return {'role':'assistant','content':''.join(parts)},events


def sample(args):
    frozen=verify_freeze(args.freeze,args.expected_freeze_sha256)
    args.output=args.output.resolve()
    if args.output.parent!=BASE/'实验':raise ValueError('Output must be a fresh C40 experiment directory')
    args.output.mkdir(exist_ok=False)
    protocol=read(PROTOCOL);spec=read(REGISTRY)['models'][0]
    assert len(protocol['cases'])==8 and protocol['sampling']['repetitions']==3
    python=environment_python(native=True)
    ready=args.output/'provider-ready.json';trace=args.output/'provider-trace.jsonl'
    command=[str(python),str(ROOT/'scripts/serve_local_model_eval.py'),'--enable-tools',
        '--model',str(ROOT/'models/qwen3-4b-gguf'/spec['file']),'--model-key',spec['model_id'],
        '--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),
        '--backend','cuda','--registry',str(REGISTRY),'--expected-registry-sha256',digest(REGISTRY)]
    report={'scope':protocol['scope'],'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'freeze_sha256':args.expected_freeze_sha256,'frozen_source_ref':frozen['source_ref'],
        'model_id':spec['model_id'],'provider_command':command,'completed':False,'failure':None,
        'native_calls':0,'Avatar_application_turns':0,'business_reads_or_writes':0,
        'synthetic_tool_result_fixtures_only':True,'groups':[],'warmups':[],'cleanup_passed':False}
    write(args.output/'evaluation.json',report)
    provider=None;engine=None;requests=[];responses=[];context={}
    request_log=(args.output/'request-wire.jsonl').open('x')
    response_log=(args.output/'response-wire.jsonl').open('x')
    started=time.monotonic()
    with (args.output/'provider.log').open('x') as log:
        try:
            provider=subprocess.Popen(command,cwd=ROOT,env=environment(python),stdout=log,stderr=subprocess.STDOUT)
            report['provider_pid']=provider.pid
            write(args.output/'evaluation.json',report)
            for _ in range(300):
                if ready.exists() or provider.poll() is not None:break
                time.sleep(1)
            if not ready.exists():raise RuntimeError('provider readiness failed before fixed study')
            actual=read(ready)
            assert actual['backend']=='cuda' and actual['model_sha256']==spec['sha256']
            assert actual['model_revision']==spec['revision'] and actual['registry_sha256']==digest(REGISTRY)
            assert actual['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
            assert actual['tool_adapter_enabled'] and actual['tool_adapter_source_sha256']==frozen['sha256']['src/avatar/lab/native_tool_wire.py']
            assert actual['template_sha256']==read(BASE/'审计/工作目录/001-工具调用调查/gguf-template.json')['template_sha256']
            assert actual['pid']==provider.pid and actual['process_gpu_mib_after_load']
            gpu_rows=processes();assert any(line.split(',')[0].strip()==str(provider.pid) and actual['chosen_gpu']['uuid'] in line for line in gpu_rows.splitlines())
            kernel={'pid':provider.pid,'cmdline':Path(f'/proc/{provider.pid}/cmdline').read_bytes().split(b'\0')[:-1],
                'gpu_processes':gpu_rows,'maps':Path(f'/proc/{provider.pid}/maps').read_text()}
            kernel['cmdline']=[n.decode() for n in kernel['cmdline']]
            assert kernel['cmdline']==command
            libs={Path(line.split()[-1]) for line in kernel['maps'].splitlines() if '/' in line and '.so' in line.split()[-1]}
            reference=read(RUNTIME)['files_sha256'];kernel['mapped_frozen_libraries']={str(p):digest(p) for p in libs if str(p) in reference}
            assert any('libggml-cuda.so' in name for name in kernel['mapped_frozen_libraries'])
            assert all(sha==reference[name] for name,sha in kernel['mapped_frozen_libraries'].items())
            write(args.output/'provider-kernel-proof.json',kernel)
            verify_freeze(args.freeze,args.expected_freeze_sha256)
            import httpx
            from openai import OpenAI
            from avatar.brain.llm import LLMEngine
            def on_request(request):
                raw=request.read();row={'ordinal':len(requests)+1,'context':dict(context),'request':json.loads(raw),
                    'request_body_sha256':hashlib.sha256(raw).hexdigest()}
                requests.append(row);request_log.write(json.dumps(row,ensure_ascii=False)+'\n');request_log.flush()
            def on_response(response):
                row={'ordinal':len(responses)+1,'status':response.status_code,'context':dict(context)}
                if 'application/json' in response.headers.get('content-type',''):
                    row['body']=json.loads(response.read())
                else:row['stream']=True
                responses.append(row);response_log.write(json.dumps(row,ensure_ascii=False)+'\n');response_log.flush()
            client=httpx.Client(trust_env=False,event_hooks={'request':[on_request],'response':[on_response]})
            engine=LLMEngine(base_url=actual['url'],api_key='local-eval-only',model=spec['model_id'],max_retries=0)
            engine._client.close()
            engine._client=OpenAI(base_url=actual['url'],api_key='local-eval-only',max_retries=0,http_client=client)
            def invoke(phase,rep,case,messages,tools=None,stream=False,max_tokens=256):
                context.clear();context.update(phase=phase,repetition=rep,case=case)
                first=len(requests);begin=time.monotonic()
                row={'phase':phase,'repetition':rep,'case':case,'request_ordinal':first+1,'result':None,'error':None}
                try:
                    if stream:
                        row['result'],row['sdk_stream_events']=collect_sdk_stream(engine._client,model=spec['model_id'],messages=messages,max_tokens=max_tokens)
                    elif tools:
                        row['result']=engine.chat_tools(messages,tools=tools,temperature=0,max_tokens=max_tokens)
                    else:
                        row['result']={'role':'assistant','content':engine.chat(messages,temperature=0,max_tokens=max_tokens)}
                except Exception as error:row['error']=type(error).__name__+': '+str(error)[:240]
                row['seconds']=time.monotonic()-begin
                assert len(requests)==first+1,'unexpected SDK retry/missing request'
                return row
            for n in range(2):
                row=invoke('warmup',0,str(n+1),[{'role':'user','content':'只回复“预热完成”。'}],stream=n==1,max_tokens=32)
                report['warmups'].append(row)
                assert row['error'] is None
            for rep in range(1,4):
                group={'repetition':rep,'plain':None,'cases':[]}
                group['plain']=invoke('plain-control',rep,'plain',[{'role':'user','content':protocol['plain_control']['text']}])
                for case in protocol['cases']:
                    messages=[{'role':'system','content':protocol['system']},{'role':'user','content':case['text']}]
                    row=invoke('selection',rep,case['id'],messages,tools=protocol['tools'])
                    selected=row['result'] or {};calls=selected.get('tool_calls',[])
                    exact=False
                    if row['error'] is None and len(calls)==1:
                        function=calls[0]['function']
                        exact=(function['name']==case['tool'] and canonical(json.loads(function['arguments']))==canonical(case['args']))
                    row['expected_tool']=case['tool'];row['exact_expected_selection']=bool(exact if case['tool'] else row['error'] is None and not calls)
                    row['followup']=None
                    if case['tool'] and exact:
                        fixture=case['fixture']|{'synthetic_fixture':True}
                        follow=messages+[selected,{'role':'tool','tool_call_id':calls[0]['id'],'content':json.dumps(fixture,ensure_ascii=False)}]
                        row['followup']=invoke('fixture-followup',rep,case['id'],follow,tools=protocol['tools'])
                    group['cases'].append(row)
                    write(args.output/f'repetition-{rep}.json',group)
                report['groups'].append(group)
                write(args.output/'evaluation.json',report)
                verify_freeze(args.freeze,args.expected_freeze_sha256)
            report['completed']=True
        except BaseException as error:
            report['failure']=type(error).__name__+': '+str(error)[:500]
        finally:
            if engine is not None:engine._client.close()
            request_log.close();response_log.close()
            if provider is not None:
                if provider.poll() is None:provider.terminate()
                try:report['provider_exit_code']=provider.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    provider.kill();report['provider_exit_code']=provider.wait(timeout=15)
                report['gpu_processes_after_cleanup']=processes()
                report['provider_proc_present_after_cleanup']=Path(f'/proc/{provider.pid}').exists()
                report['cleanup_passed']=(report['provider_exit_code']==0 and not report['provider_proc_present_after_cleanup']
                    and not any(line.split(',')[0].strip()==str(provider.pid) for line in report['gpu_processes_after_cleanup'].splitlines()))
            rows=[json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
            inferred=[r for r in rows if r.get('id')]
            report['native_calls']=len(inferred)
            report['native_raw_stop_count']=sum(r['finish_reason']=='stop' for r in inferred)
            report['wire_selection_exact_count']=sum(c['exact_expected_selection'] for g in report['groups'] for c in g['cases'])
            report['wire_selection_total']=sum(len(g['cases']) for g in report['groups'])
            report['synthetic_fixture_followups']=sum(c['followup'] is not None for g in report['groups'] for c in g['cases'])
            report['request_trace_identity_matched']=(len(inferred)==len(requests) and all(r['request_body_sha256']==q['request_body_sha256'] for r,q in zip(inferred,requests)))
            report['engineering_passed']=(report['completed'] and report['cleanup_passed'] and report['request_trace_identity_matched']
                and all(r['outcome']=='completed' and r['finish_reason']=='stop' for r in inferred))
            report['wire_expected_gate_passed']=(report['engineering_passed'] and report['wire_selection_total']==24 and report['wire_selection_exact_count']==24
                and report['synthetic_fixture_followups']==12 and all(not (c['followup']['result'] or {}).get('tool_calls') and c['followup']['error'] is None for g in report['groups'] for c in g['cases'] if c['followup']))
            report['overall_seconds_including_load_and_proof']=time.monotonic()-started
            report['source_current_after_execution']=all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
            report['actual_project_modules']={name:{'file':str(Path(module.__file__).resolve().relative_to(ROOT)),
                'sha256':digest(module.__file__)} for name,module in list(sys.modules.items()) if name.startswith('avatar') and getattr(module,'__file__',None) and Path(module.__file__).resolve().is_relative_to(ROOT)}
            report['artifacts_sha256']={p.name:digest(p) for p in args.output.iterdir() if p.is_file() and p.name!='evaluation.json'}
            write(args.output/'evaluation.json',report)
    print('C40 native study completed='+str(report['completed'])+';calls='+str(report['native_calls'])+';wire gate='+str(report.get('wire_expected_gate_passed'))+';cleanup='+str(report['cleanup_passed']))
    if not report['completed']:raise RuntimeError(report['failure'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--expected-freeze-sha256',required=True)
    parser.add_argument('--output',type=Path,required=True)
    sample(parser.parse_args())

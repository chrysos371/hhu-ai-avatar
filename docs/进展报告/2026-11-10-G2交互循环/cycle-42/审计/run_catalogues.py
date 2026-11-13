"""Frozen real4B three-arm source-catalogue/read/clarification runner; no default app."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import time

from native_common import ROOT,BASE,WORK,PROTOCOL,REGISTRY,RUNTIME,read,digest,verify_freeze,environment_python,environment,collect_sdk_stream
from sample_catalogues import sample_repetition


def write(path,data):
    temporary=path.with_suffix(path.suffix+'.part')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def processes():
    return subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)


def run(args):
    frozen=verify_freeze(args.freeze,args.expected_freeze_sha256,args.partition)
    args.output=args.output.resolve()
    if args.output.parent!=BASE/'实验' or not re.fullmatch(r'[a-z0-9_-]+',args.output.name):
        raise ValueError('Use a fresh named C42 experiment directory')
    if frozen.get('output_tag')!=args.output.name:
        raise ValueError('Output tag differs from descriptor')
    args.output.mkdir(exist_ok=False)
    protocol=read(PROTOCOL);spec=read(REGISTRY)['models'][0]
    python=environment_python(native=True)
    ready=args.output/'provider-ready.json';trace=args.output/'provider-trace.jsonl'
    command=[str(python),str(ROOT/'scripts/serve_local_model_eval.py'),'--enable-tools',
        '--model',str(ROOT/'models/qwen3-4b-gguf'/spec['file']),'--model-key',spec['model_id'],
        '--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),
        '--backend','cuda','--registry',str(REGISTRY),'--expected-registry-sha256',digest(REGISTRY)]
    report={'scope':protocol['scope'],'allowed_partition':args.partition,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'freeze_sha256':args.expected_freeze_sha256,'frozen_source_ref':frozen['source_ref'],
        'model_id':spec['model_id'],'provider_command':command,'completed':False,'failure':None,
        'native_calls':0,'Avatar_application_turns':0,'lab_branch_outcomes':0,'groups':[],'warmups':[],
        'synthetic_rows_actual_SQLite_memory':True,'disk_durability_or_personal_data_claim':False,'cleanup_passed':False,
        'core_runtime':{'executable':sys.executable,'prefix':sys.prefix,'python_version':sys.version,
            'package_versions':{name:importlib.metadata.version(name) for name in ('openai','httpx','numpy')}}}
    write(args.output/'evaluation.json',report)
    provider=None;engine=None;requests=[];responses=[];context={}
    request_log=(args.output/'request-wire.jsonl').open('x')
    response_log=(args.output/'response-wire.jsonl').open('x')
    started=time.monotonic()
    with (args.output/'provider.log').open('x') as log:
        try:
            provider=subprocess.Popen(command,cwd=ROOT,env=environment(python),stdout=log,stderr=subprocess.STDOUT)
            report['provider_pid']=provider.pid;write(args.output/'evaluation.json',report)
            for _ in range(300):
                if ready.exists() or provider.poll() is not None:break
                time.sleep(1)
            if not ready.exists():raise RuntimeError('provider readiness failed')
            actual=read(ready)
            assert actual['backend']=='cuda' and actual['model_sha256']==spec['sha256']
            assert actual['model_revision']==spec['revision'] and actual['registry_sha256']==digest(REGISTRY)
            assert actual['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
            assert actual['tool_adapter_enabled'] and actual['tool_adapter_source_sha256']==frozen['sha256']['src/avatar/lab/native_tool_wire.py']
            assert actual['pid']==provider.pid and actual['process_gpu_mib_after_load']
            gpu_rows=processes()
            assert any(line.split(',')[0].strip()==str(provider.pid) and actual['chosen_gpu']['uuid'] in line for line in gpu_rows.splitlines())
            kernel={'pid':provider.pid,'cmdline':[n.decode() for n in Path(f'/proc/{provider.pid}/cmdline').read_bytes().split(b'\0')[:-1]],
                'gpu_processes':gpu_rows,'maps':Path(f'/proc/{provider.pid}/maps').read_text()}
            assert kernel['cmdline']==command
            libraries={Path(line.split()[-1]) for line in kernel['maps'].splitlines() if '/' in line and '.so' in line.split()[-1]}
            reference=read(RUNTIME)['files_sha256']
            kernel['mapped_frozen_libraries']={str(p):digest(p) for p in libraries if str(p) in reference}
            assert any('libggml-cuda.so' in n for n in kernel['mapped_frozen_libraries'])
            assert all(sha==reference[n] for n,sha in kernel['mapped_frozen_libraries'].items())
            write(args.output/'provider-kernel-proof.json',kernel)
            verify_freeze(args.freeze,args.expected_freeze_sha256,args.partition)
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
            for n in range(2):
                context.clear();context.update(phase='warmup',repetition=0,case=str(n+1))
                messages=[{'role':'user','content':'只回复“预热完成”。'}]
                if n==0:
                    warm={'reply':engine.chat(messages,temperature=0,max_tokens=32),'request_ordinal':len(requests)}
                else:
                    reply,events=collect_sdk_stream(engine._client,model=spec['model_id'],messages=messages,max_tokens=32)
                    warm={'reply':reply['content'],'SDK_stream_events':events,'request_ordinal':len(requests)}
                report['warmups'].append(warm)
            def on_context(value):
                context.clear();context.update(value)
            for repetition in range(1,frozen['repetitions']+1):
                group=sample_repetition(engine,protocol,protocol[args.partition+'_cases'],repetition,
                    args.output/f'repetition-{repetition}',on_context=on_context)
                assert group['completed_cases']==len(protocol[args.partition+'_cases'])
                report['groups'].append(group)
                report['lab_branch_outcomes']=sum(len(g['cases'])*3 for g in report['groups'])
                write(args.output/'evaluation.json',report)
                verify_freeze(args.freeze,args.expected_freeze_sha256,args.partition)
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
            report['request_trace_identity_matched']=(len(inferred)==len(requests) and all(r['request_body_sha256']==q['request_body_sha256'] for r,q in zip(inferred,requests)))
            branches=[b for g in report['groups'] for c in g['cases'] for b in c['arms'].values()]
            report['cases_total']=sum(len(g['cases']) for g in report['groups'])
            report['arm_task_scores']={v:sum(c['arms'][v]['final_expected_task_outcome'] for g in report['groups'] for c in g['cases']) for v in protocol['arms']}
            report['arm_model_calls']={v:sum(c['arms'][v]['model_used'] for g in report['groups'] for c in g['cases']) for v in protocol['arms']}
            report['arm_framework_skips']={v:sum(c['arms'][v]['framework_skipped_model'] for g in report['groups'] for c in g['cases']) for v in protocol['arms']}
            report['all_business_unchanged']=all(b['business_unchanged'] for b in branches)
            report['all_post_source_writes_absent']=all(b['no_post_source_writes'] for b in branches)
            report['status_business_SELECTs']=sum(b['status_business_SELECTs'] for b in branches)
            report['native_adapter_contract_failures']=sum(r['outcome']=='ToolWireError' for r in inferred)
            report['engineering_passed']=(report['completed'] and report['cleanup_passed'] and report['request_trace_identity_matched']
                and len(inferred)<=frozen['max_native_calls'] and all(r['outcome'] in ('completed','ToolWireError') and r['finish_reason']=='stop' for r in inferred))
            primary=[c['arms'][protocol['primary_candidate']] for g in report['groups'] for c in g['cases']]
            report['primary_invalid_attempts']=sum(bool(b['model_error'] or b['model_contract_error'] or b['result_kind']=='validation_failure') for b in primary)
            report['primary_gate_passed']=(report['engineering_passed'] and report['all_business_unchanged']
                and report['all_post_source_writes_absent'] and not report['primary_invalid_attempts']
                and report['arm_task_scores'][protocol['primary_candidate']]==report['cases_total']
                and all(b['scope_matches_expected'] for b in branches))
            report['overall_seconds_including_load_and_proof']=time.monotonic()-started
            report['source_current_after_execution']=all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
            report['actual_project_modules']={name:{'file':str(Path(module.__file__).resolve().relative_to(ROOT)),
                'sha256':digest(module.__file__)} for name,module in list(sys.modules.items()) if name.startswith('avatar') and getattr(module,'__file__',None) and Path(module.__file__).resolve().is_relative_to(ROOT)}
            report['artifacts_sha256']={str(p.relative_to(args.output)):digest(p) for p in args.output.rglob('*') if p.is_file() and p!=args.output/'evaluation.json'}
            write(args.output/'evaluation.json',report)
    print('C42 '+args.partition+':completed='+str(report['completed'])+';native='+str(report['native_calls'])+
          ';arms='+str(report['arm_task_scores'])+';cleanup='+str(report['cleanup_passed']))
    if not report['completed']:raise RuntimeError(report['failure'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--expected-freeze-sha256',required=True)
    parser.add_argument('--partition',choices=('development','protected'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())

"""Run one frozen diagnostic model with actual Avatar cognition and generation."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

from native_common import ROOT,BASE,WORK,REGISTRY,RUNTIME,WEIGHTS,CASES,PROTOCOL,read,digest,verify_freeze,environment_python,environment,collect_sdk_stream
from sample_history import sample_trial


def write(path,value):
    temporary = path.with_suffix(path.suffix+'.part')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    temporary.replace(path)


def processes():
    return subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory',
        '--format=csv,noheader,nounits'],text=True)


def run(args):
    short = {'qwen3-4b-q4_k_m':'4b','qwen3-14b-q4_k_m':'14b'}[args.model]
    output = args.output.resolve()
    if output.parent != BASE/'实验' or output.name != short+'-development-v1':
        raise ValueError('model-specific C48 development output required')
    frozen = verify_freeze(args.freeze,args.expected_freeze_sha256,args.model,output.name)
    output.mkdir(parents=True,exist_ok=False)
    spec = next(m for m in read(REGISTRY)['models'] if m['model_id'] == args.model)
    cases = read(CASES)['cases']; protocol = read(PROTOCOL)
    python = environment_python(native=True)
    model_path = ROOT/'models'/('qwen3-'+short+'-gguf')/spec['file']
    ready,trace = output/'provider-ready.json',output/'provider-trace.jsonl'
    command = [str(python),str(ROOT/'scripts/serve_local_model_eval.py'),'--model',str(model_path),
        '--model-key',args.model,'--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),
        '--backend','cuda','--registry',str(REGISTRY),'--expected-registry-sha256',digest(REGISTRY)]
    report = {'scope':protocol['scope'],'model_id':args.model,'freeze_sha256':args.expected_freeze_sha256,
        'frozen_source_ref':frozen['source_ref'],'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'provider_command':command,'completed':False,'failure':None,'groups':[],'warmups':[],
        'cleanup_passed':False,'actual_SDK_trials':0,'actual_query_turns':0,'actual_ordinary_turns':0,
        'actual_native_calls':0,'source_data':'synthetic records in actual in-memory SQLite; no personal/durability claim',
        'core_runtime':{'executable':sys.executable,'prefix':sys.prefix,'version':sys.version,
            'packages':{n:importlib.metadata.version(n) for n in ('openai','httpx','numpy')}}}
    write(output/'evaluation.json',report)
    provider = engine = None; requests,responses,context = [],[],{}
    request_log = (output/'request-wire.jsonl').open('x'); response_log = (output/'response-wire.jsonl').open('x')
    started = time.monotonic()
    def interrupted(signum,frame):
        raise KeyboardInterrupt('C48 signal '+str(signum))
    previous = {s:signal.signal(s,interrupted) for s in (signal.SIGINT,signal.SIGTERM)}
    with (output/'provider.log').open('x') as log:
        try:
            provider = subprocess.Popen(command,cwd=ROOT,env=environment(python),stdout=log,stderr=subprocess.STDOUT)
            report['provider_pid'] = provider.pid; write(output/'evaluation.json',report)
            for _ in range(300):
                if ready.exists() or provider.poll() is not None: break
                time.sleep(1)
            if not ready.exists(): raise RuntimeError('provider readiness failed')
            actual = read(ready)
            assert actual['backend'] == 'cuda' and actual['model_sha256'] == spec['sha256']
            assert actual['model_revision'] == spec['revision'] and actual['model_id'] == args.model
            assert actual['registry_sha256'] == digest(REGISTRY) and actual['pid'] == provider.pid
            assert actual['provider_source_sha256'] == frozen['sha256']['scripts/serve_local_model_eval.py']
            assert actual['resource_selector_sha256'] == frozen['sha256']['src/avatar/gpu_resources.py']
            assert actual['tool_adapter_enabled'] is False and actual['process_gpu_mib_after_load']
            assert actual['template_sha256'] == digest(WORK/(short+'-embedded-chat-template.jinja'))
            gpu_rows = processes()
            assert any(line.split(',')[0].strip() == str(provider.pid) and actual['chosen_gpu']['uuid'] in line for line in gpu_rows.splitlines())
            kernel = {'pid':provider.pid,'cmdline':[p.decode() for p in Path(f'/proc/{provider.pid}/cmdline').read_bytes().split(b'\0')[:-1]],
                'gpu_processes':gpu_rows,'maps':Path(f'/proc/{provider.pid}/maps').read_text()}
            assert kernel['cmdline'] == command
            libraries = {Path(line.split()[-1]) for line in kernel['maps'].splitlines() if '/' in line and '.so' in line.split()[-1]}
            reference = read(RUNTIME)['files_sha256']
            kernel['mapped_frozen_libraries'] = {str(p):digest(p) for p in libraries if str(p) in reference}
            assert any('libggml-cuda.so' in name for name in kernel['mapped_frozen_libraries'])
            assert all(sha == reference[name] for name,sha in kernel['mapped_frozen_libraries'].items())
            write(output/'provider-kernel-proof.json',kernel)
            verify_freeze(args.freeze,args.expected_freeze_sha256,args.model,output.name)
            import httpx
            from openai import OpenAI
            from avatar.brain.llm import LLMEngine
            def on_request(request):
                raw = request.read()
                row = {'ordinal':len(requests)+1,'context':dict(context),'request':json.loads(raw),
                    'request_body_sha256':hashlib.sha256(raw).hexdigest()}
                requests.append(row); request_log.write(json.dumps(row,ensure_ascii=False)+'\n'); request_log.flush()
            def on_response(response):
                row = {'ordinal':len(responses)+1,'context':dict(context),'status':response.status_code}
                if 'application/json' in response.headers.get('content-type',''):
                    row['body'] = json.loads(response.read())
                else: row['stream'] = True
                responses.append(row); response_log.write(json.dumps(row,ensure_ascii=False)+'\n'); response_log.flush()
            client = httpx.Client(trust_env=False,event_hooks={'request':[on_request],'response':[on_response]})
            engine = LLMEngine(base_url=actual['url'],api_key='local-eval-only',model=args.model,timeout=120,max_retries=0)
            engine._client.close(); engine._client = OpenAI(base_url=actual['url'],api_key='local-eval-only',
                timeout=120,max_retries=0,http_client=client)
            assert engine._client.max_retries == 0
            report['SDK_max_retries'] = engine._client.max_retries
            for index in range(2):
                context.clear(); context.update(phase='warmup',repetition=0,case=str(index+1),arm=None,call_role='warmup')
                messages = [{'role':'user','content':'只回复“预热完成”。'}]
                if index == 0:
                    warm = {'reply':engine.chat(messages,temperature=0,max_tokens=32),'request_ordinal':len(requests)}
                else:
                    reply,events = collect_sdk_stream(engine._client,model=args.model,messages=messages,max_tokens=32)
                    warm = {'reply':reply,'SDK_stream_events':events,'request_ordinal':len(requests)}
                report['warmups'].append(warm); write(output/'evaluation.json',report)
            def on_context(value):
                context.clear(); context.update(value)
            for repetition in range(1,4):
                folder = output/f'repetition-{repetition}'; folder.mkdir()
                group = {'repetition':repetition,'completed':False,'trials':[]}
                for index,case in enumerate(cases):
                    arms = protocol['arms'] if (index+repetition)%2 == 0 else list(reversed(protocol['arms']))
                    for arm in arms:
                        sub = folder/(case['id']+'-'+arm)
                        receipt = sample_trial(engine,case,arm,repetition,sub,on_context=on_context,native_counter=lambda:len(requests))
                        group['trials'].append({'case':case['id'],'case_group':case['group'],'arm':arm,'folder':str(sub.relative_to(output)),
                            'final_score':receipt['final_reply_score'],'raw_score':receipt['raw_generation_score'],
                            'model_modes_valid':receipt['model_modes_valid'],
                            'business_unchanged':receipt['business_unchanged_by_query_and_ordinary'],
                            'no_new_user_facts':receipt['no_new_user_facts']})
                        report['actual_SDK_trials'] += 1; report['actual_query_turns'] += receipt['actual_query_turns']; report['actual_ordinary_turns'] += 1
                        write(output/'evaluation.json',report)
                group['completed'] = True
                write(folder/'group.json',group); report['groups'].append(group)
                write(output/'evaluation.json',report)
                verify_freeze(args.freeze,args.expected_freeze_sha256,args.model,output.name)
                print(short,'repetition',repetition,'closed;native requests',len(requests),flush=True)
            report['completed'] = True
        except BaseException as error:
            report['failure'] = type(error).__name__+': '+str(error)[:500]
        finally:
            for sig,handler in previous.items(): signal.signal(sig,handler)
            if engine is not None: engine.close()
            request_log.close(); response_log.close()
            if provider is not None:
                if provider.poll() is None: provider.terminate()
                try: report['provider_exit_code'] = provider.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    provider.kill(); report['provider_exit_code'] = provider.wait(timeout=15)
                report['GPU_after_cleanup'] = processes()
                report['provider_proc_present_after_cleanup'] = Path(f'/proc/{provider.pid}').exists()
                report['cleanup_passed'] = (report['provider_exit_code'] == 0 and not report['provider_proc_present_after_cleanup']
                    and not any(line.split(',')[0].strip() == str(provider.pid) for line in report['GPU_after_cleanup'].splitlines()))
            all_trace = [json.loads(line) for line in trace.read_text().splitlines()] if trace.exists() else []
            inferred = [r for r in all_trace if r.get('id')]
            report['actual_native_calls'] = len(inferred)
            report['native_raw_stop_count'] = sum(r['finish_reason'] == 'stop' for r in inferred)
            report['requests_rejected_before_native'] = sum(r.get('kind') == 'request_rejected' for r in all_trace)
            report['request_trace_identity_matched'] = len(inferred) == len(requests) and all(r['request_body_sha256'] == q['request_body_sha256'] for r,q in zip(inferred,requests))
            report['transport_passed'] = (report['completed'] and report['cleanup_passed'] and report['request_trace_identity_matched']
                and len(inferred) == 146 and len(responses) == 146 and all(r['status'] == 200 for r in responses)
                and all(r['outcome'] == 'completed' for r in inferred))
            trials = [t for g in report['groups'] for t in g['trials']]
            report['arm_final_contract_scores'] = {a:sum(t['final_score']['task_correct'] for t in trials if t['arm'] == a) for a in protocol['arms']}
            report['arm_raw_contract_scores'] = {a:sum(t['raw_score']['task_correct'] for t in trials if t['arm'] == a) for a in protocol['arms']}
            report['arm_group_final_contract_scores'] = {a:{g:sum(t['final_score']['task_correct'] for t in trials if t['arm']==a and t['case_group']==g) for g in ('known_category_development_regression','new_development_reobservation_control')} for a in protocol['arms']}
            report['all_business_unchanged'] = all(t['business_unchanged'] for t in trials)
            report['all_no_new_user_facts'] = all(t['no_new_user_facts'] for t in trials)
            report['all_model_modes_valid'] = all(t['model_modes_valid'] for t in trials)
            report['primary_gate_passed'] = (report['transport_passed'] and report['native_raw_stop_count'] == 146
                and report['all_business_unchanged'] and report['all_no_new_user_facts'] and report['all_model_modes_valid']
                and report['arm_final_contract_scores'][protocol['primary_candidate']] == 36)
            report['actual_project_modules'] = {n:{'path':str(Path(m.__file__).resolve().relative_to(ROOT)),
                'sha256':digest(m.__file__)} for n,m in list(sys.modules.items()) if n.startswith('avatar') and getattr(m,'__file__',None) and Path(m.__file__).resolve().is_relative_to(ROOT)}
            report['frozen_current_after_execution'] = all(digest(ROOT/n) == sha for n,sha in frozen['sha256'].items())
            report['weight_sha256_after_execution'] = digest(model_path)
            report['weight_identity_after_execution'] = report['weight_sha256_after_execution'] == spec['sha256']
            report['primary_gate_passed'] = (report['primary_gate_passed'] and report['frozen_current_after_execution']
                and report['weight_identity_after_execution'])
            report['seconds_including_model_load_and_proof'] = time.monotonic()-started
            report['artifacts_sha256'] = {str(p.relative_to(output)):digest(p) for p in output.rglob('*') if p.is_file() and p.name != 'evaluation.json'}
            write(output/'evaluation.json',report)
    print('C48',short,'completed='+str(report['completed']),'native='+str(report['actual_native_calls']),
        'final='+str(report['arm_final_contract_scores']),'cleanup='+str(report['cleanup_passed']))
    if not report['completed']: raise RuntimeError(report['failure'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--expected-freeze-sha256',required=True)
    parser.add_argument('--model',choices=('qwen3-4b-q4_k_m','qwen3-14b-q4_k_m'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args())

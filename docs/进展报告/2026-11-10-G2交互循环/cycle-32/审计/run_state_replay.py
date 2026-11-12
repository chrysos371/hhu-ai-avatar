"""Serial known-SDK-wire replay under explicit owned-native state policies."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from state_common import ROOT,BASE,PROTOCOL,FIXTURES,RUNTIME,REGISTRY,MODELS,POLICIES,digest,verify_freeze,verify_historical_binding,verify_backend,validate_fixture_provenance
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'src'))
from probe_structured_provider import environment,validate_trace,gpu_processes,write
from evaluate_native_output_audit import validate_provider_identity
from serve_local_model_eval import load_registry
from avatar.gpu_resources import select_available_gpu


def send_raw(url,raw,row):
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.path!='/v1' or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Owned loopback endpoint required')
    wire=raw.encode();payload=json.loads(raw);row.update(request=payload,raw_request_json=raw,request_sha256=sha256(wire).hexdigest(),outcome='sending')
    request=Request(url+'/chat/completions',data=wire,headers={'Authorization':'Bearer local-eval-only','Content-Type':'application/json'})
    started=time.monotonic()
    try:
        try:
            with build_opener(ProxyHandler({})).open(request,timeout=180) as response:body=response.read();status=response.status
        except HTTPError as error:
            body=error.read();row.update(status=error.code,raw_http_body=body.decode(errors='replace'),response_body_sha256=sha256(body).hexdigest(),outcome='http_error');raise
        raw_body=body.decode();row.update(status=status,raw_http_body=raw_body,response_body_sha256=sha256(body).hexdigest(),outcome='decoding')
        if payload['stream']:
            chunks=[json.loads(line[6:]) for line in raw_body.splitlines() if line.startswith('data: ') and line!='data: [DONE]']
            if not chunks or 'data: [DONE]' not in raw_body:raise ValueError('Native stream lacks completed chunks')
            reply=''.join(c['choices'][0]['delta'].get('content','') or '' for c in chunks);ident=chunks[0]['id']
            reasons=[c['choices'][0]['finish_reason'] for c in chunks if c['choices'][0]['finish_reason'] is not None];finish=reasons[-1] if reasons else None
        else:
            value=json.loads(raw_body);reply=value['choices'][0]['message']['content'];ident=value['id'];finish=value['choices'][0]['finish_reason']
        row.update(reply=reply,provider_call_id=ident,finish_reason=finish,outcome='completed')
    except BaseException as error:row['error']=repr(error);raise
    finally:row['http_roundtrip_seconds']=time.monotonic()-started


def inventory():
    raw=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True)
    return raw,[dict(index=int(parts[0]),uuid=parts[1].strip(),free_mib=int(parts[2]),utilization_percent=int(parts[3])) for parts in (line.split(',') for line in raw.splitlines())]


def choose_gpu(required,preferred,pinned):
    raw,rows=inventory();visible=os.environ.get('CUDA_VISIBLE_DEVICES')
    if pinned:
        selected=select_available_gpu(rows,required_free_mib=required,visible_mask=pinned)
        if selected['uuid']!=pinned:raise ValueError('Pinned per-model device identity changed')
        return raw,selected,'pinned_same_model_policy'
    prior=next((r for r in rows if r['uuid']==preferred),None)
    if prior:
        try:return raw,select_available_gpu(rows,required_free_mib=required,visible_mask=visible,allowed_indices={prior['index']}),'retained_source_device_currently_admissible'
        except RuntimeError:pass
    return raw,select_available_gpu(rows,required_free_mib=required,visible_mask=visible),'current_headroom_fallback_historical_hardware_difference_recorded'


def validate_policy(policy,fixture):
    rows=policy['requests'];native=[json.loads(line) for line in Path(policy['trace_path']).read_text().splitlines()]
    assert len(rows)==len(native)==35;validate_trace(rows,native)
    for index,(row,actual) in enumerate(zip(rows,native,strict=True)):
        assert row['outcome']=='completed' and row['finish_reason']=='stop' and row['status']==200
        assert json.loads(row['raw_request_json'])==row['request'] and sha256(row['raw_request_json'].encode()).hexdigest()==row['request_sha256']==actual['request_body_sha256']
        assert sha256(row['raw_http_body'].encode()).hexdigest()==row['response_body_sha256']
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda v:sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if v is not None else None
        assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt) and actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)
        state=actual['state_observation'];name=policy['state_policy'];assert state['policy']==name
        before=state['logical_tokens_before_policy'];after=state['logical_tokens_after_policy'];end=state['logical_tokens_after_generation']
        assert type(before) is int and before>=0 and type(after) is int and after>=0 and type(end) is int and end>0
        if index==0:assert before==0
        else:assert before==native[index-1]['state_observation']['logical_tokens_after_generation']
        assert state['explicit_logical_reset_called']==(name!='reuse') and state['explicit_context_memory_clear_called']==(name=='memory_clear_reset')
        assert after==(before if name=='reuse' else 0) and state['general_physical_state_guarantee'] is False
        if row['role']=='replay':
            source=fixture['requests'][row['source_ordinal']];assert row['raw_request_json']==source['raw_request_json'] and row['request_sha256']==source['request_sha256']
    target=[r for r in rows if r.get('source_ordinal')==5];assert len(target)==6 and len({r['request_sha256'] for r in target})==1
    native_map={r['id']:r for r in native};assert len({native_map[r['provider_call_id']]['prompt_sha256'] for r in target})==1
    for chain in ('without_extra_cognitive','with_extra_cognitive'):
        for rep in (1,2,3):assert [r['source_ordinal'] for r in rows if r.get('chain')==chain and r.get('repetition')==rep]==fixture['chains'][chain]
    groups={chain:[r['reply'] for r in target if r['chain']==chain] for chain in fixture['chains']}
    return {'target_replies':groups,'unique_reply_count_by_chain':{key:len(set(values)) for key,values in groups.items()},
        'within_repeat_equal':[groups['without_extra_cognitive'][i]==groups['with_extra_cognitive'][i] for i in range(3)],
        'all6_target_unique_replies':sorted(set(r['reply'] for r in target)),
        'target_wire_sha256':target[0]['request_sha256'],'target_native_prompt_sha256':native_map[target[0]['provider_call_id']]['prompt_sha256'],
        'state_observations_bound':35,'raw_sender_schema_native_trace_verified':True,'general_determinism_or_root_cause_proved':False}


def prior_gate(args):
    if args.model!=MODELS[1]:return
    if args.prior_4b is None or not args.prior_4b_sha256 or digest(args.prior_4b)!=args.prior_4b_sha256:raise ValueError('32B requires pinned same-freeze completed105-call4B state replay')
    prior=json.loads(args.prior_4b.read_text())
    if (prior.get('model_id')!=MODELS[0] or prior.get('freeze_sha256')!=args.expected_freeze_sha256 or not prior.get('completed')
            or not prior.get('engineering_passed') or not prior.get('cleanup_passed') or len(prior.get('policies',[]))!=3):raise ValueError('4B state replay engineering gate failed')
    assert sum(len(p['requests']) for p in prior['policies'])==105 and len({p['provider_ready']['chosen_gpu']['uuid'] for p in prior['policies']})==1
    fixture=validate_fixture_provenance(MODELS[0])
    for policy in prior['policies']:
        assert policy['provider_exit']==0 and policy['cleanup_passed'] and not policy.get('forced_cleanup') and policy['native_trace_sha256']==digest(Path(policy['trace_path']))
        assert validate_policy(policy,fixture)==policy['observations']


def run(args):
    if not __debug__:raise ValueError('Run without Python optimization')
    frozen=verify_freeze(args.freeze,args.expected_freeze_sha256,args.model);verify_historical_binding(frozen);fixture=validate_fixture_provenance(args.model);prior_gate(args)
    backend=verify_backend(ROOT/RUNTIME,frozen['sha256'][RUNTIME]);protocol=json.loads((ROOT/PROTOCOL).read_text())
    registry,registry_sha,_=load_registry(ROOT/REGISTRY,expected_sha256=frozen['sha256'][REGISTRY]);spec=next(m for m in registry['models'] if m['model_id']==args.model)
    args.output.mkdir(parents=True,exist_ok=False);report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'model_id':args.model,
        'scope':protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':frozen,'fixture':fixture,'backend_runtime_identity_sha256':frozen['sha256'][RUNTIME],
        'actual_native_cuda':True,'avatar_or_sql_run':False,'policies':[],'completed':False,'engineering_passed':False,'cleanup_passed':False,'failure':None,'cleanup_errors':[],
        'production_activation_authorized':False,'semantic_approval':False,'historical_backend_binaries_not_retrospectively_proved_identical':True}
    def save():write(args.output/'replay.json',report)
    def verify():verify_freeze(args.freeze,args.expected_freeze_sha256,args.model)
    save();started=time.monotonic();states=[];pinned=None
    def stop(state):
        if state['record'].get('lifecycle_checked'):return
        process=state['process'];record=state['record']
        if process.poll() is None:process.terminate()
        try:record['provider_exit']=process.wait(timeout=60)
        except subprocess.TimeoutExpired:process.kill();record['provider_exit']=process.wait();record['forced_cleanup']=True
        state['log'].close()
        for _ in range(100):
            raw=gpu_processes()
            if not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines()):break
            time.sleep(.1)
        record['gpu_processes_after']=raw;closeout=state['folder']/'provider-closeout.json'
        record['provider_closeout']=json.loads(closeout.read_text()) if closeout.exists() else None
        marker=record['provider_closeout'];valid=(marker and marker['pid']==process.pid and marker['state_policy']==record['state_policy']
            and marker['runtime_files_verified_after']==len(backend['files_sha256']) and marker['backend_runtime_identity_sha256']==frozen['sha256'][RUNTIME]
            and marker['model_closed'] and marker['server_closed'])
        record['cleanup_passed']=bool(record['provider_exit']==0 and not record.get('forced_cleanup') and valid and not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines()))
        record['lifecycle_checked']=True;save()
    try:
        for name in protocol['policy_orders'][args.model]:
            verify();folder=args.output/name;folder.mkdir();ready=folder/'provider-ready.json';trace=folder/'provider-trace.jsonl'
            snapshot,choice,reason=choose_gpu(spec['required_free_mib'],fixture['source_gpu']['uuid'],pinned)
            if pinned is None:pinned=choice['uuid']
            command=[str(args.provider_python),str(BASE/'审计/serve_state_eval.py'),'--state-policy',name,
                '--backend-runtime-identity',str(ROOT/RUNTIME),'--expected-backend-runtime-sha256',frozen['sha256'][RUNTIME],
                '--model',str(ROOT/'models'/args.model.replace('-q4_k_m','-gguf')/spec['file']),'--model-key',args.model,'--metadata',str(ROOT/spec['metadata']),
                '--ready',str(ready),'--trace',str(trace),'--backend','cuda','--registry',str(ROOT/REGISTRY),'--expected-registry-sha256',registry_sha]
            record={'state_policy':name,'provider_command':command,'controller_gpu_snapshot':snapshot,'controller_choice':choice,'choice_reason':reason,
                'historical_gpu_uuid_equal':choice['uuid']==fixture['source_gpu']['uuid'],'requests':[],'provider_pid':None,'provider_exit':None,'completed':False,'cleanup_passed':False,'trace_path':str(trace.resolve())}
            report['policies'].append(record);save();log=(folder/'provider.log').open('x');process=None
            try:
                env=environment(args.provider_python);env['CUDA_VISIBLE_DEVICES']=pinned
                process=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT);record['provider_pid']=process.pid
                state={'process':process,'record':record,'folder':folder,'log':log};states.append(state);save()
                while True:
                    if process.poll() is not None:raise RuntimeError('State provider exited before readiness')
                    if ready.exists():
                        try:metadata=json.loads(ready.read_text());break
                        except json.JSONDecodeError:pass
                    time.sleep(.1)
                validate_provider_identity(metadata,{'models_registry':REGISTRY,'models_registry_sha256':registry_sha,'provider_backend':'cuda'})
                assert metadata['pid']==process.pid and metadata['model_id']==args.model and metadata['chosen_gpu']['uuid']==pinned
                assert metadata['provider_source_sha256']==frozen['sha256'][str((BASE/'审计/serve_state_eval.py').relative_to(ROOT))]
                assert metadata['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
                assert metadata['state_policy']==name and metadata['backend_runtime_identity_sha256']==frozen['sha256'][RUNTIME] and metadata['backend_runtime_files_verified']==len(backend['files_sha256']) and metadata['model_context_memory_present']
                for method in metadata['state_method_sources'].values():assert backend['files_sha256'][method['path']]==method['file_sha256']
                for key,value in {'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1,'repeat_penalty':1.0,'top_p':1.0,'top_k':0,'state_policy':name}.items():assert metadata['configuration'].get(key)==value
                record['provider_ready']=metadata;save();print('Ready',args.model,name,'GPU',metadata['chosen_gpu'],flush=True)
                for index,stream in enumerate(protocol['warmups']):
                    verify();payload={'model':args.model,'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16};row={'role':'warmup','warmup_index':index,'state_policy':name}
                    record['requests'].append(row);save()
                    try:send_raw(metadata['url'],json.dumps(payload,ensure_ascii=False),row)
                    finally:save()
                    if row['finish_reason']!='stop':raise RuntimeError('State warmup incomplete')
                for rep,order in enumerate(protocol['chain_orders'],1):
                    for chain in order:
                        for source_index in fixture['chains'][chain]:
                            verify();source=fixture['requests'][source_index];row={'role':'replay','state_policy':name,'repetition':rep,'chain':chain,'source_ordinal':source_index,'source_stage':source['role']}
                            record['requests'].append(row);save()
                            try:send_raw(metadata['url'],source['raw_request_json'],row)
                            finally:save()
                            if row['finish_reason']!='stop':raise RuntimeError('State replay native generation incomplete')
                        print(name,'rep',rep,chain,'final',record['requests'][-1]['reply'],flush=True)
                stop(state);assert record['cleanup_passed'];record['native_trace_sha256']=digest(trace);record['observations']=validate_policy(record,fixture);record['completed']=True;save()
            except BaseException as error:
                record['failure']=repr(error)
                if report['failure'] is None:report['failure']=repr(error)
                raise
            finally:
                if process is not None:
                    try:stop(state)
                    except BaseException as error:report['cleanup_errors'].append({'pid':process.pid,'error':repr(error)})
                else:log.close()
                save()
        verify();verify_backend(ROOT/RUNTIME,frozen['sha256'][RUNTIME]);assert len(report['policies'])==3 and all(p['completed'] and p['cleanup_passed'] for p in report['policies'])
        assert sum(len(p['requests']) for p in report['policies'])==105 and len({p['provider_ready']['chosen_gpu']['uuid'] for p in report['policies']})==1
        assert len({p['observations']['target_wire_sha256'] for p in report['policies']})==len({p['observations']['target_native_prompt_sha256'] for p in report['policies']})==1
        report['same_gpu_uuid_across_policies']=pinned;report['completed']=True;report['engineering_passed']=True;report['cleanup_passed']=not report['cleanup_errors']
    except BaseException as error:
        if report['failure'] is None:report['failure']=repr(error)
        raise
    finally:
        for state in states:
            try:stop(state)
            except BaseException as error:report['cleanup_errors'].append({'pid':state['process'].pid,'error':repr(error)})
        report['seconds']=time.monotonic()-started;save()
    print('Complete known-wire state replay',args.model,[(p['state_policy'],p['observations']['within_repeat_equal'],p['observations']['all6_target_unique_replies']) for p in report['policies']],'root cause not globally approved',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',required=True,choices=MODELS);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--freeze',required=True,type=Path);p.add_argument('--expected-freeze-sha256',required=True);p.add_argument('--provider-python',required=True,type=Path)
    p.add_argument('--prior-4b',type=Path);p.add_argument('--prior-4b-sha256');args=p.parse_args()
    signal.signal(signal.SIGTERM,lambda signum,frame:(_ for _ in ()).throw(KeyboardInterrupt('Owned state replay interrupted')))
    run(args)

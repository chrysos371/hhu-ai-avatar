"""C38 owned 4B paired development provider; original generation and plan identities separate."""
import argparse,json,os,re,subprocess,sys,time
from pathlib import Path
from native_common import ROOT,BASE,PROTOCOL,REGISTRY,RUNTIME,digest,read,verify_source,capture_runtime,environment_python,environment
from native_wire_relay import NativeWireRelay,parse_wire
from evaluate_native_output_audit import validate_provider_identity
from run_native_output_models import gpu_snapshot,gpu_processes,has_pid


def sampler_command(metadata, output, freeze, expected, repetition):
    return [sys.executable,str(BASE/'审计/sample_pairs.py'),'--provider',str(metadata),'--output',str(output/'sample'),
        '--wire',str(output/'wire.jsonl'),'--freeze',str(freeze.resolve()),
        '--expected-freeze-sha256',expected,'--repetition',str(repetition)]


def main(args):
    frozen=verify_source(args.freeze,args.expected_freeze_sha256,args.model)
    assert not args.run_tag or re.fullmatch(r'[a-z0-9_-]+',args.run_tag)
    assert args.model=='qwen3-4b-q4_k_m' and args.repetition in (1,2,3)
    output=BASE/'实验'/f'paired-4b-r{args.repetition}{"-"+args.run_tag if args.run_tag else ""}'
    output.mkdir(parents=True,exist_ok=False)
    target=output/'evaluation.json'
    report={'scope':'isolated_typed_gate_paired_development','source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'model_id':args.model,'repetition':args.repetition,'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':frozen,
        'provider_pid':None,'provider_exit':None,'sampler_pid':None,'sampler_exit':None,'relay_closed':False,
        'completed':False,'engineering_passed':False,'cleanup_passed':False,'failure':None,
        'actual_native_or_gpu':True,'per_case_app_os_restart_claim':False,'full_response_buffering_no_latency_claim':True,
        'semantic_or_production_approval':False,'application_results':0,'native_calls':0,'native_finish_counts':{},'quality_truncations':[]}
    def save():
        tmp=target.with_suffix('.tmp');tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');tmp.replace(target)
    save();process=None;worker=None;relay=None;failure=None
    try:
        runtime=capture_runtime();assert runtime['files_sha256']==read(RUNTIME)['files_sha256'];report['runtime_before']=runtime
        report['gpu_before']=gpu_snapshot();report['processes_before']=gpu_processes();save()
        registry=read(REGISTRY);spec=next(m for m in registry['models'] if m['model_id']==args.model)
        model=ROOT/'models'/args.model.replace('-q4_k_m','-gguf')/spec['file']
        ready=output/'provider-ready.json';trace=output/'provider-trace.jsonl';python=environment_python(native=True)
        command=[str(python),str(ROOT/'scripts/serve_local_model_eval.py'),'--model',str(model),'--model-key',args.model,
            '--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),'--backend','cuda',
            '--registry',str(REGISTRY),'--expected-registry-sha256',digest(REGISTRY)]
        report['provider_argv']=command
        with (output/'provider.log').open('x') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=environment(python),stdout=log,stderr=subprocess.STDOUT)
            report['provider_pid']=process.pid;save();started=time.monotonic()
            while True:
                if process.poll() is not None:raise RuntimeError('Owned provider exited before ready: '+str(process.returncode))
                if ready.exists():
                    try:native=read(ready)
                    except json.JSONDecodeError:native=None
                    if native is not None:break
                if time.monotonic()-started>180:raise RuntimeError('Owned provider readiness timeout')
                time.sleep(.1)
            assert native['pid']==process.pid;validate_provider_identity(native,read(PROTOCOL))
            report['provider_ready_sha256']=digest(ready);report['chosen_gpu']=native['chosen_gpu'];save()
            print(args.model,'r'+str(args.repetition),'ready GPU',native['chosen_gpu']['index'],'pid',process.pid,flush=True)
            with NativeWireRelay(native['url'],output/'wire.jsonl',actual_native=True) as relay:
                via=dict(native,url=relay.url,upstream_native_url=native['url'],full_wire_relay_buffered=True)
                metadata=output/'relay-provider-ready.json';metadata.write_text(json.dumps(via,ensure_ascii=False,indent=2)+'\n')
                sampler=sampler_command(metadata,output,args.freeze,args.expected_freeze_sha256,args.repetition)
                report['sampler_argv']=sampler;save()
                with (output/'sampler.log').open('x') as log:
                    worker=subprocess.Popen(sampler,cwd=ROOT,env=dict(os.environ,NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'),stdout=log,stderr=subprocess.STDOUT)
                    report['sampler_pid']=worker.pid;save();report['sampler_exit']=worker.wait();save()
            report['relay_closed']=relay.closed
            sample=read(output/'sample/sample.json')
            report['application_results']=sum(t['terminal']=='result' for c in sample['arms'] for t in c['turns'])
            native_rows=[json.loads(line) for line in trace.read_text().splitlines()]
            wire=[json.loads(line) for line in (output/'wire.jsonl').read_text().splitlines()]
            report['native_calls']=len(native_rows);report['wire_requests']=len(wire);save()
            assert len(native_rows)==len(wire)>=2
            parsed=[]
            for index,(row,actual) in enumerate(zip(wire,native_rows)):
                value=parse_wire(row);parsed.append(value)
                assert row['ordinal']==index+1 and actual['outcome']=='completed'
                assert row['request_body_sha256']==actual['request_body_sha256'] and row['request']['messages']==actual['messages']
                assert value['id']==actual['id'] and value['reply']==actual['response'] and value['finish_reason']==actual['finish_reason']
                assert actual['analysis']==bool(row['request'].get('response_format'))
                finish=value['finish_reason'];report['native_finish_counts'][finish]=report['native_finish_counts'].get(finish,0)+1
                if index>=2 and finish!='stop':report['quality_truncations'].append({'ordinal':index+1,'kind':row['kind'],'finish_reason':finish})
            assert report['sampler_exit']==0 and sample['engineering_passed'] and sample['completed']
            assert len(sample['arms'])==24 and report['application_results']==44
            mappings=[];assigned=[];counts={'warmup':2,'cognitive':0,'generation':0,'plan':0}
            for arm in sample['arms']:
                assert arm['completed'] and arm['failure'] is None and arm['server_closed']
                for turn in arm['turns']:
                    indices=[n-1 for n in turn['native_ordinals']];assigned.extend(indices)
                    kinds={}
                    for index in indices:
                        schema=wire[index]['request'].get('response_format',{}).get('json_schema',{}).get('name')
                        kind='plan' if schema=='avatar_lab_action_plan_v1' else 'cognitive' if schema=='avatar_cognitive_analysis' else 'generation'
                        kinds.setdefault(kind,[]).append(index);counts[kind]+=1
                    result=turn['result'];review=result.get('response_review')
                    gens=kinds.get('generation',[]);plans=kinds.get('plan',[])
                    if result['generation_mode'] in ('llm','reviewed_response'):
                        assert len(gens)==1
                        original=parsed[gens[0]]['reply']
                        if review is not None:assert review['original_draft']==original
                    else:assert not gens
                    if review is not None and review['plan_raw'] is not None:
                        assert len(plans)==1 and parsed[plans[0]]['reply']==review['plan_raw']
                    else:assert not plans
                    assert turn['final_display_reply']==result['reply']==turn['stored_assistants'][-1]['content']
                    if result['generation_mode'] in ('llm','reviewed_response'):assert turn['visible']==result['reply']
                    else:assert turn['visible'] in ('',result['reply'])
                    mappings.append({'case':arm['id'],'arm':arm['arm'],'input':turn['input'],
                        'native_ordinals':turn['native_ordinals'],'request_kinds':{k:[n+1 for n in v] for k,v in kinds.items()},
                        'generation_mode':result['generation_mode'],'fixed_renderer_used':bool(review and review['fixed_renderer_used'])})
            assert sorted(assigned)==list(range(2,len(wire)))
            assert sum(counts.values())==len(wire)
            report['turn_native_mapping']=mappings;report['native_kind_counts']=counts
            report['sample_sha256']=digest(output/'sample/sample.json')
            report['wire_sha256']=digest(output/'wire.jsonl');report['native_trace_sha256']=digest(trace)
            report['engineering_passed']=True
    except BaseException as error:
        failure=error;report['failure']=repr(error)
    finally:
        if relay is not None:report['relay_closed']=relay.closed
        report['forced_sampler_cleanup']=False
        if worker is not None and worker.poll() is None:
            worker.terminate();report['sampler_exit']=worker.wait();report['forced_sampler_cleanup']=True
        if process is not None:
            if process.poll() is None:process.terminate()
            report['provider_exit']=process.wait()
            for _ in range(100):
                raw=gpu_processes()
                if not has_pid(raw,process.pid):break
                time.sleep(.1)
            report['processes_after']=raw;report['gpu_after']=gpu_snapshot()
            report['cleanup_passed']=report['provider_exit']==0 and not has_pid(raw,process.pid) and (relay is None or relay.closed)
        # Failed samplers still count every recorded native call/application
        # result. Never leave a misleading zero simply because later parsing failed.
        trace_path=output/'provider-trace.jsonl'
        if trace_path.exists():
            observed=[json.loads(line) for line in trace_path.read_text().splitlines()]
            report['native_calls']=len(observed)
            report['observed_native_finish_counts']={}
            for row in observed:
                key=str(row.get('finish_reason'))
                report['observed_native_finish_counts'][key]=report['observed_native_finish_counts'].get(key,0)+1
        sample_path=output/'sample/sample.json'
        if sample_path.exists():
            partial=read(sample_path)
            report['application_results']=sum(t.get('terminal')=='result' for c in partial.get('arms',[]) for t in c.get('turns',[]))
        try:
            report['runtime_after']=capture_runtime()
            assert report['runtime_after']['files_sha256']==read(RUNTIME)['files_sha256']
            verify_source(args.freeze,args.expected_freeze_sha256,args.model)
        except BaseException as error:
            report['failure']=report['failure'] or repr(error);failure=failure or error
        report['completed']=report['engineering_passed'] and report['cleanup_passed'] and report['failure'] is None;save()
    if not report['completed']:raise RuntimeError('C38 native pair incomplete; raw data retained: '+str(report['failure'])) from failure
    print(args.model,'r'+str(args.repetition),'complete44app results;',report['native_calls'],'native calls;',len(report['quality_truncations']),'quality finish exceptions;provider clean',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',required=True,choices=('qwen3-4b-q4_k_m',));p.add_argument('--repetition',type=int,required=True,choices=(1,2,3))
    p.add_argument('--freeze',type=Path,required=True);p.add_argument('--expected-freeze-sha256',required=True);p.add_argument('--run-tag',default='')
    main(p.parse_args())

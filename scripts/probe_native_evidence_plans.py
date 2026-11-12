"""Frozen standalone finite-content comparison; never an Avatar release gate."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from native_evidence_plan import payload, render, decode
from probe_structured_provider import environment, request, validate_trace, schema_valid, gpu_processes, write
from evaluate_native_output_audit import validate_provider_identity
from serve_local_model_eval import load_registry

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL='evals/interaction/cycle-27/source-atom-content-protocol.json'
REGISTRY='evals/interaction/cycle-26/model-scale-registry.json'
MODELS=('qwen3-4b-q4_k_m','qwen3-32b-q4_k_m')


def digest(path):return sha256(path.read_bytes()).hexdigest()


def required_paths(root=ROOT):
    base={PROTOCOL,REGISTRY,'scripts/native_evidence_plan.py','scripts/probe_native_evidence_plans.py',
          'scripts/probe_structured_provider.py','scripts/evaluate_native_output_audit.py','scripts/serve_local_model_eval.py','src/avatar/gpu_resources.py'}
    base.update(str(p.relative_to(root)) for folder in ('src','tests') for p in (root/folder).rglob('*.py'))
    base.update('evals/interaction/cycle-26/model-metadata-'+label+'.json' for label in ('4b','14b','32b'))
    return base


def verify_freeze(path,expected,model,root=ROOT):
    if digest(path)!=expected:raise ValueError('Freeze descriptor identity changed')
    frozen=json.loads(path.read_text())
    if (frozen.get('scope')!='standalone_native_source_atom_content_diagnostic' or frozen.get('backend')!='cuda'
            or frozen.get('protocol')!=PROTOCOL or frozen.get('models')!=list(MODELS) or model not in MODELS
            or frozen.get('production_activation_authorized') is not False
            or frozen.get('prospective_execution_authorized') is not False
            or frozen.get('diagnostic_requests_per_model')!=24):raise ValueError('Frozen contract mismatch')
    if not required_paths(root)<=frozen.get('sha256',{}).keys():raise ValueError('Frozen inputs incomplete')
    for name,value in frozen['sha256'].items():
        p=root/name
        if not p.resolve().is_relative_to(root.resolve()) or digest(p)!=value:raise ValueError('Frozen input changed: '+name)
    return frozen


def validate_protocol(protocol):
    if (protocol.get('scope')!='standalone_native_source_atom_content_diagnostic' or protocol.get('backend')!='cuda'
            or protocol.get('registry')!=REGISTRY or protocol.get('models')!=list(MODELS)
            or protocol.get('production_activation_authorized') is not False or protocol.get('prospective_execution_authorized') is not False
            or protocol.get('gold_sent_to_model') is not False or protocol.get('same_messages_between_arms') is not True
            or protocol.get('diagnostic_requests_per_model')!=24 or protocol.get('arms')!=['plain','plan']
            or protocol.get('warmups')!=[False,True] or any(type(v) is not bool for v in protocol.get('warmups',[]))
            or len(protocol.get('cases',[]))!=12 or len(protocol.get('arm_orders',[]))!=12
            or len({c['id'] for c in protocol['cases']})!=12
            or any(sorted(order)!=['plain','plan'] for order in protocol['arm_orders'])):raise ValueError('Unexpected fixed protocol contract')
    for case in protocol['cases']:render(case['gold'],case['context'])


def validate_rows(rows,protocol,model):
    validate_protocol(protocol)
    expected=[]
    for index,stream in enumerate(protocol['warmups']):
        value={'model':model,'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16}
        expected.append((value,{'role':'warmup','warmup_index':index},None))
    for case,order in zip(protocol['cases'],protocol['arm_orders']):
        for arm in order:expected.append((payload(case,arm,model),{'role':'source_atom_diagnostic','case':case['id'],'arm':arm},case))
    if len(rows)!=len(expected):raise ValueError('Diagnostic request schedule incomplete')
    for row,(value,identity,case) in zip(rows,expected):
        if row.get('request')!=value or row.get('finish_reason')!='stop' or any(row.get(k)!=v for k,v in identity.items()):raise ValueError('Diagnostic request schedule changed')
        if identity.get('arm')=='plan':
            grade=grade_plan(row['reply'],case)
            if any(row.get(k)!=v for k,v in grade.items()):raise ValueError('Stored plan grade differs from raw reply')


def prior_gate(path,expected,prior_sha):
    if path is None or not prior_sha or digest(path)!=prior_sha:raise ValueError('32B requires pinned completed4B evidence')
    prior=json.loads(path.read_text());trace=path.parent/'provider-trace.jsonl'
    if (prior.get('freeze_sha256')!=expected or prior.get('model_id')!=MODELS[0] or not prior.get('completed')
            or not prior.get('engineering_passed') or not prior.get('cleanup_passed') or prior.get('provider_exit')!=0
            or prior.get('native_trace_sha256')!=digest(trace) or len(prior.get('requests',[]))!=26):raise ValueError('4B evidence incomplete')
    validate_trace(prior['requests'],[json.loads(x) for x in trace.read_text().splitlines()],require_request_identity=True)
    validate_rows(prior['requests'],json.loads((ROOT/PROTOCOL).read_text()),MODELS[0])
    plans=[row for row in prior['requests'] if row.get('arm')=='plan']
    if len(plans)!=12 or not all(row['declared_schema_valid'] for row in plans):raise ValueError('4B actual schema evidence incomplete')


def grade_plan(text,case):
    result={'declared_schema_valid':schema_valid(text,payload(case,'plan')['response_format']['json_schema']['schema']),
            'plan_exact':False,'render_passed':False,'rendered_task_exact':False,'rendered':None,'render_error':None}
    try:
        plan=decode(text);result['plan']=plan;result['plan_exact']=plan==case['gold']
        result['rendered']=render(plan,case['context']);result['render_passed']=True
        result['rendered_task_exact']=result['rendered']==render(case['gold'],case['context'])
    except (ValueError,KeyError,TypeError) as error:result['render_error']=repr(error)
    return result


def run(args):
    if not __debug__:raise ValueError('Run without Python optimization')
    frozen=verify_freeze(args.freeze,args.expected_freeze_sha256,args.model)
    if args.model==MODELS[1]:prior_gate(args.prior_4b,args.expected_freeze_sha256,args.prior_4b_sha256)
    protocol=json.loads((ROOT/PROTOCOL).read_text())
    validate_protocol(protocol)
    registry,registry_sha,_=load_registry(ROOT/REGISTRY,expected_sha256=frozen['sha256'][REGISTRY])
    spec=next(m for m in registry['models'] if m['model_id']==args.model)
    args.output.mkdir(parents=True,exist_ok=False)
    ready=args.output/'provider-ready.json';trace=args.output/'provider-trace.jsonl'
    command=[str(args.provider_python),str(ROOT/'scripts/serve_local_model_eval.py'),'--model',str(ROOT/'models'/args.model.replace('-q4_k_m','-gguf')/spec['file']),
             '--model-key',args.model,'--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),'--backend','cuda',
             '--registry',str(ROOT/REGISTRY),'--expected-registry-sha256',registry_sha]
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'model_id':args.model,
            'scope':protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':frozen,'provider_command':command,
            'requests':[],'completed':False,'failure':None,'engineering_passed':False,'semantic_approved':False,
            'cleanup_passed':False,'provider_pid':None,'provider_exit':None,'atoms_are_experiment_fixtures':True,
            'avatar_integration_run':False,'real_sql_commit_verified':False}
    def save():write(args.output/'probe.json',report)
    def verify():verify_freeze(args.freeze,args.expected_freeze_sha256,args.model)
    save();process=None;started=time.monotonic()
    try:
        verify()
        with (args.output/'provider.log').open('x') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=environment(args.provider_python),stdout=log,stderr=subprocess.STDOUT)
            report['provider_pid']=process.pid;save()
            while True:
                if process.poll() is not None:raise RuntimeError('Provider exited before ready')
                if ready.exists():
                    try:metadata=json.loads(ready.read_text());break
                    except json.JSONDecodeError:pass
                time.sleep(.1)
            validate_provider_identity(metadata,{'models_registry':REGISTRY,'models_registry_sha256':registry_sha,'provider_backend':'cuda'})
            if (metadata['pid']!=process.pid or metadata['model_id']!=args.model
                    or metadata['provider_source_sha256']!=frozen['sha256']['scripts/serve_local_model_eval.py']
                    or metadata['resource_selector_sha256']!=frozen['sha256']['src/avatar/gpu_resources.py']):raise ValueError('Runtime provider source/PID mismatch')
            expected={'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1}
            if any(metadata['configuration'].get(k)!=v for k,v in expected.items()):raise ValueError('Provider generation configuration changed')
            report['provider_ready']=metadata;save();print('Ready',args.model,'GPU',metadata['chosen_gpu'],flush=True)
            for index,stream in enumerate(protocol['warmups']):
                verify();value={'model':args.model,'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16}
                row=request(metadata['url'],value);row.update(role='warmup',warmup_index=index);report['requests'].append(row);save()
                if row['finish_reason']!='stop':raise RuntimeError('Native warmup incomplete')
            for case,order in zip(protocol['cases'],protocol['arm_orders']):
                for arm in order:
                    verify();row=request(metadata['url'],payload(case,arm,args.model));row.update(role='source_atom_diagnostic',case=case['id'],arm=arm)
                    if arm=='plan':row.update(grade_plan(row['reply'],case))
                    report['requests'].append(row);save()
                    if row['finish_reason']!='stop':raise RuntimeError('Native generation incomplete')
                    print(case['id'],arm,'completed',row.get('plan_exact'),row.get('render_passed'),flush=True)
        verify()
    except BaseException as error:report['failure']=repr(error);raise
    finally:
        if process is not None:
            if process.poll() is None:process.terminate()
            try:report['provider_exit']=process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();report['provider_exit']=process.wait();report['forced_cleanup']=True
            for _ in range(100):
                raw=gpu_processes()
                if not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines()):break
                time.sleep(.1)
            report['gpu_processes_after']=raw
            report['cleanup_passed']=report['provider_exit']==0 and not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines())
        report['seconds']=time.monotonic()-started;save()
    try:
        calls=[json.loads(line) for line in trace.read_text().splitlines()];validate_trace(report['requests'],calls,require_request_identity=True)
        validate_rows(report['requests'],protocol,args.model)
        report['native_trace_sha256']=digest(trace)
        for row in report['requests']:row['native_trace_matched']=True
        plans=[r for r in report['requests'] if r.get('arm')=='plan']
        report.update(schema_arms_passed=sum(r['declared_schema_valid'] for r in plans),plan_exact=sum(r['plan_exact'] for r in plans),
                      render_passed=sum(r['render_passed'] for r in plans),rendered_task_exact=sum(r['rendered_task_exact'] for r in plans))
        report['engineering_passed']=(len(report['requests'])==26 and len(plans)==12 and report['schema_arms_passed']==12
            and all(r['finish_reason']=='stop' for r in report['requests']) and report['cleanup_passed'])
        verify();report['completed']=True;save()
    except BaseException as error:report['failure']=repr(error);save();raise
    print('Complete schema',report['schema_arms_passed'],'plan_exact',report['plan_exact'],'rendered_task_exact',report['rendered_task_exact'],'/12; semantic approval false',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True,choices=MODELS);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--freeze',required=True,type=Path);parser.add_argument('--expected-freeze-sha256',required=True)
    parser.add_argument('--provider-python',required=True,type=Path);parser.add_argument('--prior-4b',type=Path);parser.add_argument('--prior-4b-sha256');options=parser.parse_args()
    def stop(signum,frame):raise KeyboardInterrupt('Owned diagnostic interrupted')
    signal.signal(signal.SIGTERM,stop);run(options)

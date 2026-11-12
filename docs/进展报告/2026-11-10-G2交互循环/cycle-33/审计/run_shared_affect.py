"""One real preparation per pair, two isolated SQLite clones and fresh OS probes."""
import argparse
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import build_opener,ProxyHandler
from shared_affect_common import ROOT,BASE,OLD31,OLD32,PROTOCOL,REGISTRY,RUNTIME,MODELS,ARMS,digest,verify_freeze,verify_historical_binding,verify_backend
from shared_snapshot import backup_pair,logical_dump
from run_state_replay import send_raw
from run_readonly_analysis_cost import CostContext
from run_native_context_use import NativeContext,parse_wire,normalize
from context_native_relay import NativeRelay
from run_context_baseline import save
from probe_structured_provider import environment,request,validate_trace,gpu_processes
from evaluate_native_output_audit import validate_provider_identity
from serve_local_model_eval import load_registry


def validate_calls(report):
    native=[json.loads(line) for line in (Path(report['output'])/'provider-trace.jsonl').read_text().splitlines()]
    rows=report['requests'];skipped=sum(c['probe_skipped'] for c in report['cases'] if c['role']=='probe')
    assert len(rows)==len(native)==386-skipped and 0<=skipped<=48;validate_trace(rows,native)
    validate_trace(rows[:2],native[:2],require_request_identity=True)
    for row,actual in zip(rows,native,strict=True):
        wire=row['raw_request_json'];assert json.loads(wire)==row['request'] and digest_bytes(wire)==row['request_sha256']==actual['request_body_sha256']
        assert digest_bytes(row['raw_http_body'])==row['response_body_sha256'] and row['finish_reason']=='stop'
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda v:digest_bytes(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))) if v is not None else None
        assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt) and actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)
        state=actual['state_observation'];assert state['policy']=='logical_reset' and state['logical_tokens_after_policy']==0 and state['explicit_logical_reset_called'] is True and state['explicit_context_memory_clear_called'] is False
    assert sum(r['kind']=='generation' for c in report['cases'] for r in c['model_requests'])==192
    return skipped


def digest_bytes(value):
    from hashlib import sha256
    return sha256(value.encode()).hexdigest()


def prior_gate(args):
    if args.model!=MODELS[1]:return
    if args.prior_4b is None or not args.prior_4b_sha256 or digest(args.prior_4b)!=args.prior_4b_sha256:raise ValueError('32B requires pinned completed same-freeze shared4B engineering evidence')
    report=json.loads(args.prior_4b.read_text())
    assert report['model_id']==MODELS[0] and report['freeze_sha256']==args.expected_freeze_sha256 and report['completed'] and report['engineering_passed'] and report['cleanup_passed']
    assert len(report['groups'])==48 and len(report['workers'])==144 and report['provider_exit']==0
    assert all(w['exit_code']==0 and not w['forced_cleanup'] for w in report['workers'])
    assert digest(args.prior_4b.parent/'provider-trace.jsonl')==report['native_trace_sha256'];validate_calls(report)


class SharedAffect(CostContext):
    def __init__(self,args):
        self.args=args;self.frozen=verify_freeze(args.freeze,args.expected_freeze_sha256,args.model);verify_historical_binding(self.frozen);prior_gate(args)
        self.backend=verify_backend(ROOT/RUNTIME,self.frozen['sha256'][RUNTIME]);self.protocol=json.loads((ROOT/PROTOCOL).read_text())
        args.output.mkdir(parents=True,exist_ok=False)
        self.report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'output':str(args.output.resolve()),'model_id':args.model,
            'scope':self.protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':self.frozen,'actual_llm_or_gpu':True,
            'groups':[],'cases':[],'workers':[],'http_calls':[],'requests':[],'warmups':[],'cleanup_errors':[],'completed':False,'engineering_passed':False,
            'semantic_approved':False,'production_activation_authorized':False,'failure':None,'cleanup_passed':False,'provider_pid':None,'provider_exit':None,
            'relay_buffers_full_response':True,'provider_policy':'logical_reset','shared_preparation_not_regenerated_per_arm':True}
        self.opener=build_opener(ProxyHandler({}));self.states=[];self.state=None;self.ready=None;self.persist()
    def verify(self):verify_freeze(self.args.freeze,self.args.expected_freeze_sha256,self.args.model)
    def start(self,optout=False):
        assert not optout;self.verify();number=len(self.report['workers'])+1
        ready=self.temporary/f'worker-{number}-ready.json';runtime=self.folder/f'worker-{number}-runtime.json'
        command=[sys.executable,str(BASE/'审计/shared_affect_worker.py'),'--db',str(self.db),'--ready',str(ready),'--runtime-out',str(runtime),
            '--provider-url',f'http://127.0.0.1:{self.relay.server_port}/v1','--freeze',str(self.args.freeze.resolve()),'--expected-freeze-sha256',self.args.expected_freeze_sha256,
            '--model',self.args.model,'--analysis-arm',self.case['arm']]
        log=(self.folder/f'worker-{number}.log').open('x');process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
        record={'case':self.case['id'],'pid':process.pid,'argv':command,'runtime_file':str(runtime.relative_to(self.args.output)),
            'exit_code':None,'forced_cleanup':False,'turns_completed':0,'recover_context':True,'analysis_arm':self.case['arm']}
        state={'process':process,'record':record,'runtime':runtime,'log':log};self.states.append(state);self.report['workers'].append(record);self.state=state;self.persist();started=time.monotonic()
        while not ready.exists():
            if process.poll() is not None:raise RuntimeError('Shared affect worker exited before readiness')
            if time.monotonic()-started>25:raise TimeoutError('Shared affect worker readiness timeout')
            time.sleep(.02)
        self.ready=json.loads(ready.read_text());assert self.ready['pid']==process.pid
        record['readiness']={k:v for k,v in self.ready.items() if k!='token'};self.persist()
    def stop(self,state=None):
        state=state or self.state
        if state is None or state['record'].get('analysis_runtime_verified'):return
        NativeContext.stop(self,state);record=state['record'];runtime=json.loads(state['runtime'].read_text())
        assert runtime['audit_analysis_arm']==record['analysis_arm'] and runtime['audit_analysis_hook']==(record['analysis_arm']==ARMS[1])
        assert set(runtime['initial_emotion'])=={'valence','arousal','user_valence','user_arousal'} and all(value==0 for value in runtime['initial_emotion'].values())
        source=runtime['audit_candidate_source']
        if record['analysis_arm']==ARMS[1]:assert Path(source['path']).resolve()==(OLD31/'readonly_analysis_candidate.py').resolve() and source['sha256']==self.frozen['sha256'][str(Path(source['path']).relative_to(ROOT))]
        else:assert source is None and runtime['audit_analysis_rows']==[]
        record.update(analysis_runtime_verified=True,analysis_rows=runtime['audit_analysis_rows'],initial_emotion=runtime['initial_emotion']);self.persist()
    def begin(self,text):
        self.verify();index=len(self.case['turns'])+1;started=time.monotonic_ns()
        accepted=self.query('/turns',{'request_id':f'c33_shared_{self.case["id"]}_{index:03d}','text':text,'use_web':False})
        row={'input':text,'accepted':accepted,'job_id':accepted['body']['data']['job_id'],'app_pid':self.state['process'].pid,'client_submit_started_ns':started}
        self.case['turns'].append(row);self.persist();return row
    def segment(self,group,case,role,arm,texts,db):
        self.db=db;self.folder=self.args.output/group['id']/(role if role=='preparation' else arm);self.folder.mkdir()
        self.case={'id':group['id']+'_'+(role if role=='preparation' else arm),'case_id':case['id'],'repetition':group['repetition'],'role':role,'arm':arm,
            'turns':[],'checks':[],'snapshots':[],'external_operations':[],'complete':False,'owned_runtime_dir':str(self.temporary),'probe_skipped':False}
        self.report['cases'].append(self.case);self.state=None;start=len(self.relay.rows);self.persist()
        try:
            if role=='probe':
                self.snapshot('initial');initial=logical_dump(self.db)
                assert digest_bytes(initial)==group['backup']['initial_logical_dump_sha256']
                (self.folder/'initial-database_dump.sql').write_text(initial)
            self.start()
            for text in texts:
                result=self.turn(text);assert result['generation_mode']=='llm'
                assert result['analysis_mode'] in ({'llm','lab_readonly_context_rules'} if role=='probe' and arm==ARMS[1] else {'llm'})
            self.stop();snapshot=self.snapshot('final')
            (self.folder/'database_dump.sql').write_text(logical_dump(self.db))
            rows=[parse_wire(deepcopy(row)) for row in self.relay.rows[start:]];skipped=result['analysis_mode']=='lab_readonly_context_rules'
            assert len(rows)==2*len(texts)-int(skipped) and sum(r['kind']=='generation' for r in rows)==len(texts) and all(r['finish_reason']=='stop' for r in rows)
            analysis_rows=self.state['record']['analysis_rows']
            if arm==ARMS[1]:assert len(analysis_rows)==1 and analysis_rows[0]['decision']['eligible']==skipped
            else:assert analysis_rows==[]
            if role=='probe':
                expected=group['shared_role_messages'];generation=next(r for r in rows if r['kind']=='generation')
                assert generation['request']['messages'][1:-1]==expected and generation['request']['messages'][-1]=={'role':'user','content':case['probe']}
                if not skipped:assert next(r for r in rows if r['kind']=='cognitive')['request']['messages'][1:-1]==expected
                assert len(snapshot['memory_messages'])==6
                aid=result['conversation']['assistant_message_id'];sources={r['source_id'] for r in snapshot['memory_response_context'] if r['message_id']==aid and r['source_type']=='message'}
                assert {m['id'] for m in snapshot['memory_messages'] if m['id']!=aid}<=sources
                self.case.update(strict_code_correct=result['reply'].strip()==case['expected_code'],probe_messages=generation['request']['messages'])
            else:assert len(snapshot['memory_messages'])==4
            assert not snapshot['memory_reminders'] and not snapshot['memory_action_receipts']
            self.case.update(probe_skipped=skipped,analysis_rows=analysis_rows,model_requests=rows,complete=True)
        finally:
            if self.state is not None:
                try:self.stop()
                except BaseException as error:self.report['cleanup_errors'].append({'case':self.case['id'],'error':repr(error)})
            raw=[deepcopy(row) for row in self.relay.rows[start:]];self.case['raw_model_requests']=raw
            self.report['requests'].extend(parse_wire(row) for row in raw if row.get('outcome')=='completed' and row.get('http_status')==200);self.persist()
        save(self.folder/'segment-completed.json',self.case);return self.case
    def run_group(self,case,rep,order):
        self.verify();identifier=f'r{rep}_{case["id"]}';folder=self.args.output/identifier;folder.mkdir()
        self.temporary=Path(tempfile.mkdtemp(prefix='c33-context-',dir=ROOT.parent/'runtime/tmp'));preparation=self.temporary/'preparation.db'
        group={'id':identifier,'case_id':case['id'],'repetition':rep,'stratum':case['stratum'],'arm_order':order,'complete':False,'owned_runtime_dir':str(self.temporary)}
        self.report['groups'].append(group);self.persist()
        prepared=self.segment(group,case,'preparation',ARMS[0],case['shared_preparation'],preparation)
        expected=[]
        for turn in prepared['turns']:expected.extend([{'role':'user','content':turn['input']},{'role':'assistant','content':turn['result']['reply']}])
        group['preparation_case']=prepared['id'];group['shared_role_messages']=expected
        targets={arm:self.temporary/(arm+'.db') for arm in ARMS}
        assert self.state['record']['exit_code']==0 and self.state['process'].poll()==0
        group['backup']=backup_pair(preparation,[targets[arm] for arm in ARMS],preparation_worker_closed=True);self.persist()
        original=logical_dump(preparation);probes={}
        for arm in order:
            assert digest_bytes(logical_dump(targets[arm]))==group['backup']['initial_logical_dump_sha256']
            probes[arm]=self.segment(group,case,'probe',arm,[case['probe']],targets[arm])
            assert logical_dump(preparation)==original
        before,after=[probes[arm]['turns'][-1]['result'] for arm in ARMS];fields=('user_valence','user_arousal','user_emotion','valence','arousal','emotion','strategy','style')
        group.update(probe_cases={arm:probes[arm]['id'] for arm in ARMS},actual_candidate_skipped=probes[ARMS[1]]['probe_skipped'],
            observed_fields={arm:{field:probes[arm]['turns'][-1]['result'][field] for field in fields} for arm in ARMS},
            raw_replies_identical=before['reply']==after['reply'],differing_fields=[field for field in fields if before[field]!=after[field]],
            strict_code_correct=[probes[arm]['strict_code_correct'] for arm in ARMS],complete=True)
        save(folder/'group-completed.json',group);self.persist()
        print(identifier,'skip',group['actual_candidate_skipped'],'different_fields',group['differing_fields'],'strict',group['strict_code_correct'],flush=True)
    def run(self):
        registry,registry_sha,_=load_registry(ROOT/REGISTRY,expected_sha256=self.frozen['sha256'][REGISTRY]);spec=next(m for m in registry['models'] if m['model_id']==self.args.model)
        ready=self.args.output/'provider-ready.json';trace=self.args.output/'provider-trace.jsonl'
        command=[str(self.args.provider_python),str(OLD32/'serve_state_eval.py'),'--state-policy','logical_reset',
            '--backend-runtime-identity',str(ROOT/RUNTIME),'--expected-backend-runtime-sha256',self.frozen['sha256'][RUNTIME],
            '--model',str(ROOT/'models'/self.args.model.replace('-q4_k_m','-gguf')/spec['file']),'--model-key',self.args.model,
            '--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),'--backend','cuda','--registry',str(ROOT/REGISTRY),'--expected-registry-sha256',registry_sha]
        self.report['provider_command']=command;process=None;relay_thread=None;started=time.monotonic();self.persist()
        try:
            with (self.args.output/'provider.log').open('x') as log:
                self.verify();process=subprocess.Popen(command,cwd=ROOT,env=environment(self.args.provider_python),stdout=log,stderr=subprocess.STDOUT);self.report['provider_pid']=process.pid;self.persist()
                while True:
                    if process.poll() is not None:raise RuntimeError('Shared affect native provider exited before readiness')
                    if ready.exists():
                        try:metadata=json.loads(ready.read_text());break
                        except json.JSONDecodeError:pass
                    time.sleep(.1)
                validate_provider_identity(metadata,{'models_registry':REGISTRY,'models_registry_sha256':registry_sha,'provider_backend':'cuda'})
                assert metadata['pid']==process.pid and metadata['model_id']==self.args.model
                assert metadata['provider_source_sha256']==self.frozen['sha256'][str((OLD32/'serve_state_eval.py').relative_to(ROOT))]
                assert metadata['resource_selector_sha256']==self.frozen['sha256']['src/avatar/gpu_resources.py']
                assert metadata['backend_runtime_identity_sha256']==self.frozen['sha256'][RUNTIME] and metadata['backend_runtime_files_verified']==54 and metadata['model_context_memory_present']
                for method in metadata['state_method_sources'].values():assert self.backend['files_sha256'][method['path']]==method['file_sha256']
                for key,value in {'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1,'repeat_penalty':1.0,'top_p':1.0,'top_k':0,'state_policy':'logical_reset'}.items():assert metadata['configuration'][key]==value
                self.report['provider_ready']=metadata;self.persist();print('Ready shared affect',self.args.model,metadata['chosen_gpu'],flush=True)
                for index,stream in enumerate(self.protocol['warmups']):
                    self.verify();payload={'model':self.args.model,'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16}
                    row={'role':'warmup','warmup_index':index};self.report['warmups'].append(row);self.report['requests'].append(row);self.persist()
                    try:send_raw(metadata['url'],json.dumps(payload,ensure_ascii=False),row)
                    finally:self.persist()
                    assert row['finish_reason']=='stop'
                self.relay=NativeRelay(metadata['url']);relay_thread=threading.Thread(target=self.relay.serve_forever,daemon=True);relay_thread.start()
                for rep,orders in enumerate(self.protocol['case_arm_orders'],1):
                    for case,order in zip(self.protocol['cases'],orders,strict=True):self.run_group(case,rep,order)
                self.verify()
        except BaseException as error:self.report['failure']=repr(error);raise
        finally:
            for state in self.states:
                try:self.stop(state)
                except BaseException as error:self.report['cleanup_errors'].append({'pid':state['process'].pid,'error':repr(error)})
            if relay_thread:self.relay.shutdown();relay_thread.join(10);self.relay.server_close()
            if process is not None:
                if process.poll() is None:process.terminate()
                try:self.report['provider_exit']=process.wait(timeout=60)
                except subprocess.TimeoutExpired:process.kill();self.report['provider_exit']=process.wait();self.report['provider_forced_cleanup']=True
                for _ in range(100):
                    raw=gpu_processes()
                    if not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines()):break
                    time.sleep(.1)
                self.report['gpu_processes_after']=raw;closeout=self.args.output/'provider-closeout.json';marker=json.loads(closeout.read_text()) if closeout.exists() else None
                self.report['provider_closeout']=marker
                valid=(marker and marker['pid']==process.pid and marker['state_policy']=='logical_reset' and marker['model_closed'] and marker['server_closed']
                    and marker['backend_runtime_identity_sha256']==self.frozen['sha256'][RUNTIME] and marker['runtime_files_verified_after']==54)
                self.report['cleanup_passed']=bool(valid and self.report['provider_exit']==0 and not self.report.get('provider_forced_cleanup') and not self.report['cleanup_errors']
                    and not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines()))
            self.report['seconds']=time.monotonic()-started;self.persist()
        try:
            skipped=validate_calls(self.report);self.report['native_trace_sha256']=digest(trace)
            assert len(self.report['workers'])==144 and len(self.report['cases'])==144 and len(self.report['groups'])==48 and all(g['complete'] for g in self.report['groups'])
            assert all(c['complete'] for c in self.report['cases']) and all(w['exit_code']==0 and not w['forced_cleanup'] for w in self.report['workers']) and self.report['cleanup_passed']
            assert sum(len(c['turns']) for c in self.report['cases'])==192
            self.verify();verify_backend(ROOT/RUNTIME,self.frozen['sha256'][RUNTIME])
            self.report.update(actual_candidate_skips=skipped,engineering_passed=True,completed=True);self.persist()
        except BaseException as error:self.report['failure']=repr(error);self.persist();raise
        print('Complete shared affect',self.args.model,'192app turns/144OS/48pairs; actual native',len(self.report['requests']),'skips',skipped,'semantic approval false',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True,choices=MODELS);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--freeze',required=True,type=Path);parser.add_argument('--expected-freeze-sha256',required=True);parser.add_argument('--provider-python',required=True,type=Path)
    parser.add_argument('--prior-4b',type=Path);parser.add_argument('--prior-4b-sha256');args=parser.parse_args()
    if not __debug__:raise ValueError('Run without Python optimization')
    signal.signal(signal.SIGTERM,lambda signum,frame:(_ for _ in ()).throw(KeyboardInterrupt('Owned shared affect experiment interrupted')))
    SharedAffect(args).run()

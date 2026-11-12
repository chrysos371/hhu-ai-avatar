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
                self.case.update(strict_code_correct=normalize(result['reply'],literal=True)==case['expected_code'],probe_messages=generation['request']['messages'])
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

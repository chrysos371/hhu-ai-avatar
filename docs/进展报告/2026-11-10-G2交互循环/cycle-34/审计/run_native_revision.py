"""Known live emotion-source deletion regression, before/after immutable sources."""
import argparse
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import build_opener,ProxyHandler
from revision_common import ROOT,BASE,OLD33,OLD32,PROTOCOL,REGISTRY,RUNTIME,MODELS,PHASES,digest,verify_freeze,verify_historical_binding,verify_backend
from run_shared_affect import SharedAffect
from run_native_context_use import NativeContext,parse_wire
from context_native_relay import NativeRelay
from run_state_replay import send_raw
from probe_structured_provider import environment,validate_trace,gpu_processes
from evaluate_native_output_audit import validate_provider_identity
from serve_local_model_eval import load_registry
from avatar.brain.memory import MemoryStore


def validate_calls(report):
    trace=[json.loads(line) for line in (Path(report['output'])/'provider-trace.jsonl').read_text().splitlines()];rows=report['requests']
    assert len(rows)==len(trace)==8;validate_trace(rows,trace);validate_trace(rows[:2],trace[:2],require_request_identity=True)
    previous=0
    for row,actual in zip(rows,trace,strict=True):
        assert hash_text(row['raw_request_json'])==row['request_sha256']==actual['request_body_sha256'] and json.loads(row['raw_request_json'])==row['request']
        assert hash_text(row['raw_http_body'])==row['response_body_sha256'] and row['finish_reason']=='stop'
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda value:hash_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))) if value is not None else None
        assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt) and actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)
        state=actual['state_observation'];assert state['policy']=='logical_reset' and state['logical_tokens_before_policy']==previous and state['logical_tokens_after_policy']==0 and state['explicit_logical_reset_called'] and not state['explicit_context_memory_clear_called']
        previous=state['logical_tokens_after_generation'];assert type(previous) is int and previous>0


def hash_text(value):
    from hashlib import sha256
    return sha256(value.encode()).hexdigest()


def gate(args):
    if args.model==MODELS[1]:
        if args.prior_4b is None or not args.prior_4b_sha256 or digest(args.prior_4b)!=args.prior_4b_sha256:raise ValueError('32B requires same-phase completed4B engineering proof')
        prior=json.loads(args.prior_4b.read_text());assert prior['model_id']==MODELS[0] and prior['phase']==args.phase and prior['freeze_sha256']==args.expected_freeze_sha256 and prior['completed'] and prior['engineering_passed'] and prior['cleanup_passed'];validate_calls(prior)
    if args.phase=='after':
        if args.before is None or not args.before_sha256 or digest(args.before)!=args.before_sha256:raise ValueError('After requires pinned same-model completed before evidence')
        before=json.loads(args.before.read_text());assert before['phase']=='before' and before['model_id']==args.model and before['completed'] and before['cleanup_passed'];validate_calls(before)


class RevisionAudit(SharedAffect):
    def __init__(self,args):
        self.args=args;self.frozen=verify_freeze(args.freeze,args.expected_freeze_sha256,args.model,phase=args.phase);verify_historical_binding(self.frozen);gate(args)
        self.backend=verify_backend(ROOT/RUNTIME,self.frozen['sha256'][RUNTIME]);self.protocol=json.loads((ROOT/PROTOCOL).read_text());args.output.mkdir(parents=True,exist_ok=False)
        self.folder=args.output/'application';self.folder.mkdir();self.temporary=Path(tempfile.mkdtemp(prefix='c34-emotion-'+args.phase+'-',dir=ROOT.parent/'runtime/tmp'));self.db=self.temporary/'owned.db'
        self.case={'id':'c34_'+args.phase+'_'+args.model,'turns':[],'checks':[],'snapshots':[],'external_operations':[],'emotions':{},'complete':False,'owned_runtime_dir':str(self.temporary)}
        self.report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'output':str(args.output.resolve()),'phase':args.phase,'model_id':args.model,
            'scope':self.protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':self.frozen,'actual_llm_or_gpu':True,'cases':[self.case],
            'workers':[],'http_calls':[],'requests':[],'warmups':[],'cleanup_errors':[],'completed':False,'engineering_passed':False,'cleanup_passed':False,'failure':None,
            'provider_pid':None,'provider_exit':None,'production_candidate_activation_authorized':False,'general_semantic_or_human_quality_approved':False}
        if args.before is not None:self.report.update(before_path=str(args.before.resolve()),before_sha256=args.before_sha256)
        self.states=[];self.state=None;self.ready=None;self.opener=build_opener(ProxyHandler({}));self.persist()
    def verify(self):verify_freeze(self.args.freeze,self.args.expected_freeze_sha256,self.args.model,phase=self.args.phase)
    def start(self,optout=False):
        assert not optout;self.verify();ready=self.temporary/'worker-ready.json';runtime=self.folder/'worker-runtime.json'
        command=[sys.executable,str(BASE/'审计/revision_worker.py'),'--phase',self.args.phase,'--db',str(self.db),'--ready',str(ready),'--runtime-out',str(runtime),
            '--provider-url',f'http://127.0.0.1:{self.relay.server_port}/v1','--freeze',str(self.args.freeze.resolve()),'--expected-freeze-sha256',self.args.expected_freeze_sha256,'--model',self.args.model]
        log=(self.folder/'worker.log').open('x');process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
        record={'case':self.case['id'],'pid':process.pid,'argv':command,'runtime_file':str(runtime.relative_to(self.args.output)),'exit_code':None,'forced_cleanup':False,'turns_completed':0,'recover_context':True}
        state={'process':process,'record':record,'runtime':runtime,'log':log};self.states.append(state);self.report['workers'].append(record);self.state=state;self.persist();started=time.monotonic()
        while not ready.exists():
            if process.poll() is not None:raise RuntimeError('Revision worker exited before readiness')
            if time.monotonic()-started>25:raise TimeoutError('Revision worker readiness timeout')
            time.sleep(.02)
        self.ready=json.loads(ready.read_text());assert self.ready['pid']==process.pid;record['readiness']={key:value for key,value in self.ready.items() if key!='token'};self.persist()
    def stop(self,state=None):
        state=state or self.state
        if state is None or state['record'].get('revision_runtime_verified'):return
        NativeContext.stop(self,state);runtime=json.loads(state['runtime'].read_text());assert runtime['phase']==self.args.phase
        state['record']['revision_runtime_verified']=True;self.persist()
    def emotion(self,label):
        value=self.query('/emotion')['body']['data'];self.case['emotions'][label]=value;self.persist();return value
    def workflow(self):
        self.start();self.emotion('initial')
        for text in self.protocol['native_fixed_source']:
            result=self.turn(text);assert result['analysis_mode']==result['generation_mode']=='llm'
        prepared=self.emotion('prepared');self.snapshot('prepared')
        source=self.case['turns'][-1]['result']['conversation']['user_message_id']
        with closing(MemoryStore(str(self.db))) as writer:
            revision=writer.context_revision;fragment=writer.remember('C34受控情绪来源标识。',source_message_id=source);writer.forget(fragment);current=writer.context_revision
        state=self.snapshot('forgotten');assert current==revision+1 and next(row for row in state['memory_messages'] if row['id']==source)['content']=='[redacted]'
        self.case['external_operations'].append({'kind':'independent_writer_forget','source_message_id':source,'fragment_id':fragment,'revision_before':revision,'revision_after':current})
        forgotten=self.emotion('forgotten')
        control=self.turn(self.protocol['native_after_forget_turns'][0]);assert control['analysis_mode']==control['generation_mode']=='rules_speaker_control';self.emotion('confirmed')
        neutral=self.turn(self.protocol['native_after_forget_turns'][1]);assert neutral['analysis_mode']==neutral['generation_mode']=='llm';self.emotion('neutral');self.snapshot('final');self.stop()
        rows=[parse_wire(deepcopy(row)) for row in self.relay.rows];assert len(rows)==6 and sum(row['kind']=='generation' for row in rows)==3 and all(row['finish_reason']=='stop' for row in rows)
        cue=self.protocol['native_fixed_source'][-1]
        assert all(cue not in json.dumps(row['request'],ensure_ascii=False) for row in rows[-2:])
        nonzero=lambda values:any(abs(values[key])>1e-9 for key in ('valence','arousal'))
        self.case.update(model_requests=rows,complete=True,observations={'prepared_nonzero_automatic':nonzero(prepared['automatic']),
            'prepared_nonzero_user_observation':nonzero(prepared['user_observation']),'automatic_zero_after_forget':not nonzero(forgotten['automatic']),
            'user_observation_zero_after_forget':not nonzero(forgotten['user_observation']),'erased_cue_absent_after_forget_sdk':True,
            'neutral_result_character_pad':[neutral['valence'],neutral['arousal']],'neutral_result_user_observation':[neutral['user_valence'],neutral['user_arousal']],
            'human_emotion_truth_or_quality_claim':False})
        self.persist();print(self.args.phase,self.args.model,self.case['observations'],flush=True)

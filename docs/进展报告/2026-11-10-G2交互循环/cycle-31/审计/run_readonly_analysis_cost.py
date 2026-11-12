"""Three fixed repetitions of source-bound readonly-analysis latency/protection."""
import argparse
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from analysis_cost_common import ROOT,BASE,OLD30,PROTOCOL,REGISTRY,MODELS,ARMS,digest,verify_freeze,verify_historical_binding
sys.path.insert(0,str(OLD30));sys.path.insert(0,str(ROOT/'scripts'))
from run_native_context_use import NativeContext,parse_wire,normalize
from context_native_relay import NativeRelay
from run_context_baseline import save,events
from probe_structured_provider import environment,request,validate_trace,gpu_processes
from evaluate_native_output_audit import validate_provider_identity
from serve_local_model_eval import load_registry


def grade(text,case,protocol):
    if case.get('metric')=='missing_abstention':
        import re
        return {'correct':any(v in text for v in protocol['missing_abstention_patterns']) and not re.search(r'\d{5,}',text),'target_present':None}
    return {'correct':normalize(text)==normalize(case['expected']),'target_present':case['expected'] in text,'forbidden_old_value':bool(case.get('forbidden') and case['forbidden'] in text)}


def percentile(values,p):
    values=sorted(values);position=(len(values)-1)*p;lo=int(position);hi=min(lo+1,len(values)-1)
    return values[lo]+(values[hi]-values[lo])*(position-lo)


def calculate_pairs(report,protocol):
    groups={}
    for c in report['cases']:groups.setdefault((c['repetition'],c['case_id']),{})[c['arm']]=c
    pairs=[];quality=True
    for (rep,case_id),arms in groups.items():
        a=arms[ARMS[0]];z=arms[ARMS[1]];case=next(c for c in protocol['cases'] if c['id']==case_id)
        before=a['turns'][-1]['result'];after=z['turns'][-1]['result']
        strict_no_regression=not a['grade']['correct'] or bool(z['grade']['correct'])
        source_no_regression=not a['grade'].get('target_present') or bool(z['grade'].get('target_present'))
        protected=not case['candidate_probe_eligible'];affect_fields=('user_valence','user_arousal','user_emotion','strategy','style')
        protected_equal=not protected or (all(before[k]==after[k] for k in affect_fields) and a['profile']==z['profile'] and a['facts_signature']==z['facts_signature'])
        # Identical raw replies avoid silently approving a different answer with
        # the same target substring. Non-identical pairs require later review.
        raw_equal=before['reply']==after['reply']
        quality=quality and strict_no_regression and source_no_regression and protected_equal and raw_equal
        pairs.append({'repetition':rep,'case':case_id,'template_readonly':case['candidate_probe_eligible'],
            'actual_candidate_skipped':z['probe_skipped'],'strict_no_regression':strict_no_regression,'source_no_regression':source_no_regression,
            'protected_affect_profile_facts_equal':protected_equal,'raw_probe_replies_identical':raw_equal,
            'strict_correct':[bool(a['grade']['correct']),bool(z['grade']['correct'])],
            'seconds':[a['turns'][-1]['submit_to_terminal_seconds'],z['turns'][-1]['submit_to_terminal_seconds']],
            'probe_replies':[before['reply'],after['reply']]})
    selected=[p for p in pairs if p['template_readonly']];assert len(selected)==18
    stats={}
    for arm,index in zip(ARMS,(0,1)):
        values=[p['seconds'][index] for p in selected]
        stats[arm]={'pairs':18,'median_seconds':statistics.median(values),'p95_seconds_linear':percentile(values,.95),
            'per_repeat':[{'repetition':rep,'pairs':6,'median_seconds':statistics.median(p['seconds'][index] for p in selected if p['repetition']==rep)} for rep in (1,2,3)]}
    improvement=1-stats[ARMS[1]]['median_seconds']/stats[ARMS[0]]['median_seconds']
    return {'pairs':pairs,'quality_gate_passed':bool(quality),'conservative_raw_equality_gate':True,'latency':stats,
        'median_relative_improvement':improvement,'bounded_performance_gate_passed':bool(quality and improvement>=.15),
        'all18_template_pairs_retained':True,'general_speed_or_quality_claim':False}


def validate_native_calls(report,native):
    rows=report['requests'];validate_trace(rows,native);validate_trace(rows[:2],native[:2],require_request_identity=True)
    skipped=sum(c['probe_skipped'] for c in report['cases']);assert 0<=skipped<=18 and len(rows)==len(native)==290-skipped
    assert sum(r['kind']=='generation' for c in report['cases'] for r in c['model_requests'])==144
    for row,actual in zip(rows[2:],native[2:],strict=True):
        assert json.loads(row['raw_request_json'])==row['request']
        assert sha256(row['raw_request_json'].encode()).hexdigest()==row['request_body_sha256']==actual['request_body_sha256']
        assert sha256(row['raw_http_body'].encode()).hexdigest()==row['response_body_sha256'] and row['finish_reason']=='stop'
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda value:sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value is not None else None
        assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt) and actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)


def prior_gate(args):
    if args.model!=MODELS[1]:return
    if args.prior_4b is None or not args.prior_4b_sha256 or digest(args.prior_4b)!=args.prior_4b_sha256:raise ValueError('32B requires pinned completed4B readonly protection evidence')
    data=json.loads(args.prior_4b.read_text());trace=args.prior_4b.parent/'provider-trace.jsonl'
    if (data.get('model_id')!=MODELS[0] or data.get('freeze_sha256')!=args.expected_freeze_sha256 or not data.get('completed')
            or not data.get('engineering_passed') or not data.get('cleanup_passed') or not data.get('comparison',{}).get('quality_gate_passed')
            or data.get('provider_exit')!=0 or len(data.get('workers',[]))!=96 or data.get('native_trace_sha256')!=digest(trace)):
        raise ValueError('4B readonly engineering/protection/no-regression gate failed')
    validate_native_calls(data,[json.loads(line) for line in trace.read_text().splitlines()])


class CostContext(NativeContext):
    def __init__(self,args):
        self.args=args;self.frozen=verify_freeze(args.freeze,args.expected_freeze_sha256,args.model);verify_historical_binding(self.frozen);prior_gate(args)
        self.protocol=json.loads((ROOT/PROTOCOL).read_text());args.output.mkdir(parents=True,exist_ok=False)
        self.report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'model_id':args.model,
            'scope':self.protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':self.frozen,
            'historical_git_inputs_verified_before_output':True,'actual_llm_or_gpu':True,'cases':[],'workers':[],'http_calls':[],
            'requests':[],'warmups':[],'cleanup_errors':[],'completed':False,'engineering_passed':False,'semantic_approved':False,
            'failure':None,'cleanup_passed':False,'provider_pid':None,'provider_exit':None,'relay_buffers_full_response':True,
            'candidate_only_audit_hook':True,'production_activation_authorized':False}
        self.opener=build_opener(ProxyHandler({}));self.states=[];self.state=None;self.ready=None;self.persist()
    def verify(self):verify_freeze(self.args.freeze,self.args.expected_freeze_sha256,self.args.model)
    def query(self,route,value=None):
        req=Request(self.ready['base_url']+route,data=None if value is None else json.dumps(value,ensure_ascii=False).encode(),
                    headers={'X-Avatar-Token':self.ready['token'],'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=60) as response:raw=response.read().decode();status=response.status
            self.report['http_calls'].append({'case':self.case['id'],'route':route,'request':value,'status':status,'raw_body':raw})
            return {'status':status,'body':json.loads(raw)}
        except HTTPError as error:
            self.report['http_calls'].append({'case':self.case['id'],'route':route,'request':value,'status':error.code,'raw_body':error.read().decode(errors='replace')});self.persist();raise
    def start(self,optout=False):
        assert not optout;self.verify();n=len(self.report['workers'])+1
        ready=self.temporary/f'worker-{n}-ready.json';runtime=self.folder/f'worker-{n}-runtime.json'
        command=[sys.executable,str(BASE/'审计/analysis_cost_worker.py'),'--db',str(self.db),'--ready',str(ready),'--runtime-out',str(runtime),
            '--provider-url',f'http://127.0.0.1:{self.relay.server_port}/v1','--freeze',str(self.args.freeze.resolve()),'--expected-freeze-sha256',self.args.expected_freeze_sha256,
            '--model',self.args.model,'--analysis-arm',self.case['arm']]
        log=(self.folder/f'worker-{n}.log').open('x');p=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
        record={'case':self.case['id'],'pid':p.pid,'argv':command,'runtime_file':str(runtime.relative_to(self.args.output)),
                'exit_code':None,'forced_cleanup':False,'turns_completed':0,'recover_context':True,'analysis_arm':self.case['arm']}
        state={'process':p,'record':record,'runtime':runtime,'log':log};self.states.append(state);self.report['workers'].append(record);self.state=state;self.persist();tick=time.monotonic()
        while not ready.exists():
            if p.poll() is not None:raise RuntimeError('Readonly app exited before readiness')
            if time.monotonic()-tick>25:raise TimeoutError('Readonly app readiness timeout')
            time.sleep(.02)
        self.ready=json.loads(ready.read_text());assert self.ready['pid']==p.pid;record['readiness']={k:v for k,v in self.ready.items() if k!='token'};self.persist()
    def stop(self,state=None):
        state=state or self.state
        if state is None or state['record'].get('analysis_runtime_verified'):return
        super().stop(state);record=state['record'];runtime=json.loads(state['runtime'].read_text())
        assert runtime['audit_analysis_arm']==record['analysis_arm'] and runtime['audit_analysis_hook']==(record['analysis_arm']==ARMS[1])
        source=runtime['audit_candidate_source']
        if record['analysis_arm']==ARMS[1]:assert source['sha256']==self.frozen['sha256'][str(Path(source['path']).relative_to(ROOT))]
        else:assert source is None and runtime['audit_analysis_rows']==[]
        record['analysis_runtime_verified']=True;record['analysis_rows']=runtime['audit_analysis_rows'];self.persist()
    def begin(self,text):
        self.verify();idx=len(self.case['turns'])+1;started=time.monotonic_ns()
        accepted=self.query('/turns',{'request_id':f'c31_cost_{self.case["id"]}_turn_{idx:03d}','text':text,'use_web':False})
        row={'input':text,'accepted':accepted,'job_id':accepted['body']['data']['job_id'],'app_pid':self.state['process'].pid,'client_submit_started_ns':started}
        self.case['turns'].append(row);return row
    def finish(self,row):
        req=Request(self.ready['base_url']+'/turns/'+row['job_id']+'/events',headers={'X-Avatar-Token':self.ready['token']})
        with self.opener.open(req,timeout=60) as response:kind,result,observed,raw=events(response,time.perf_counter())
        ended=time.monotonic_ns();row.update(terminal=kind,result=result,events=observed,raw_sse=raw,client_terminal_ns=ended,
            submit_to_terminal_seconds=(ended-row['client_submit_started_ns'])/1e9)
        row['conversation']=self.query('/conversation')
        if kind=='result':
            assert ''.join(e['data']['text'] for e in observed if e['event']=='text')==result['reply'];self.state['record']['turns_completed']+=1
        self.persist();return row
    def run_case(self,case,arm,rep):
        self.verify();identifier=f'r{rep}_{case["id"]}_{arm}';self.folder=self.args.output/identifier;self.folder.mkdir()
        self.temporary=Path(tempfile.mkdtemp(prefix='c31-context-',dir=ROOT.parent/'runtime/tmp'));self.db=self.temporary/'owned.db'
        self.case={'id':identifier,'case_id':case['id'],'repetition':rep,'arm':arm,'turns':[],'checks':[],'snapshots':[],
            'external_operations':[],'complete':False,'owned_runtime_dir':str(self.temporary),'probe_skipped':False}
        self.report['cases'].append(self.case);self.state=None;start=len(self.relay.rows)
        try:
            self.start()
            for index,text in enumerate(case['turns']):
                if index==2:self.restart()
                result=self.turn(text)
                assert result['generation_mode']=='llm'
                allowed={'llm','lab_readonly_context_rules'} if index==2 and arm==ARMS[1] and case['candidate_probe_eligible'] else {'llm'}
                assert result['analysis_mode'] in allowed
            self.stop();state=self.snapshot('final')
            with closing(sqlite3.connect('file:'+str(self.db)+'?mode=ro',uri=True)) as conn:(self.folder/'database_dump.sql').write_text('\n'.join(conn.iterdump())+'\n')
            rows=[parse_wire(deepcopy(r)) for r in self.relay.rows[start:]];gens=[r for r in rows if r['kind']=='generation']
            skipped=self.case['turns'][-1]['result']['analysis_mode']=='lab_readonly_context_rules';self.case['probe_skipped']=skipped
            assert len(rows)==6-int(skipped) and len(gens)==3 and all(r['finish_reason']=='stop' for r in rows)
            expected=[]
            for t in self.case['turns'][:2]:expected.extend([{'role':'user','content':t['input']},{'role':'assistant','content':t['result']['reply']}])
            assert gens[-1]['request']['messages'][1:-1]==expected and gens[-1]['request']['messages'][-1]=={'role':'user','content':case['turns'][-1]}
            assert len(state['memory_messages'])==6 and not state['memory_reminders'] and not state['memory_action_receipts']
            result=self.case['turns'][-1]['result'];aid=result['conversation']['assistant_message_id'];deps={r['source_id'] for r in state['memory_response_context'] if r['message_id']==aid and r['source_type']=='message'}
            assert {m['id'] for m in state['memory_messages'] if m['id']!=aid}<=deps
            profile={}
            for fragment in state['memory_fragments']:
                if fragment.get('profile_key') and fragment.get('status')=='active':profile[fragment['profile_key']]=fragment['content']
            if 'expected_profile_name' in case:
                assert any(case['expected_profile_name'] in value for value in profile.values())
                assert any(s['source_message_id']==5 and case['expected_profile_name'] in s['evidence'] for s in state['memory_sources'])
            analysis_rows=[r for w in self.report['workers'] if w['case']==identifier for r in w.get('analysis_rows',[])]
            if arm==ARMS[1]:assert len(analysis_rows)==3 and sum(r['decision']['eligible'] for r in analysis_rows)==int(skipped)
            else:assert analysis_rows==[]
            self.case.update(model_requests=rows,probe_messages=gens[-1]['request']['messages'],history_role_messages_verified=4,
                profile=profile,facts_signature=sorted((f['memory_type'],f['category'],f['content'],f['status']) for f in state['memory_fragments']),
                grade=grade(result['reply'],case,self.protocol),analysis_rows=analysis_rows,complete=True)
        finally:
            for state in self.states:
                try:self.stop(state)
                except BaseException as error:self.report['cleanup_errors'].append({'pid':state['process'].pid,'error':repr(error)})
            self.case['model_requests']=[deepcopy(r) for r in self.relay.rows[start:]]
            self.report['requests'].extend(parse_wire(deepcopy(r)) for r in self.relay.rows[start:] if r.get('outcome')=='completed' and r.get('http_status')==200)
            self.persist()
        print('rep',rep,case['id'],arm,'skipped',skipped,'strict',self.case['grade']['correct'],'seconds',self.case['turns'][-1]['submit_to_terminal_seconds'],flush=True)
    def run(self):
        registry,registry_sha,_=load_registry(ROOT/REGISTRY,expected_sha256=self.frozen['sha256'][REGISTRY]);spec=next(m for m in registry['models'] if m['model_id']==self.args.model)
        ready=self.args.output/'provider-ready.json';trace=self.args.output/'provider-trace.jsonl'
        command=[str(self.args.provider_python),str(ROOT/'scripts/serve_local_model_eval.py'),'--model',str(ROOT/'models'/self.args.model.replace('-q4_k_m','-gguf')/spec['file']),
            '--model-key',self.args.model,'--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),'--backend','cuda','--registry',str(ROOT/REGISTRY),'--expected-registry-sha256',registry_sha]
        self.report['provider_command']=command;process=None;relay_thread=None;tick=time.monotonic();self.persist()
        try:
            with (self.args.output/'provider.log').open('x') as log:
                self.verify();process=subprocess.Popen(command,cwd=ROOT,env=environment(self.args.provider_python),stdout=log,stderr=subprocess.STDOUT);self.report['provider_pid']=process.pid;self.persist()
                while True:
                    if process.poll() is not None:raise RuntimeError('Readonly native provider exited before readiness')
                    if ready.exists():
                        try:metadata=json.loads(ready.read_text());break
                        except json.JSONDecodeError:pass
                    time.sleep(.1)
                validate_provider_identity(metadata,{'models_registry':REGISTRY,'models_registry_sha256':registry_sha,'provider_backend':'cuda'})
                assert metadata['pid']==process.pid and metadata['model_id']==self.args.model and metadata['provider_source_sha256']==self.frozen['sha256']['scripts/serve_local_model_eval.py']
                assert metadata['resource_selector_sha256']==self.frozen['sha256']['src/avatar/gpu_resources.py']
                for key,value in {'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1}.items():assert metadata['configuration'].get(key)==value
                self.report['provider_ready']=metadata;self.persist();print('Ready',self.args.model,metadata['chosen_gpu'],flush=True)
                for index,stream in enumerate(self.protocol['warmups']):
                    self.verify();payload={'model':self.args.model,'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16}
                    row=request(metadata['url'],payload);row.update(role='warmup',warmup_index=index);self.report['warmups'].append(row);self.report['requests'].append(row);self.persist();assert row['finish_reason']=='stop'
                self.relay=NativeRelay(metadata['url']);relay_thread=threading.Thread(target=self.relay.serve_forever,daemon=True);relay_thread.start()
                for rep,orders in enumerate(self.protocol['case_arm_orders'],1):
                    for case,order in zip(self.protocol['cases'],orders,strict=True):
                        for arm in order:self.run_case(case,arm,rep)
                self.verify()
        except BaseException as error:self.report['failure']=repr(error);raise
        finally:
            for state in self.states:
                try:self.stop(state)
                except BaseException as error:self.report['cleanup_errors'].append({'pid':state['process'].pid,'error':repr(error)})
            if relay_thread:self.relay.shutdown();relay_thread.join(10);self.relay.server_close()
            if process is not None:
                if process.poll() is None:process.terminate()
                try:self.report['provider_exit']=process.wait(timeout=15)
                except subprocess.TimeoutExpired:process.kill();self.report['provider_exit']=process.wait();self.report['provider_forced_cleanup']=True
                for _ in range(100):
                    raw=gpu_processes()
                    if not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines()):break
                    time.sleep(.1)
                self.report['gpu_processes_after']=raw;self.report['cleanup_passed']=self.report['provider_exit']==0 and not self.report.get('provider_forced_cleanup') and not self.report['cleanup_errors'] and not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines())
            self.report['seconds']=time.monotonic()-tick;self.persist()
        try:
            validate_native_calls(self.report,[json.loads(line) for line in trace.read_text().splitlines()]);self.report['native_trace_sha256']=digest(trace)
            assert len(self.report['workers'])==96 and len(self.report['cases'])==48 and all(c['complete'] for c in self.report['cases']) and self.report['cleanup_passed']
            self.report['comparison']=calculate_pairs(self.report,self.protocol);self.verify();self.report['engineering_passed']=True;self.report['completed']=True;self.persist()
        except BaseException as error:self.report['failure']=repr(error);self.persist();raise
        print('Complete;quality',self.report['comparison']['quality_gate_passed'],'median relative improvement',self.report['comparison']['median_relative_improvement'],'activation false',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',required=True,choices=MODELS);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--freeze',required=True,type=Path);p.add_argument('--expected-freeze-sha256',required=True);p.add_argument('--provider-python',required=True,type=Path)
    p.add_argument('--prior-4b',type=Path);p.add_argument('--prior-4b-sha256');args=p.parse_args()
    signal.signal(signal.SIGTERM,lambda signum,frame:(_ for _ in ()).throw(KeyboardInterrupt('Owned readonly experiment interrupted')))
    CostContext(args).run()

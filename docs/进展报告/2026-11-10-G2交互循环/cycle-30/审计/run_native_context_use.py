"""Source-frozen native model use of real Web/OS recovered role history."""
import argparse
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import build_opener,ProxyHandler
from context_native_common import ROOT,BASE,OLD,PROTOCOL,REGISTRY,MODELS,ARMS,digest,verify_freeze
from context_native_relay import NativeRelay
sys.path.insert(0,str(OLD));sys.path.insert(0,str(ROOT/'scripts'))
from run_context_fault_controls import Harness
from run_context_baseline import save
from probe_structured_provider import environment,request,validate_trace,gpu_processes
from evaluate_native_output_audit import validate_provider_identity
from serve_local_model_eval import load_registry


def normalize(text,*,literal=False):
    value=text.strip()
    quotes={'“':'”','「':'」','"':'"',"'":"'",'‘':'’','《':'》'}
    while len(value)>=2 and value[0] in quotes and value[-1]==quotes[value[0]]:value=value[1:-1].strip()
    return value if literal else value.rstrip('。.!！?？').strip()


def grade(reply,case):
    if case['metric']=='missing_abstention':
        protocol=json.loads((ROOT/PROTOCOL).read_text())
        abstain=any(s in reply for s in protocol['missing_abstention_patterns'])
        digits=bool(re.search(r'\d{5,}',reply))
        return {'correct':abstain and not digits,'abstained':abstain,'phone_like_digits':digits,'kind':'missing_abstention'}
    exact=normalize(reply,literal=case['id']=='literal_quote')==normalize(case['expected'],literal=case['id']=='literal_quote')
    return {'correct':exact,'target_present':case['expected'] in reply,'forbidden_old_value':bool(case.get('forbidden') and case['forbidden'] in reply),'kind':case['metric']}


def parse_wire(row):
    assert row['http_status']==200 and row['outcome']=='completed'
    raw=row['raw_http_body']
    if row['request'].get('stream'):
        chunks=[json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ') and line!='data: [DONE]']
        assert chunks and 'data: [DONE]' in raw
        text=''.join(c['choices'][0]['delta'].get('content','') for c in chunks)
        reasons=[c['choices'][0]['finish_reason'] for c in chunks if c['choices'][0]['finish_reason'] is not None]
        ident=chunks[0]['id'];finish=reasons[-1] if reasons else None
    else:
        body=json.loads(raw);text=body['choices'][0]['message']['content'];ident=body['id'];finish=body['choices'][0]['finish_reason']
    return {**row,'reply':text,'provider_call_id':ident,'finish_reason':finish,'request_sha256':row['request_body_sha256'],'raw_sender_identity':True}


def validate_native_calls(report,trace):
    rows=report['requests'];validate_trace(rows,trace)
    assert len(rows)==len(trace)==74
    validate_trace(rows[:2],trace[:2],require_request_identity=True)
    for row,native in zip(rows[2:],trace[2:],strict=True):
        assert json.loads(row['raw_request_json'])==row['request']
        assert sha256(row['raw_request_json'].encode()).hexdigest()==row['request_body_sha256']==native['request_body_sha256']
        assert sha256(row['raw_http_body'].encode()).hexdigest()==row['response_body_sha256']
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda value:sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value is not None else None
        assert native['response_format']==fmt and native['response_format_sha256']==canonical(fmt)
        assert native['response_schema_sha256']==canonical(schema) and native['grammar_enabled']==bool(fmt)
        assert row['finish_reason']=='stop' and row['actual_llm_or_gpu'] is True


def prior_gate(args):
    if args.model!=MODELS[1]:return
    if args.prior_4b is None or not args.prior_4b_sha256 or digest(args.prior_4b)!=args.prior_4b_sha256:raise ValueError('32B requires pinned same-freeze complete4B evidence')
    prior=json.loads(args.prior_4b.read_text());trace=args.prior_4b.parent/'provider-trace.jsonl'
    if (prior.get('model_id')!=MODELS[0] or prior.get('freeze_sha256')!=args.expected_freeze_sha256
            or not prior.get('completed') or not prior.get('engineering_passed') or not prior.get('cleanup_passed')
            or prior.get('provider_exit')!=0 or len(prior.get('workers',[]))!=24 or digest(trace)!=prior.get('native_trace_sha256')):raise ValueError('4B engineering gate failed')
    assert all(w['exit_code']==0 and not w['forced_cleanup'] for w in prior['workers'])
    validate_native_calls(prior,[json.loads(line) for line in trace.read_text().splitlines()])


class NativeContext(Harness):
    def __init__(self,args):
        self.args=args;self.frozen=verify_freeze(args.freeze,args.expected_freeze_sha256,args.model);prior_gate(args)
        self.protocol=json.loads((ROOT/PROTOCOL).read_text());args.output.mkdir(parents=True,exist_ok=False)
        self.report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'model_id':args.model,
            'scope':self.protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':self.frozen,
            'actual_llm_or_gpu':True,'cases':[],'workers':[],'http_calls':[],'requests':[],'warmups':[],
            'cleanup_errors':[],'completed':False,'failure':None,'engineering_passed':False,'semantic_approved':False,
            'cleanup_passed':False,'provider_pid':None,'provider_exit':None,'relay_buffers_full_response':True}
        self.opener=build_opener(ProxyHandler({}));self.states=[];self.state=None;self.ready=None;self.persist()
    def persist(self):save(self.args.output/'evaluation.json',self.report)
    def verify(self):verify_freeze(self.args.freeze,self.args.expected_freeze_sha256,self.args.model)
    def start(self,optout=False):
        self.verify();n=len(self.report['workers'])+1;ready=self.temporary/f'worker-{n}-ready.json';runtime=self.folder/f'worker-{n}-runtime.json'
        command=[sys.executable,str(BASE/'审计/context_native_worker.py'),'--db',str(self.db),'--ready',str(ready),'--runtime-out',str(runtime),
                 '--provider-url',f'http://127.0.0.1:{self.relay.server_port}/v1','--freeze',str(self.args.freeze.resolve()),
                 '--expected-freeze-sha256',self.args.expected_freeze_sha256,'--model',self.args.model]+(['--no-context-recovery'] if optout else [])
        log=(self.folder/f'worker-{n}.log').open('x');p=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
              env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
        record={'case':self.case['id'],'pid':p.pid,'argv':command,'runtime_file':str(runtime.relative_to(self.args.output)),
                'exit_code':None,'forced_cleanup':False,'turns_completed':0,'recover_context':not optout}
        state={'process':p,'record':record,'runtime':runtime,'log':log};self.states.append(state);self.report['workers'].append(record);self.state=state;self.persist();tick=time.monotonic()
        while not ready.exists():
            if p.poll() is not None:raise RuntimeError('Native app exited before readiness')
            if time.monotonic()-tick>25:raise TimeoutError('Native app readiness timeout')
            time.sleep(.02)
        self.ready=json.loads(ready.read_text());assert self.ready['pid']==p.pid
        record['readiness']={k:v for k,v in self.ready.items() if k!='token'};self.persist()
    def stop(self,state=None):
        state=state or self.state
        if state is None or state['record']['exit_code'] is not None:return
        p=state['process'];record=state['record']
        if p.poll() is None:p.terminate()
        try:record['exit_code']=p.wait(timeout=15)
        except subprocess.TimeoutExpired:p.kill();record['exit_code']=p.wait();record['forced_cleanup']=True
        state['log'].close();self.persist()
        if record['exit_code']!=0 or record['forced_cleanup']:raise RuntimeError('Unclean native app exit')
        runtime=json.loads(state['runtime'].read_text());assert runtime['pid']==p.pid and runtime['failure'] is None
        assert runtime['recover_context']==record['recover_context'] and runtime['actual_llm_or_gpu'] is True
        assert runtime['provider_kind']=='actual_native_loopback_relay' and runtime['audit_timing_hooks'] is False
        if record['turns_completed']:assert {'avatar.main','avatar.web','avatar.brain.llm'}<=runtime['module_sources'].keys()
        for row in runtime['module_sources'].values():assert self.frozen['sha256'][str(Path(row['path']).relative_to(ROOT))]==row['sha256']
        record['runtime_modules_bound']=len(runtime['module_sources']);self.persist()
    def begin(self,text):
        self.verify();idx=len(self.case['turns'])+1
        accepted=self.query('/turns',{'request_id':f'c30_native_{self.case["id"]}_turn_{idx:03d}','text':text,'use_web':False})
        row={'input':text,'accepted':accepted,'job_id':accepted['body']['data']['job_id'],'app_pid':self.state['process'].pid}
        self.case['turns'].append(row);self.persist();return row
    def run_case(self,case,arm):
        self.verify();self.folder=self.args.output/(case['id']+'-'+arm);self.folder.mkdir()
        self.temporary=Path(tempfile.mkdtemp(prefix='c30-context-',dir=ROOT.parent/'runtime/tmp'));self.db=self.temporary/'owned.db'
        self.case={'id':case['id']+'_'+arm,'case_id':case['id'],'arm':arm,'turns':[],'checks':[],'snapshots':[],
                   'external_operations':[],'complete':False,'owned_runtime_dir':str(self.temporary)}
        self.report['cases'].append(self.case);self.state=None;start=len(self.relay.rows)
        try:
            self.start(arm=='optout_restart')
            for index,text in enumerate(case['turns']):
                if index==2:self.restart(arm=='optout_restart')
                result=self.turn(text)
                if result['generation_mode']!='llm' or result['analysis_mode']!='llm':raise RuntimeError('Native normal generation/analysis not reached')
            self.stop();state=self.snapshot('final')
            with closing(sqlite3.connect('file:'+str(self.db)+'?mode=ro',uri=True)) as conn:(self.folder/'database_dump.sql').write_text('\n'.join(conn.iterdump())+'\n')
            rows=[parse_wire(deepcopy(r)) for r in self.relay.rows[start:]];self.case['model_requests']=rows
            assert len(rows)==6 and sum(r['kind']=='generation' for r in rows)==3 and all(r['finish_reason']=='stop' for r in rows)
            generations=[r for r in rows if r['kind']=='generation'];third=generations[-1]['request']['messages']
            expected=[]
            if arm=='recovered_restart':
                for t in self.case['turns'][:2]:expected.extend([{'role':'user','content':t['input']},{'role':'assistant','content':t['result']['reply']}])
            assert third[1:-1]==expected and third[-1]=={'role':'user','content':case['turns'][-1]}
            assert len(state['memory_messages'])==6 and not state['memory_reminders'] and not state['memory_action_receipts']
            ids=self.case['turns'][-1]['result']['conversation'];deps={r['source_id'] for r in state['memory_response_context'] if r['message_id']==ids['assistant_message_id'] and r['source_type']=='message'}
            if arm=='recovered_restart':assert {r['id'] for r in state['memory_messages'] if r['id']!=ids['assistant_message_id']}<=deps
            nonhistory=third[:1]+third[-1:];needles=case.get('source_answers',[case['expected']] if 'expected' in case else [])
            leaks=[{'needle':v,'role':m['role']} for v in needles for m in nonhistory if v in m['content']]
            self.case.update(probe_messages=third,history_role_messages_verified=len(expected),nonhistory_source_answer_occurrences=leaks,
                             history_only_isolation_passed=not leaks,grade=grade(self.case['turns'][-1]['result']['reply'],case),complete=True)
        finally:
            for state in self.states:
                try:self.stop(state)
                except BaseException as error:self.report['cleanup_errors'].append({'pid':state['process'].pid,'error':repr(error)})
            self.case['model_requests']=[deepcopy(r) for r in self.relay.rows[start:]]
            self.report['requests'].extend(parse_wire(deepcopy(r)) for r in self.relay.rows[start:] if r.get('outcome')=='completed' and r.get('http_status')==200)
            self.persist()
        print(case['id'],arm,'strict',self.case['grade']['correct'],'isolated',self.case['history_only_isolation_passed'],flush=True)
    def run(self):
        registry,registry_sha,_=load_registry(ROOT/REGISTRY,expected_sha256=self.frozen['sha256'][REGISTRY]);spec=next(m for m in registry['models'] if m['model_id']==self.args.model)
        ready=self.args.output/'provider-ready.json';trace=self.args.output/'provider-trace.jsonl'
        command=[str(self.args.provider_python),str(ROOT/'scripts/serve_local_model_eval.py'),'--model',str(ROOT/'models'/self.args.model.replace('-q4_k_m','-gguf')/spec['file']),
                 '--model-key',self.args.model,'--metadata',str(ROOT/spec['metadata']),'--ready',str(ready),'--trace',str(trace),'--backend','cuda',
                 '--registry',str(ROOT/REGISTRY),'--expected-registry-sha256',registry_sha]
        self.report['provider_command']=command;process=None;relay_thread=None;tick=time.monotonic();self.persist()
        try:
            self.verify()
            with (self.args.output/'provider.log').open('x') as log:
                process=subprocess.Popen(command,cwd=ROOT,env=environment(self.args.provider_python),stdout=log,stderr=subprocess.STDOUT);self.report['provider_pid']=process.pid;self.persist()
                while True:
                    if process.poll() is not None:raise RuntimeError('Native provider exited before readiness')
                    if ready.exists():
                        try:metadata=json.loads(ready.read_text());break
                        except json.JSONDecodeError:pass
                    time.sleep(.1)
                validate_provider_identity(metadata,{'models_registry':REGISTRY,'models_registry_sha256':registry_sha,'provider_backend':'cuda'})
                assert metadata['pid']==process.pid and metadata['model_id']==self.args.model
                assert metadata['provider_source_sha256']==self.frozen['sha256']['scripts/serve_local_model_eval.py'] and metadata['resource_selector_sha256']==self.frozen['sha256']['src/avatar/gpu_resources.py']
                expected={'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1}
                assert all(metadata['configuration'].get(k)==v for k,v in expected.items())
                self.report['provider_ready']=metadata;self.persist();print('Ready',self.args.model,'GPU',metadata['chosen_gpu'],flush=True)
                for index,stream in enumerate(self.protocol['warmups']):
                    self.verify();payload={'model':self.args.model,'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16}
                    row=request(metadata['url'],payload);row.update(role='warmup',warmup_index=index);self.report['requests'].append(row);self.report['warmups'].append(row);self.persist()
                    assert row['finish_reason']=='stop'
                self.relay=NativeRelay(metadata['url']);relay_thread=threading.Thread(target=self.relay.serve_forever,daemon=True);relay_thread.start()
                for case,order in zip(self.protocol['cases'],self.protocol['case_arm_orders'],strict=True):
                    for arm in order:self.run_case(case,arm)
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
                self.report['gpu_processes_after']=raw
                self.report['cleanup_passed']=self.report['provider_exit']==0 and not self.report.get('provider_forced_cleanup') and not self.report['cleanup_errors'] and not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines())
            self.report['seconds']=time.monotonic()-tick;self.persist()
        try:
            native=[json.loads(line) for line in trace.read_text().splitlines()];validate_native_calls(self.report,native)
            self.report['native_trace_sha256']=digest(trace);assert len(self.report['workers'])==24 and len(self.report['cases'])==12
            assert all(c['complete'] and len(c['turns'])==3 for c in self.report['cases']) and self.report['cleanup_passed']
            self.report['metrics']={arm:{'cases':6,'strict_correct':sum(c['grade']['correct'] for c in self.report['cases'] if c['arm']==arm),'isolated_pairs':sum(c['history_only_isolation_passed'] for c in self.report['cases'] if c['arm']==arm)} for arm in ARMS}
            self.verify();self.report['engineering_passed']=True;self.report['completed']=True;self.persist()
        except BaseException as error:self.report['failure']=repr(error);self.persist();raise
        print('Complete',self.report['metrics'],'semantic approval false',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model',required=True,choices=MODELS);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--freeze',required=True,type=Path);p.add_argument('--expected-freeze-sha256',required=True);p.add_argument('--provider-python',required=True,type=Path)
    p.add_argument('--prior-4b',type=Path);p.add_argument('--prior-4b-sha256');args=p.parse_args()
    signal.signal(signal.SIGTERM,lambda signum,frame:(_ for _ in ()).throw(KeyboardInterrupt('Owned native context experiment interrupted')))
    NativeContext(args).run()

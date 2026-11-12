"""One explicitly scheduled read/forget interleaving with real HTTP, OS and SQL."""
import argparse
from contextlib import closing
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request,build_opener,ProxyHandler
from context_race_common import ROOT,BASE,PROTOCOL,verify_freeze
from run_context_fault_controls import Harness,Provider,MemoryStore
from run_context_baseline import save,events


class Race(Harness):
    def __init__(self,args):
        self.args=args;self.frozen=verify_freeze(args.freeze,args.expected_freeze_sha256)
        self.protocol=json.loads((ROOT/PROTOCOL).read_text());args.output.mkdir(parents=True,exist_ok=False)
        self.report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'scope':self.protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':self.frozen,
            'actual_llm_or_gpu':False,'cases':[],'workers':[],'http_calls':[],'cleanup_errors':[],
            'completed':False,'failure':None,'explicit_delegated_timing_wrappers':True}
        self.opener=build_opener(ProxyHandler({}));self.states=[];self.state=None;self.ready=None;self.persist()
    def verify(self):verify_freeze(self.args.freeze,self.args.expected_freeze_sha256)
    def persist(self):save(self.args.output/'race.json',self.report)
    def start(self,timing_hooks=False):
        self.verify();n=len(self.report['workers'])+1;ready=self.temporary/f'race-{n}-ready.json';runtime=self.folder/f'worker-{n}-runtime.json'
        command=[sys.executable,str(BASE/'审计/context_race_worker.py'),'--db',str(self.db),'--ready',str(ready),'--runtime-out',str(runtime),
                 '--provider-url',f'http://127.0.0.1:{self.provider.server_port}/v1','--freeze',str(self.args.freeze.resolve()),
                 '--expected-freeze-sha256',self.args.expected_freeze_sha256]+(['--timing-hooks'] if timing_hooks else [])
        log=(self.folder/f'worker-{n}.log').open('x');p=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
              env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
        record={'case':self.case['id'],'pid':p.pid,'argv':command,'runtime_file':str(runtime.relative_to(self.args.output)),
                'exit_code':None,'forced_cleanup':False,'turns_completed':0,'recover_context':True,'timing_hooks':timing_hooks}
        state={'process':p,'record':record,'runtime':runtime,'log':log};self.states.append(state);self.report['workers'].append(record);self.state=state;self.persist()
        started=time.monotonic()
        while not ready.exists():
            if p.poll() is not None:raise RuntimeError('Owned race app exited before readiness')
            if time.monotonic()-started>25:raise TimeoutError('Owned race app readiness timeout')
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
        if record['exit_code']!=0 or record['forced_cleanup']:raise RuntimeError('Unclean owned race app exit')
        actual=json.loads(state['runtime'].read_text());assert actual['pid']==p.pid and actual['failure'] is None
        assert actual['recover_context'] is True and actual['audit_timing_hooks']==record['timing_hooks']
        for row in actual['module_sources'].values():assert self.frozen['sha256'][str(Path(row['path']).relative_to(ROOT))]==row['sha256']
        record['runtime_modules_bound']=len(actual['module_sources']);self.persist()
    def mark(self,name,**values):
        data={'event':name,'monotonic_ns':time.monotonic_ns(),'pid':os.getpid(),**values};save(self.temporary/(name+'.json'),data);return data
    def wait_file(self,name):
        start=time.monotonic();path=self.temporary/(name+'.json')
        while not path.exists():
            if time.monotonic()-start>25:raise TimeoutError('Owned race wait: '+name)
            time.sleep(.01)
        return json.loads(path.read_text())
    def run(self):
        tick=time.monotonic();self.folder=self.args.output/'transaction_privacy';self.folder.mkdir()
        self.temporary=Path(tempfile.mkdtemp(prefix='c29-context-',dir=ROOT.parent/'runtime/tmp'));self.db=self.temporary/'owned.db'
        self.case={'id':'transaction_privacy','turns':[],'checks':[],'snapshots':[],'external_operations':[],
                   'complete':False,'owned_runtime_dir':str(self.temporary)};self.report['cases'].append(self.case)
        self.provider=Provider();provider_thread=threading.Thread(target=self.provider.serve_forever,daemon=True);provider_thread.start()
        writer=None;reader=None;writer_start=threading.Event();writer_ready=threading.Event();writer_errors=[];stream_ready=threading.Event();stream_errors=[]
        try:
            self.start();old=self.turn('窗边的纸风车编号C29PRIVATE。');uid=old['conversation']['user_message_id'];aid=old['conversation']['assistant_message_id']
            fragment,_=self.mutate('remember-private-race-source',lambda m:m.remember('纸风车编号C29PRIVATE。',source_message_id=uid));self.stop();self.start(True)
            def forget():
                try:
                    with closing(MemoryStore(str(self.db))) as memory:
                        def trace(statement):
                            if statement.strip().upper()=='BEGIN IMMEDIATE':self.mark('writer-begin-intent',statement=statement)
                        memory._conn.set_trace_callback(trace);writer_ready.set()
                        if not writer_start.wait(25):raise TimeoutError('Writer not started')
                        memory.forget(fragment);self.mark('writer-done',revision=memory.context_revision)
                except BaseException as error:writer_errors.append(repr(error));writer_ready.set()
            writer=threading.Thread(target=forget);writer.start();assert writer_ready.wait(25) and not writer_errors
            before=self.snapshot('before-interleaving');calls_before=len(self.provider.rows)
            row=self.begin('现在继续新场景C29_RACE。');held=self.wait_file('read-held')
            self.check('real_read_holds_source_transaction',held['transaction_held'] and set(held['source_ids'])=={uid,aid},held)
            # Subscribe before privacy revision changes, so the real cancellation event
            # remains observable without a later GET refreshing/removing the old job.
            def stream():
                try:
                    req=Request(self.ready['base_url']+'/turns/'+row['job_id']+'/events',headers={'X-Avatar-Token':self.ready['token']})
                    with self.opener.open(req,timeout=30) as response:
                        stream_ready.set();kind,result,observed,raw=events(response,time.perf_counter())
                    row.update(terminal=kind,result=result,events=observed,raw_sse=raw)
                except BaseException as error:stream_errors.append(repr(error));stream_ready.set()
            reader=threading.Thread(target=stream);reader.start();assert stream_ready.wait(25) and not stream_errors
            self.mark('stream-subscribed');writer_start.set();intent=self.wait_file('writer-begin-intent')
            blocked=not (self.temporary/'writer-done.json').exists();self.check('writer_waits_while_source_lock_held',blocked,{'intent':intent,'writer_finished':not blocked})
            self.mark('release-read');done=self.wait_file('writer-done');reader.join(25);writer.join(25)
            assert not reader.is_alive() and not writer.is_alive() and not writer_errors and not stream_errors
            self.check('revision_checkpoint_cancels_before_models',row['terminal']=='cancelled' and len(self.provider.rows)==calls_before,{'terminal':row.get('terminal'),'calls_before':calls_before,'calls_after':len(self.provider.rows)})
            after=self.snapshot('after-interleaving');self.check('forget_committed_and_source_redacted',done['revision']==before['memory_context_revision'][0]['revision']+1 and {uid,aid}<={r['id'] for r in after['memory_messages'] if r['content']=='[redacted]'},done)
            self.check('no_new_assistant_after_stale_read',len(after['memory_messages'])==3 and after['memory_messages'][-1]['role']=='user' and not after['memory_chat_results'],after['memory_messages'])
            self.stop();self.snapshot('final')
            with closing(sqlite3.connect('file:'+str(self.db)+'?mode=ro',uri=True)) as conn:(self.folder/'database_dump.sql').write_text('\n'.join(conn.iterdump())+'\n')
            self.verify();self.case['complete']=True;self.report['completed']=True
        except BaseException as error:self.report['failure']=repr(error);raise
        finally:
            self.provider.release.set();writer_start.set()
            for name in ('release-read','writer-done'):
                if not (self.temporary/(name+'.json')).exists():self.mark(name,cleanup_release=True)
            if writer:writer.join(25)
            if reader:reader.join(25)
            self.report['thread_cleanup']={'writer_alive':bool(writer and writer.is_alive()),'stream_alive':bool(reader and reader.is_alive()),'writer_errors':writer_errors,'stream_errors':stream_errors}
            for state in self.states:
                try:self.stop(state)
                except BaseException as error:self.report['cleanup_errors'].append({'pid':state['process'].pid,'error':repr(error)})
            self.provider.shutdown();provider_thread.join(10);self.provider.server_close()
            self.case['model_requests']=deepcopy(self.provider.rows)
            self.report['timing_evidence']={p.name:json.loads(p.read_text()) for p in self.temporary.glob('*.json') if not p.name.endswith('ready.json')}
            # Live worker readiness tokens are expressly excluded.
            if self.db.exists():self.snapshot('exit-state')
            self.report['seconds']=time.monotonic()-tick;self.persist()
        assert not self.report['cleanup_errors'] and not any(self.report['thread_cleanup'][n] for n in ('writer_alive','stream_alive','writer_errors','stream_errors'))
        print('Controlled read/forget OS interleaving passed:2 apps,1 result/1 cancelled,only2 setup model HTTP calls.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--freeze',required=True,type=Path)
    parser.add_argument('--expected-freeze-sha256',required=True);Race(parser.parse_args()).run()

"""Actual HTTP/SSE and OS restart audit with a controlled HTTP model fixture."""
import argparse
from collections import Counter
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request,ProxyHandler,build_opener
from urllib.error import HTTPError
from context_baseline_common import ROOT,BASE,PROTOCOL,verify_freeze
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_native_output_audit import events


class FixtureServer(ThreadingHTTPServer):
    def __init__(self):
        self.rows=[];self.counter=0;self.guard=threading.RLock()
        super().__init__(('127.0.0.1',0),FixtureHandler)


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        if self.path!='/v1/chat/completions':self.send_error(404);return
        raw=self.rfile.read(int(self.headers['Content-Length']));payload=json.loads(raw)
        with self.server.guard:
            kind='cognitive' if payload.get('response_format') else 'generation'
            if kind=='generation':self.server.counter+=1
            reply=(json.dumps({'emotion':{'valence':0,'arousal':0},'facts':[]},ensure_ascii=False) if kind=='cognitive'
                   else '受控回复C29-'+str(self.server.counter)+'。')
            identifier='c29-fixture-'+str(len(self.server.rows)+1);created=int(time.time())
            if payload.get('stream'):
                chunks=[{'id':identifier,'object':'chat.completion.chunk','created':created,'model':'c29-controlled',
                         'choices':[{'index':0,'delta':{'content':reply},'finish_reason':None}]},
                        {'id':identifier,'object':'chat.completion.chunk','created':created,'model':'c29-controlled',
                         'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
                body=''.join('data: '+json.dumps(c,ensure_ascii=False)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
            else:
                body=json.dumps({'id':identifier,'object':'chat.completion','created':created,'model':'c29-controlled',
                    'choices':[{'index':0,'message':{'role':'assistant','content':reply},'finish_reason':'stop'}]},ensure_ascii=False)
            row={'id':identifier,'kind':kind,'request':payload,'raw_request_json':raw.decode(),'request_sha256':sha256(raw).hexdigest(),
                 'reply':reply,'raw_http_body':body,'controller_pid':os.getpid(),'provider_kind':'controlled_http_fixture',
                 'actual_llm_or_gpu':False,'outcome':'writing'}
            self.server.rows.append(row)
        try:
            data=body.encode();self.send_response(200);self.send_header('Content-Type','text/event-stream' if payload.get('stream') else 'application/json')
            self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers();self.wfile.write(data);self.wfile.flush()
            row['outcome']='completed'
        except BaseException as error:row['outcome']='failed';row['error']=repr(error);raise


def save(path,value):
    tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda v:{'sqlite_blob_hex':v.hex()} if isinstance(v,bytes) else str(v))+'\n');os.replace(tmp,path)


def sql_snapshot(path):
    with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as conn:
        conn.row_factory=sqlite3.Row
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name:[dict(row) for row in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')] for name in tables}


def run(args):
    if not __debug__:raise ValueError('Run without Python optimization')
    frozen=verify_freeze(args.freeze,args.expected_freeze_sha256);protocol=json.loads((ROOT/PROTOCOL).read_text())
    if [c['id'] for c in protocol['cases']]!=['same_instance','new_os_instance'] or any(len(c['turns'])!=3 for c in protocol['cases']):raise ValueError('Unexpected fixed baseline protocol')
    args.output.mkdir(parents=True,exist_ok=False);output=args.output/'baseline.json'
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'scope':protocol['scope'],
            'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':frozen,'provider_kind':'controlled_loopback_http_fixture',
            'actual_llm_or_gpu':False,'cases':[],'workers':[],'http_calls':[],'cleanup_errors':[],'completed':False,'engineering_passed':False,'failure':None}
    opener=build_opener(ProxyHandler({}));live=[]
    def persist():save(output,report)
    def verify():verify_freeze(args.freeze,args.expected_freeze_sha256)
    def query(ready,route,value=None):
        req=Request(ready['base_url']+route,data=None if value is None else json.dumps(value,ensure_ascii=False).encode(),
                    headers={'X-Avatar-Token':ready['token'],'Content-Type':'application/json'})
        try:
            with opener.open(req,timeout=30) as response:
                raw=response.read().decode();result={'status':response.status,'body':json.loads(raw)}
                report['http_calls'].append({'route':route,'request':value,'status':response.status,'raw_body':raw});persist();return result
        except HTTPError as error:
            report['http_calls'].append({'route':route,'request':value,'status':error.code,'raw_body':error.read().decode(errors='replace')});persist();raise
    def start_worker(case_folder,temporary,db,provider):
        verify();number=len(report['workers'])+1;ready_path=temporary/f'app-{number}-ready.json';runtime=case_folder/f'app-{number}-runtime.json'
        command=[sys.executable,str(BASE/'审计/context_baseline_worker.py'),'--db',str(db),'--ready',str(ready_path),'--runtime-out',str(runtime),
                 '--provider-url',f'http://127.0.0.1:{provider.server_port}/v1','--freeze',str(args.freeze.resolve()),'--expected-freeze-sha256',args.expected_freeze_sha256]
        log=(case_folder/f'app-{number}.log').open('x');process=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
            env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
        record={'pid':process.pid,'argv':command,'runtime_file':str(runtime.relative_to(args.output)),'exit_code':None,'forced_cleanup':False,'turns_completed':0}
        state={'process':process,'record':record,'runtime':runtime,'log':log};live.append(state);report['workers'].append(record);persist();started=time.monotonic()
        while not ready_path.exists():
            if process.poll() is not None:raise RuntimeError('Application worker exited before readiness')
            if time.monotonic()-started>30:raise TimeoutError('Owned worker startup resource timeout')
            time.sleep(.05)
        ready=json.loads(ready_path.read_text())
        if ready['pid']!=process.pid:raise ValueError('Worker readiness PID differs')
        record['readiness']={k:v for k,v in ready.items() if k!='token'};persist();return state,ready
    def stop_worker(state):
        process=state['process'];record=state['record']
        if record['exit_code'] is not None:return
        if process.poll() is None:process.terminate()
        try:record['exit_code']=process.wait(timeout=15)
        except subprocess.TimeoutExpired:process.kill();record['exit_code']=process.wait();record['forced_cleanup']=True
        state['log'].close();persist()
        if record['exit_code']!=0 or record['forced_cleanup']:raise RuntimeError('Owned worker did not cleanly exit')
        actual=json.loads(state['runtime'].read_text());record['runtime_pid_matches']=actual['pid']==process.pid
        if not record['runtime_pid_matches'] or actual['failure'] is not None:raise ValueError('Runtime PID/failure mismatch')
        if record['turns_completed'] and not {'avatar.main','avatar.web','avatar.brain.memory','avatar.brain.llm'}<=actual['module_sources'].keys():raise ValueError('Required actual runtime modules absent after accepted chat')
        for module,value in actual['module_sources'].items():
            relative=str(Path(value['path']).relative_to(ROOT))
            if frozen['sha256'].get(relative)!=value['sha256']:raise ValueError('Actual worker imported unfrozen module: '+module)
        record['runtime_modules_bound']=len(actual['module_sources']);persist()
    def stop_all():
        errors=[]
        for state in live:
            try:stop_worker(state)
            except BaseException as error:errors.append({'pid':state['process'].pid,'error':repr(error)})
        if errors:report['cleanup_errors'].extend(errors);persist()
        return errors
    persist();started=time.monotonic()
    try:
        for case in protocol['cases']:
            verify();folder=args.output/case['id'];folder.mkdir();provider=FixtureServer();thread=threading.Thread(target=provider.serve_forever,daemon=True);thread.start()
            row={'id':case['id'],'turns':[],'complete':False};report['cases'].append(row);persist()
            try:
                temporary=Path(tempfile.mkdtemp(prefix='c29-context-',dir=ROOT.parent/'runtime/tmp'));row['owned_runtime_dir']=str(temporary)
                db=temporary/'owned.db';state,ready=start_worker(folder,temporary,db,provider)
                for index,text in enumerate(case['turns'],1):
                    verify()
                    if case['restart_after_turn'] is not None and index==case['restart_after_turn']+1:
                        row['conversation_before_restart']=query(ready,'/conversation');stop_worker(state);state,ready=start_worker(folder,temporary,db,provider)
                    accepted=query(ready,'/turns',{'request_id':f'c29_context_baseline_{case["id"]}_{index}','text':text,'use_web':False});job=accepted['body']['data']['job_id']
                    req=Request(ready['base_url']+'/turns/'+job+'/events',headers={'X-Avatar-Token':ready['token']});tick=time.perf_counter()
                    with opener.open(req,timeout=30) as response:kind,result,observed,raw_sse=events(response,tick)
                    turn={'input':text,'accepted':accepted,'terminal':kind,'result':result,'events':observed,'raw_sse':raw_sse,'app_pid':state['process'].pid,
                          'conversation':query(ready,'/conversation')};row['turns'].append(turn);persist()
                    if kind!='result' or result.get('generation_mode')!='llm':raise RuntimeError('Ordinary controlled generation path not reached')
                    if ''.join(e['data']['text'] for e in observed if e['event']=='text')!=result['reply']:raise ValueError('SSE/final reply mismatch')
                    state['record']['turns_completed']+=1;persist()
                stop_worker(state)
                row['sql_snapshot']=sql_snapshot(db)
                with closing(sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)) as export:
                    with (folder/'database_dump.sql').open('x') as stream:stream.write('\n'.join(export.iterdump())+'\n')
                with provider.guard:row['model_requests']=deepcopy(provider.rows)
                generations=[r for r in row['model_requests'] if r['kind']=='generation'];assert len(generations)==3
                final=generations[-1]['request']['messages'];actual=Counter((m['role'],m['content']) for m in final)
                expected=[]
                for turn in row['turns'][:2]:expected.extend([{'role':'user','content':turn['input']},{'role':'assistant','content':turn['result']['reply']}])
                row['third_generation_messages']=final;row['expected_prior_messages']=expected
                row['prior_message_counts']=[{'role':item['role'],'content':item['content'],'count':actual[(item['role'],item['content'])]} for item in expected]
                row['desired_context_continuity_passed']=all(item['count']==1 for item in row['prior_message_counts'])
                row['persistent_messages_after']=row['sql_snapshot']['memory_messages'];row['complete']=True;persist()
                if case['id']=='same_instance' and not row['desired_context_continuity_passed']:raise ValueError('Same-instance positive control failed; restart difference uninterpretable')
            except BaseException as error:
                if report['failure'] is None:report['failure']=repr(error)
                persist();raise
            finally:
                errors=stop_all()
                provider.shutdown();thread.join(timeout=10);provider.server_close()
                with provider.guard:row['model_requests']=deepcopy(provider.rows)
                persist()
                if errors and report['failure'] is None:raise RuntimeError('Controlled worker cleanup/identity failed')
        verify();report['completed']=len(report['cases'])==2 and all(case['complete'] for case in report['cases'])
        report['engineering_passed']=(report['completed'] and len(report['workers'])==3 and all(row['exit_code']==0 and row['runtime_pid_matches'] for row in report['workers'])
            and all(request['outcome']=='completed' for case in report['cases'] for request in case['model_requests']))
        report['desired_context_continuity_passed']=all(case['desired_context_continuity_passed'] for case in report['cases'])
    except BaseException as error:
        if report['failure'] is None:report['failure']=repr(error)
        raise
    finally:
        stop_all()
        report['seconds']=time.monotonic()-started;persist()
    print('Engineering',report['engineering_passed'],'desired continuity',report['desired_context_continuity_passed'],
          [(c['id'],c['desired_context_continuity_passed']) for c in report['cases']],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--freeze',required=True,type=Path)
    parser.add_argument('--expected-freeze-sha256',required=True);run(parser.parse_args())

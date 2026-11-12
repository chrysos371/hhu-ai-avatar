"""Eight pre-registered controlled-provider workflows through real HTTP/OS apps."""
import argparse
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
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from context_fault_common import ROOT,BASE,PROTOCOL,CASES,verify_freeze
from run_context_baseline import save,sql_snapshot,events
sys.path.insert(0,str(ROOT/'src'))
from avatar.brain.memory import MemoryStore


class Provider(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self):
        self.rows=[];self.guard=threading.RLock();self.counter=0
        self.held=threading.Event();self.release=threading.Event()
        super().__init__(('127.0.0.1',0),ProviderHandler)


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        if self.path!='/v1/chat/completions':self.send_error(404);return
        raw=self.rfile.read(int(self.headers['Content-Length']));payload=json.loads(raw)
        kind='cognitive' if payload.get('response_format') else 'generation'
        with self.server.guard:
            if kind=='generation':self.server.counter+=1
            identifier='c29-fault-'+str(len(self.server.rows)+1)
            reply=(json.dumps({'emotion':{'valence':0,'arousal':0},'facts':[]},ensure_ascii=False) if kind=='cognitive'
                   else ('受控回复包含C29PRIVATE。' if any(m['role']=='user' and 'C29PRIVATE' in m['content'] for m in payload['messages'])
                         else '受控故障回复'+str(self.server.counter)+'。'))
            record={'id':identifier,'kind':kind,'request':payload,'raw_request_json':raw.decode(),'request_sha256':sha256(raw).hexdigest(),
                    'reply':reply,'controller_pid':os.getpid(),'actual_llm_or_gpu':False,'outcome':'admitted'}
            self.server.rows.append(record)
        if kind=='generation' and 'C29_CANCEL' in payload['messages'][-1]['content']:
            record['held_before_response']=True;self.server.held.set()
            if not self.server.release.wait(25):raise TimeoutError('Owned cancellation fixture release missing')
            record['released_after_explicit_cancel']=True
        created=int(time.time())
        if payload.get('stream'):
            chunks=[{'id':identifier,'object':'chat.completion.chunk','created':created,'model':'c29-controlled',
                     'choices':[{'index':0,'delta':{'content':reply},'finish_reason':None}]},
                    {'id':identifier,'object':'chat.completion.chunk','created':created,'model':'c29-controlled',
                     'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]}]
            body=''.join('data: '+json.dumps(c,ensure_ascii=False)+'\n\n' for c in chunks)+'data: [DONE]\n\n'
        else:
            body=json.dumps({'id':identifier,'object':'chat.completion','created':created,'model':'c29-controlled',
                'choices':[{'index':0,'message':{'role':'assistant','content':reply},'finish_reason':'stop'}]},ensure_ascii=False)
        record['raw_http_body']=body
        try:
            data=body.encode();self.send_response(200);self.send_header('Content-Type','text/event-stream' if payload.get('stream') else 'application/json')
            self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers();self.wfile.write(data);self.wfile.flush()
            record['outcome']='completed'
        except (BrokenPipeError,ConnectionResetError) as error:
            record['outcome']='client_closed';record['error']=repr(error)


class Harness:
    def __init__(self,args):
        self.args=args;self.frozen=verify_freeze(args.freeze,args.expected_freeze_sha256)
        self.protocol=json.loads((ROOT/PROTOCOL).read_text());args.output.mkdir(parents=True,exist_ok=False)
        self.report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'scope':self.protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':self.frozen,
            'actual_llm_or_gpu':False,'cases':[],'workers':[],'http_calls':[],'cleanup_errors':[],
            'completed':False,'failure':None,'controlled_timing_only_for_provider_cancel':True}
        self.opener=build_opener(ProxyHandler({}));self.states=[];self.state=None;self.ready=None
        self.persist()
    def verify(self):verify_freeze(self.args.freeze,self.args.expected_freeze_sha256)
    def persist(self):save(self.args.output/'faults.json',self.report)
    def query(self,route,value=None):
        req=Request(self.ready['base_url']+route,data=None if value is None else json.dumps(value,ensure_ascii=False).encode(),
                    headers={'X-Avatar-Token':self.ready['token'],'Content-Type':'application/json'})
        try:
            with self.opener.open(req,timeout=30) as response:
                raw=response.read().decode();result={'status':response.status,'body':json.loads(raw)}
                self.report['http_calls'].append({'case':self.case['id'],'route':route,'request':value,'status':response.status,'raw_body':raw})
                self.persist();return result
        except HTTPError as error:
            self.report['http_calls'].append({'case':self.case['id'],'route':route,'request':value,'status':error.code,'raw_body':error.read().decode(errors='replace')})
            self.persist();raise
    def start(self,optout=False):
        self.verify();n=len(self.report['workers'])+1;ready=self.temporary/f'worker-{n}-ready.json';runtime=self.folder/f'worker-{n}-runtime.json'
        command=[sys.executable,str(BASE/'审计/context_fault_worker.py'),'--db',str(self.db),'--ready',str(ready),'--runtime-out',str(runtime),
                 '--provider-url',f'http://127.0.0.1:{self.provider.server_port}/v1','--freeze',str(self.args.freeze.resolve()),
                 '--expected-freeze-sha256',self.args.expected_freeze_sha256]+(['--no-context-recovery'] if optout else [])
        log=(self.folder/f'worker-{n}.log').open('x');p=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
              env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),NO_PROXY='127.0.0.1,localhost',no_proxy='127.0.0.1,localhost'))
        record={'case':self.case['id'],'pid':p.pid,'argv':command,'runtime_file':str(runtime.relative_to(self.args.output)),
                'exit_code':None,'forced_cleanup':False,'turns_completed':0,'recover_context':not optout}
        state={'process':p,'record':record,'runtime':runtime,'log':log};self.states.append(state);self.report['workers'].append(record);self.state=state;self.persist()
        started=time.monotonic()
        while not ready.exists():
            if p.poll() is not None:raise RuntimeError('Owned app exited before readiness')
            if time.monotonic()-started>25:raise TimeoutError('Owned app readiness timeout')
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
        if record['exit_code']!=0 or record['forced_cleanup']:raise RuntimeError('Unclean owned app exit')
        actual=json.loads(state['runtime'].read_text());assert actual['pid']==p.pid and actual['failure'] is None
        assert actual['recover_context']==record['recover_context'] and actual['audit_timing_hooks'] is False
        if record['turns_completed']:assert {'avatar.main','avatar.web','avatar.brain.llm'}<=actual['module_sources'].keys()
        for row in actual['module_sources'].values():assert self.frozen['sha256'][str(Path(row['path']).relative_to(ROOT))]==row['sha256']
        record['runtime_modules_bound']=len(actual['module_sources']);self.persist()
    def restart(self,optout=False):self.stop();self.start(optout)
    def begin(self,text):
        self.verify();idx=len(self.case['turns'])+1
        accepted=self.query('/turns',{'request_id':f'c29_fault_{self.case["id"]}_turn_{idx:03d}','text':text,'use_web':False})
        row={'input':text,'accepted':accepted,'job_id':accepted['body']['data']['job_id'],'app_pid':self.state['process'].pid}
        self.case['turns'].append(row);self.persist();return row
    def finish(self,row):
        req=Request(self.ready['base_url']+'/turns/'+row['job_id']+'/events',headers={'X-Avatar-Token':self.ready['token']})
        with self.opener.open(req,timeout=30) as response:kind,result,observed,raw=events(response,time.perf_counter())
        row.update(terminal=kind,result=result,events=observed,raw_sse=raw,conversation=self.query('/conversation'))
        if kind=='result':
            assert ''.join(e['data']['text'] for e in observed if e['event']=='text')==result['reply']
            self.state['record']['turns_completed']+=1
        self.persist();return row
    def turn(self,text):
        row=self.finish(self.begin(text));assert row['terminal']=='result';return row['result']
    def roles(self):
        rows=[r for r in self.provider.rows if r['kind']=='generation']
        assert rows;return rows[-1]['request']['messages'][1:]
    def check(self,name,condition,evidence):
        self.case['checks'].append({'name':name,'passed':bool(condition),'evidence':evidence});self.persist()
        if not condition:raise AssertionError(name)
    def snapshot(self,label):
        data=sql_snapshot(self.db);path=self.folder/(label+'.json');save(path,data)
        self.case['snapshots'].append({'label':label,'file':str(path.relative_to(self.args.output)),'sha256':sha256(path.read_bytes()).hexdigest()});self.persist();return data
    def mutate(self,name,fn):
        before=self.snapshot(name+'-before')
        with closing(MemoryStore(str(self.db))) as memory:result=fn(memory)
        after=self.snapshot(name+'-after');self.case['external_operations'].append({'name':name,'result':result});self.persist();return result,after
    def privacy_crosssession(self):
        first=self.turn('窗边的纸风车编号C29PRIVATE。');uid=first['conversation']['user_message_id'];oldaid=first['conversation']['assistant_message_id']
        fragment,_=self.mutate('remember-linked-private',lambda m:m.remember('纸风车编号C29PRIVATE。',source_message_id=uid))
        self.restart();resumed=self.turn('继续前面的场景。');aid=resumed['conversation']['assistant_message_id']
        before=self.snapshot('recovered-crosssession');linked={r['source_id'] for r in before['memory_response_context'] if r['message_id']==aid and r['source_type']=='message'}
        self.check('crosssession_restored_sources_bound',{uid,oldaid}<=linked and 'C29PRIVATE' in resumed['reply'],{'source_ids':sorted(linked),'reply':resumed['reply']})
        _,after=self.mutate('forget-private',lambda m:m.forget(fragment))
        redacted={r['id'] for r in after['memory_messages'] if r['content']=='[redacted]'}
        self.check('forget_redacts_derived_reply',aid in redacted and not any(r['message_id']==aid for r in after['memory_chat_results']),{'redacted_ids':sorted(redacted),'derived_assistant_id':aid})
        fresh=self.turn('这是新场景C29FRESH。');self.turn('继续新场景。')
        messages=self.roles();self.check('same_service_fresh_window',any(m['content']=='这是新场景C29FRESH。' for m in messages),messages)
        self.restart();self.turn('再次随便聊聊。');full=[r for r in self.provider.rows if r['kind']=='generation'][-3:]
        self.check('privacy_marker_absent_all_post_forget_prompts',not any('C29PRIVATE' in m['content'] for r in full for m in r['request']['messages']),[r['id'] for r in full])
        self.check('fresh_assistant_still_recovered',any(m['content']==fresh['reply'] for m in self.roles()),self.roles())
    def scope(self):
        self.turn('真人风景C29REAL。');self.turn('我来扮演一个虚构角色。');self.turn('角色风景C29FICTION，我叫虚构甲。')
        self.check('fiction_excludes_real_role_history',not any('C29REAL' in m['content'] for m in self.roles()),self.roles())
        blocked=self.turn('提醒我明天下午3点去图书馆。')
        self.check('fiction_reminder_blocked',blocked['speaker_tool_blocked'] and blocked['reminder'] is None,blocked['speaker_attribution'])
        self.restart();self.turn('角色继续聊。');self.check('fiction_history_after_restart',any('C29FICTION' in m['content'] for m in self.roles()),self.roles())
        self.turn('回到现实。');self.turn('现实里继续聊。')
        self.check('real_excludes_fiction_role_history',not any('C29FICTION' in m['content'] for m in self.roles()),self.roles())
        self.turn('我叫真实乙。');self.restart();new=self.turn('提醒我明天下午4点去操场。');s=self.snapshot('scope-final')
        self.check('only_real_reminder_created',len(s['memory_reminders'])==1 and new['reminder'] is not None,len(s['memory_reminders']))
        contents=[r['content'] for r in s['memory_fragments']]
        self.check('fiction_name_not_persisted_real_name_positive',not any('虚构甲' in t for t in contents) and any('真实乙' in t for t in contents),contents)
    def cancel(self):
        self.turn('旧场景C29SAFE。');row=self.begin('暂时等待的C29_CANCEL场景。')
        if not self.provider.held.wait(25):raise TimeoutError('Provider generation barrier not reached')
        row['cancel_response']=self.query('/turns/'+row['job_id']+'/cancel',{});self.provider.release.set();self.finish(row)
        self.check('explicit_cancel_terminal',row['terminal']=='cancelled',row['events'])
        self.restart();self.turn('这是取消后的新场景C29AFTERCANCEL。')
        self.check('orphan_gap_stops_prior_role_history',not any('C29_CANCEL' in m['content'] or 'C29SAFE' in m['content'] for m in self.roles()),self.roles())
        self.turn('继续新的取消后场景。');self.check('new_valid_pair_after_cancel_restored',any('C29AFTERCANCEL' in m['content'] for m in self.roles()),self.roles())
    def corrupt_result(self):
        first=self.turn('旧场景C29CORRUPT。');aid=first['conversation']['assistant_message_id'];self.stop()
        def corrupt(m):m._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?',('{not-json',aid));m._conn.commit();return aid
        self.mutate('invalid-result-json',corrupt);self.start();self.turn('新场景C29VALID。')
        self.check('corrupt_pair_not_restored',not any('C29CORRUPT' in m['content'] for m in self.roles()),self.roles())
        self.turn('继续新的场景。');self.check('valid_suffix_after_corruption_recovers',any('C29VALID' in m['content'] for m in self.roles()),self.roles())
    def mixed_writer(self):
        self.turn('早先的场景C29TRACKED。');self.stop()
        self.mutate('external-cli-orphan',lambda m:m.add_message('user','外部CLI内容C29UNTRACKED。','c29-cli-fixture'))
        self.start();before=len(self.provider.rows);guard=self.turn('继续说说场景。')
        self.check('untracked_scope_fails_closed_without_model',guard['speaker_attribution']['scope']=='unverified' and len(self.provider.rows)==before,guard['speaker_attribution'])
        self.turn('回到现实。');self.turn('现实新场景C29SAFEAFTERCLI。')
        self.check('canonical_control_excludes_unknown_and_old_roles',not any('C29UNTRACKED' in m['content'] or 'C29TRACKED' in m['content'] for m in self.roles()),self.roles())
    def bounded_window(self):
        for i in range(12):self.turn(f'这是风景编号C29-W{i:02d}。')
        for i in range(2):
            self.restart();self.turn(f'重启继续看风景C29-R{i}。');messages=self.roles();users=[m['content'] for m in messages if m['role']=='user']
            self.check('bounded_complete_unique_window_'+str(i),len(messages)==19 and [m['role'] for m in messages]==['user','assistant']*9+['user'] and len(users)==len(set(users)),messages)
    def no_old_actions(self):
        old=self.turn('提醒我明天下午3点去图书馆。');before=self.snapshot('old-action');calls=len(self.provider.rows);self.restart();idle=self.snapshot('after-idle-restart')
        self.check('startup_neither_models_nor_actions',len(self.provider.rows)==calls and idle['memory_reminders']==before['memory_reminders'],{'calls':calls,'reminder_ids':[r['id'] for r in idle['memory_reminders']]})
        ordinary=self.turn('聊聊窗外。');s=self.snapshot('ordinary-no-replay')
        self.check('restored_request_is_not_reexecuted',len(s['memory_reminders'])==1 and ordinary['reminder'] is None and ordinary['tool_calls']==[] and any(m['content']=='提醒我明天下午3点去图书馆。' for m in self.roles()),{'roles':self.roles(),'reminders':s['memory_reminders']})
        new=self.turn('提醒我明天下午4点去操场。');self.check('new_action_positive_distinct_id',new['reminder']['id']!=old['reminder']['id'],[old['reminder']['id'],new['reminder']['id']])
        self.restart();self.turn('继续聊窗外。');s=self.snapshot('actions-final');self.check('second_restart_no_replay',len(s['memory_reminders'])==2,len(s['memory_reminders']))
    def optout(self):
        self.turn('天气话题C29OPTOUTOLD。');self.restart(True);self.turn('随便聊聊。');s=self.snapshot('optout-final')
        self.check('explicit_optout_transient_but_persisted',not any('C29OPTOUTOLD' in m['content'] for m in self.roles()) and len(s['memory_messages'])==4,self.roles())
    def run(self):
        tick=time.monotonic()
        try:
            for expected in self.protocol['cases']:
                self.verify();self.folder=self.args.output/expected['id'];self.folder.mkdir()
                self.temporary=Path(tempfile.mkdtemp(prefix='c29-context-',dir=ROOT.parent/'runtime/tmp'));self.db=self.temporary/'owned.db'
                self.case={'id':expected['id'],'turns':[],'checks':[],'snapshots':[],'external_operations':[],'complete':False,'owned_runtime_dir':str(self.temporary)}
                self.report['cases'].append(self.case);self.provider=Provider();thread=threading.Thread(target=self.provider.serve_forever,daemon=True);thread.start();self.state=None
                try:
                    self.start(expected['id']=='optout');getattr(self,expected['id'])();self.stop();self.snapshot('final')
                    with closing(sqlite3.connect('file:'+str(self.db)+'?mode=ro',uri=True)) as conn:(self.folder/'database_dump.sql').write_text('\n'.join(conn.iterdump())+'\n')
                    assert len(self.case['turns'])==expected['submitted_turns']
                    assert len([w for w in self.report['workers'] if w['case']==expected['id']])==expected['app_processes']
                    self.case['complete']=True
                except BaseException as error:
                    self.report['failure']=repr(error);raise
                finally:
                    self.provider.release.set()
                    for state in self.states:
                        try:self.stop(state)
                        except BaseException as error:self.report['cleanup_errors'].append({'pid':state['process'].pid,'error':repr(error)})
                    self.provider.shutdown();thread.join(timeout=10);self.provider.server_close()
                    with self.provider.guard:self.case['model_requests']=deepcopy(self.provider.rows)
                    if self.db.exists():self.snapshot('exit-state')
                    self.persist()
            self.verify();turns=[t for c in self.report['cases'] for t in c['turns']]
            assert len(turns)==45 and sum(t['terminal']=='result' for t in turns)==44 and sum(t['terminal']=='cancelled' for t in turns)==1
            assert len(self.report['workers'])==20 and not self.report['cleanup_errors']
            self.report['completed']=True
        except BaseException as error:
            if self.report['failure'] is None:self.report['failure']=repr(error)
            raise
        finally:self.report['seconds']=time.monotonic()-tick;self.persist()
        print('Eight controlled OS workflows passed:45 submitted,44 results,1 explicit cancel,20 clean app exits.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--freeze',required=True,type=Path)
    parser.add_argument('--expected-freeze-sha256',required=True);Harness(parser.parse_args()).run()

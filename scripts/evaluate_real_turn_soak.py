"""Fixed-round real-model HTTP/SSE endurance; public synthetic data only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import uuid

from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.web import create_server
import avatar.main as main_module
from evaluate_real_interaction import sha, save


def read_events(response):
    """Return one terminal event and all preceding event types/text."""
    kind='message';data=[];kinds=[];text=[]
    for raw in response:
        line=raw.decode('utf-8').rstrip('\r\n')
        if not line:
            if data:
                value=json.loads('\n'.join(data));kinds.append(kind)
                if kind=='text':text.append(value['text'])
                if kind in {'result','cancelled','error'}:
                    return kind,value,kinds,text
            kind='message';data=[]
        elif line.startswith('event:'):kind=line[6:].strip()
        elif line.startswith('data:'):data.append(line[5:].lstrip())
    raise ValueError('SSE ended without a terminal event')


def assert_result(case,result,erased_names):
    if result.get('generation_mode') in {None,'rules_service_error','rules_unconfigured'}:
        raise AssertionError('Service fallback is not a valid real-model turn')
    if bool(result.get('task')) != case['task']:
        raise AssertionError('Task scope survived or disappeared incorrectly')
    if any(value not in result['reply'] for value in case['all']):
        raise AssertionError('Required result content missing')
    if result.get('delivery_check',{}).get('remaining_issues'):
        raise AssertionError('Unresolved delivery contract')
    if case['task'] and result.get('delivery_check',{}).get('literal_plan_version')!='v2':
        raise AssertionError('Unexpected literal protocol')
    if result.get('trace',{}).get('verifier',{}).get('available') is not False:
        raise AssertionError('Unexpected generic verifier activation')
    if any(name in json.dumps(result,ensure_ascii=False) for name in erased_names):
        raise AssertionError('Erased source reappeared in a later application result')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh evidence path')
    spec_path=Path('evals/interaction/cycle-03/real-turn-soak100-v2.json')
    spec=json.loads(spec_path.read_text());provider=json.loads(args.provider.read_text())
    registry=json.loads(Path('evals/interaction/cycle-02/model-scale-protocol.json').read_text())
    model=next(row for row in registry['models'] if row['model_id']==provider['model_id'])
    parsed=urlsplit(provider['url'])
    if (provider['model_id']!='qwen3-4b-q4_k_m' or parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or parsed.path!='/v1'
            or provider['model_sha256']!=model['sha256'] or provider['model_revision']!=model['revision']):
        raise ValueError('Only the hash-verified local provider is supported')
    config.llm.base_url=provider['url'];config.llm.api_key='local-eval-only';config.llm.model=provider['model_id']
    config.embedding.model=''
    raw_started=threading.Event();audit_lock=threading.Lock()
    state={'round':0,'erased':set(),'violations':[],'calls':[]}
    original_engine=main_module.LLMEngine
    class ObservedEngine(original_engine):
        def stream_chat(self,messages,**kwargs):
            serialized=json.dumps(messages,ensure_ascii=False,sort_keys=True)
            schema=(kwargs.get('response_format') or {}).get('json_schema',{}).get('name')
            started=time.perf_counter()
            with audit_lock:
                call={'round':state['round'],'schema':schema,'prompt_sha256':hashlib.sha256(serialized.encode()).hexdigest(),'first_seconds':None}
                state['calls'].append(call)
                matches=sorted(name for name in state['erased'] if name in serialized)
                if matches:state['violations'].append({'round':state['round'],'erased_names':matches,'schema':schema,'prompt_sha256':call['prompt_sha256']})
            callback=kwargs.pop('on_delta',None)
            def witness(piece):
                if call['first_seconds'] is None:call['first_seconds']=time.perf_counter()-started
                if schema is None:raw_started.set()
                if callback:callback(piece)
            try:
                value=super().stream_chat(messages,on_delta=witness,**kwargs)
                call['outcome']='completed';return value
            except Exception as exc:
                call['outcome']=type(exc).__name__;raise
            finally:call['seconds']=time.perf_counter()-started
    main_module.LLMEngine=ObservedEngine
    report={'created_utc':datetime.now(timezone.utc).isoformat(),
        'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/main.py'),Path('src/avatar/web.py'),Path('src/avatar/turns.py')]},
        'protocol':spec,'protocol_sha256':sha(spec_path),'provider':provider,
        'rows':[],'checkpoints':[],'erasures':[],'failure':None,'passed':False,'completed_rounds':0,'execution_complete':False,
        'semantic_approved':False,'multi_day_stability_approved':False,'instrumentation':'Only observes real SDK stream dispatch/chunks; never filters or changes model messages/results'}
    def snapshot(path,server):
        with sqlite3.connect(path) as db:
            counts={role:db.execute('SELECT COUNT(*) FROM memory_messages WHERE role=?',(role,)).fetchone()[0] for role in ['user','assistant']}
            counts['reminders']=db.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='memory_reminders'").fetchone() else 0
            counts['ledger']=db.execute('SELECT COUNT(*) FROM runtime_turn_ledger').fetchone()[0] if db.execute("SELECT 1 FROM sqlite_master WHERE name='runtime_turn_ledger'").fetchone() else 0
            counts['integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
        with server.turns._lock:counts['job_cache']=len(server.turns._jobs)
        status=Path('/proc/self/status').read_text();rss=next(row for row in status.splitlines() if row.startswith('VmRSS:'))
        counts.update(rss_mib=int(rss.split()[1])/1024,threads=threading.active_count(),fds=len(os.listdir('/proc/self/fd')))
        return counts
    def persist():
        with audit_lock:
            report['model_calls']=[dict(row) for row in state['calls']]
            report['observed_privacy_violations']=list(state['violations'])
        save(args.output,report)
    persist()
    started=time.perf_counter();run_id=uuid.uuid4().hex[:16]
    with tempfile.TemporaryDirectory(prefix='real-soak-',dir='data/g2-cycle-03') as folder:
        path=str(Path(folder)/'runtime.db');memory=MemoryStore(path);memory.close()
        server=create_server(path,port=0,identity_grounding=True,profile_grounding=True,task_delivery_check=True,literal_composition=True)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base=f'http://127.0.0.1:{server.server_port}'
        def api(route,data=None):
            request=urllib.request.Request(base+'/api/v1'+route,
                data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,
                headers={'X-Avatar-Token':server.token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(request,timeout=30) as response:return response.status,json.load(response)
            except urllib.error.HTTPError as exc:return exc.code,json.loads(exc.read())
        def query(route):
            status,body=api(route)
            if status!=200:raise AssertionError(f'Query failed: {status}')
            return body['data']
        names=[];erased=[];expected_reminders=0
        try:
            for index in range(spec['rounds']):
                block,position=divmod(index,spec['block_length']);case=spec['cases'][position]
                state['round']=index+1;name=f'测试用户{block:02d}'
                text=case['turns'][0].format(block=block)
                row={'round':index+1,'case':case['id'],'input':text,'error':None}
                before=snapshot(path,server);turn_start=time.perf_counter()
                request_id=f'real_soak_{run_id}_{index:03d}';payload={'request_id':request_id,'text':text,'use_web':False}
                try:
                    if position in spec['cancel_positions']:raw_started.clear();trace_offset=args.trace.stat().st_size
                    status,accepted=api('/turns',payload)
                    if status!=202:raise AssertionError(f'Turn submission failed: {status}')
                    job_id=accepted['data']['job_id']
                    if position in spec['cancel_positions']:
                        while not raw_started.wait(.02):
                            if query('/turns/'+job_id)['status'] in {'completed','cancelled','failed'}:
                                raise AssertionError('Turn terminated before a real raw reply was observed')
                        cancel_start=time.perf_counter();status,_=api('/turns/'+job_id+'/cancel',{})
                        if status!=200:raise AssertionError('Cancellation request rejected')
                        while (job:=query('/turns/'+job_id))['status'] not in {'completed','cancelled','failed'}:
                            raw_started.wait(.02);time.sleep(.01)
                        row['cancel_http_seconds']=time.perf_counter()-cancel_start
                        if job['status']!='cancelled':raise AssertionError('Observed real reply was not cancelled')
                        with server.turns._lock:job_object=server.turns._jobs[job_id]
                        with job_object.changed:row['event_types']=[event['event'] for event in job_object.events]
                        if 'text' in row['event_types']:raise AssertionError('Cancelled guarded draft was visible')
                        while True:
                            with args.trace.open('rb') as trace:
                                trace.seek(trace_offset);lines=trace.read().decode('utf-8',errors='replace').splitlines()
                            found=[]
                            for line in lines:
                                try:entry=json.loads(line)
                                except json.JSONDecodeError:continue
                                if not entry['analysis'] and entry['messages'][-1]['content']==text:found.append(entry)
                            if found:break
                            time.sleep(.02)
                        row['provider_cancel']={key:found[-1][key] for key in ['id','outcome','first_seconds','total_seconds']}
                        if row['provider_cancel']['outcome']!='client_disconnected':raise AssertionError('Provider iterator did not observe disconnect')
                    else:
                        request=urllib.request.Request(base+'/api/v1/turns/'+job_id+'/events',headers={'X-Avatar-Token':server.token})
                        with urllib.request.urlopen(request,timeout=180) as response:kind,result,kinds,visible=read_events(response)
                        row.update(event_types=kinds,visible=visible,result=result)
                        if kind!='result':raise AssertionError('Real turn ended in non-result event')
                        assert_result(case,result,erased)
                        if visible and ''.join(visible)!=result['reply']:raise AssertionError('Visible text differs from final checked result')
                        if position==3:names.append(name)
                        if position in [3,4,5]:
                            expected=None if position==5 and index in [45,95] else name
                            if expected is not None and expected not in result['reply']:raise AssertionError('Current name was not recalled')
                            if expected is None and name in result['reply']:raise AssertionError('Erased name recalled')
                        if position==7:expected_reminders+=1
                        if position in spec['duplicate_positions']:
                            count_calls=len(state['calls']);status,duplicate=api('/turns',payload)
                            if status!=202 or duplicate['data']['job_id']!=job_id or len(state['calls'])!=count_calls:
                                raise AssertionError('Duplicate request executed again')
                            row['duplicate_reused']=True
                    after=snapshot(path,server)
                    if after['user']!=index+1 or after['ledger']!=index+1 or after['assistant']!=before['assistant']+(position not in spec['cancel_positions']):
                        raise AssertionError('Turn message count is not exactly once')
                    if after['reminders']!=expected_reminders or after['job_cache']>32 or after['integrity']!='ok':
                        raise AssertionError('Reminder, cache or SQLite integrity invariant failed')
                    if state['violations']:raise AssertionError('Erased source was sent in a later model request')
                    if index+1 in spec['privacy_after_rounds']:
                        writer=MemoryStore(path)
                        try:
                            fragment=next(item for item in writer.list_memories() if item['content']=='名字: '+name)
                            writer.forget(fragment['id'])
                            if writer.get_user_profile().get('名字') is not None:raise AssertionError('Name still active after erasure')
                            if any(old in item[0] for old in names for item in writer._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'")):
                                raise AssertionError('Dependent assistant copy survived erasure')
                        finally:writer.close()
                        with audit_lock:state['erased'].update(names)
                        erased=list(names)
                        status,old=api('/turns/'+job_id)
                        replay_status,_=api('/turns',payload)
                        if status!=404 or replay_status!=410 or any(old_name in json.dumps(old,ensure_ascii=False) for old_name in erased):
                            raise AssertionError('Erased job is readable or replayable')
                        report['erasures'].append({'after_round':index+1,'erased_names':list(names),'old_job_status':status,'replay_status':replay_status})
                    row['seconds']=time.perf_counter()-turn_start;row['passed']=True
                    report['rows'].append(row)
                    if (index+1)%10==0:report['checkpoints'].append({'round':index+1,'seconds':time.perf_counter()-started,**snapshot(path,server)})
                    persist();print(index+1,case['id'],'passed',round(row['seconds'],3),flush=True)
                except Exception as exc:
                    row.update(error={'type':type(exc).__name__,'message':str(exc)},passed=False,seconds=time.perf_counter()-turn_start)
                    report['rows'].append(row);report['failure']=row['error'];persist();break
            report['passed']=len(report['rows'])==spec['rounds'] and all(row['passed'] for row in report['rows'])
            report['completed_rounds']=sum(row['passed'] for row in report['rows'])
            report['execution_complete']=len(report['rows'])==spec['rounds']
            report['final']=snapshot(path,server)
        finally:
            server.shutdown();thread.join();server.server_close();main_module.LLMEngine=original_engine
            report['seconds']=time.perf_counter()-started;persist()
    print(json.dumps({'passed':report['passed'],'completed_rounds':report['completed_rounds'],'failure':report['failure'],'seconds':report['seconds']},ensure_ascii=False),flush=True)


if __name__=='__main__':main()

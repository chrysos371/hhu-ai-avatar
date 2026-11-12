"""Simultaneous HTTP clients and instrumented SQLite write-lock audit."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from audit_reminder_delivery_baseline import ROOT, digest, write, seed, service
from avatar.paths import project_data_root
from audit_reminder_recovery_restart import send, sql
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore


def locked_ack(folder, change):
    db=folder/(change+'.db');seed(db,{'due_offset_seconds':-60,'status':'active'})
    with closing(MemoryStore(str(db))) as writer:
        store=ReminderStore(writer);event=store.pending_deliveries()[0]
        fragment=writer.remember_user('名字','锁等待审计名')
        ready=threading.Event();proceed=threading.Event();attempting=threading.Event()
        result={'change':change,'events':[]}
        def mark(event):result['events'].append({'event':event,'monotonic':time.monotonic()})
        def run():
            try:
                with closing(MemoryStore(str(db))) as memory:
                    current=ReminderStore(memory)
                    memory._conn.set_trace_callback(lambda command: (mark('ack_begin_attempt'),attempting.set()) if command=='BEGIN IMMEDIATE' else None)
                    ready.set()
                    if not proceed.wait(15):raise RuntimeError('start handshake timeout')
                    try:
                        result['ack']=current.acknowledge_delivery(event['delivery_id'],expected_revision=0)
                    except ValueError as error:result['rejected']=str(error)
                    mark('ack_finished')
            except BaseException as error:result['failure']=repr(error);ready.set();attempting.set()
        thread=threading.Thread(target=run);thread.start()
        try:
            assert ready.wait(15)
            with writer.transaction():
                mark('writer_lock_held');proceed.set();assert attempting.wait(15)
                assert 'failure' not in result
                if change=='privacy':writer.forget(fragment)
                else:store.set_status(event['id'],'cancelled')
                mark('invalidation_before_commit')
            mark('writer_commit_returned')
        finally:
            proceed.set();thread.join(15)
        assert not thread.is_alive() and 'failure' not in result
        assert result['rejected']==('delivery_revision_changed' if change=='privacy' else 'delivery_not_pending')
        result['final_sql']=sql(db)
        assert result['final_sql']['deliveries'][0]['acknowledged_at'] is None
        assert result['final_sql']['integrity']=='ok'
        result['completed']=True
        return result


def run(output):
    if not __debug__:raise RuntimeError('Assertions required')
    output.mkdir(parents=True,exist_ok=False)
    paths=[*ROOT.glob('src/avatar/**/*.py'),Path(__file__),ROOT/'scripts/lab/audit_reminder_delivery_baseline.py',ROOT/'scripts/lab/audit_reminder_recovery_restart.py']
    hashes={str(p.relative_to(ROOT)):digest(p) for p in paths}
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'source_sha256':hashes,
            'scope':'20 fixed simultaneous two-client HTTP rounds and two instrumented SQLite lock-wait controls; no model/GPU/human perception.',
            'rounds':[],'processes':[],'lock_wait_controls':[],'completed':False}
    def save():write(output/'concurrency.json',report)
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='reminder-concurrency-',dir=project_data_root(ROOT)/'tmp') as name:
            folder=Path(name);db=folder/'http.db'
            seed(db,{'due_offset_seconds':-60,'status':'active'})
            with service(db,folder,output,1,report['processes']) as url:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    def both(route,payloads):
                        gate=threading.Barrier(2)
                        def call(payload):gate.wait(timeout=15);return send(url,route,payload)
                        return [f.result() for f in [pool.submit(call,payload) for payload in payloads]]
                    for index in range(20):
                        if index:seed(db,{'due_offset_seconds':-60,'status':'active'})
                        row={'round':index+1}
                        row['pending']=both('/reminders/deliveries/pending',[{},{}])
                        a,b=[r['envelope']['data'] for r in row['pending']]
                        assert all(r['status']==200 for r in row['pending'])
                        assert a==b and len(a['items'])==1
                        event=a['items'][0]['delivery_id'];payload={'instance_id':a['instance_id'],'revision':a['revision']}
                        row['acks']=both(f'/reminders/deliveries/{event}/ack',[payload,payload])
                        assert all(r['status']==200 for r in row['acks'])
                        assert row['acks'][0]['envelope']['data']==row['acks'][1]['envelope']['data']
                        row['final_pending']=send(url,'/reminders/deliveries/pending',{})
                        assert row['final_pending']['envelope']['data']['items']==[]
                        state=sql(db);assert len(state['deliveries'])==index+1
                        assert all(r['acknowledged_at'] is not None for r in state['deliveries'])
                        assert state['integrity']=='ok'
                        row['delivery_id']=event;row['completed']=True;report['rounds'].append(row);save()
            assert all(p['exit_code']==0 and p['identity_after_wait'] is None for p in report['processes'])
            report['final_http_sql']=sql(db)
            for change in ('privacy','cancelled'):
                report['lock_wait_controls'].append(locked_ack(folder,change));save()
        report['owned_temporary_directory_removed']=not folder.exists()
        assert all(digest(ROOT/p)==h for p,h in hashes.items())
        report['source_unchanged_after_run']=True;report['http_request_count']=100;report['completed']=True
    except BaseException as error:report['failure']=repr(error);raise
    finally:save()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);run(parser.parse_args().output)

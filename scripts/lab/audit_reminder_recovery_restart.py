"""Real owned OS restart protocols; explicit client ACK, no human-read claim."""
import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
from audit_reminder_delivery_baseline import ROOT, TOKEN, digest, write, seed, service


def sql(db):
    with sqlite3.connect('file:'+str(db)+'?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return {'reminders':[dict(r) for r in conn.execute('SELECT * FROM memory_reminders')],
                'deliveries':[dict(r) for r in conn.execute('SELECT * FROM memory_reminder_deliveries')],
                'integrity':conn.execute('PRAGMA integrity_check').fetchone()[0]}


def send(url, route, payload=None, *, discard=False):
    req = Request(url+route, data=None if payload is None else json.dumps(payload).encode(),
                  headers={'X-Avatar-Token':TOKEN,'Content-Type':'application/json'})
    start = time.monotonic()
    try:
        response = build_opener(ProxyHandler({})).open(req, timeout=15)
    except HTTPError as error:
        response = error
    with response:
        row = {'route':route,'method':req.get_method(),'payload':payload,'status':response.code,'body_consumed':not discard}
        if not discard: row['envelope'] = json.load(response)
        else: row['scope'] = 'Close after committed response headers without JSON consumption; not wire-loss or display proof.'
    row['seconds'] = time.monotonic()-start
    return row


def run(output):
    if __debug__ is False: raise RuntimeError('Assertions required')
    protocol_path = ROOT/'evals/interaction/cycle-24/reminder-recovery-protocol.json'
    protocol = json.loads(protocol_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    paths = [*ROOT.glob('src/avatar/**/*.py'),Path(__file__),ROOT/'scripts/lab/audit_reminder_delivery_baseline.py',protocol_path]
    hashes = {str(p.relative_to(ROOT)):digest(p) for p in paths}
    report = {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
              'source_sha256':hashes,'scope':'Three actual loopback HTTP/SQLite protocols, each two owned OS server processes; models disabled, no browser/human perception.',
              'cases':[],'completed':False,'model_or_gpu_used':False}
    def save(): write(output/'restart-recovery.json',report)
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='reminder-recovery-',dir=ROOT.parent/'runtime/tmp') as name:
            root = Path(name)
            for case in protocol['os_restart_cases']:
                folder = root/case; folder.mkdir(); evidence = output/case; evidence.mkdir(); db = folder/'owned.db'
                row = {'case':case,'seed':seed(db,{'due_offset_seconds':-60,'status':'active'}),'processes':[],'requests':[]}
                report['cases'].append(row)
                def request(url,path,payload=None,**kwargs):
                    result=send(url,path,payload,**kwargs);row['requests'].append(result);return result
                with service(db,folder,evidence,1,row['processes']) as url:
                    old = request(url,'/conversation')['envelope']['data']
                    first = request(url,'/reminders/deliveries/pending',{},discard=case=='unconsumed_pending_response')
                    assert first['status']==200
                    before = sql(db); event=before['deliveries'][0]['id']; row['before_restart']=before
                    if case=='committed_ack_response_unconsumed':
                        assert request(url,f'/reminders/deliveries/{event}/ack',{'instance_id':old['instance_id'],'revision':old['revision']},discard=True)['status']==200
                        row['ack_committed_before_restart']=sql(db)
                with service(db,folder,evidence,2,row['processes']) as url:
                    current=request(url,'/conversation')['envelope']['data']
                    assert current['instance_id'] != old['instance_id']
                    pending=request(url,'/reminders/deliveries/pending',{})['envelope']['data']
                    old_ack=request(url,f'/reminders/deliveries/{event}/ack',{'instance_id':old['instance_id'],'revision':old['revision']})
                    assert old_ack['status']==409 and old_ack['envelope']['error']['code']=='delivery_instance_changed'
                    if case=='committed_ack_response_unconsumed':
                        assert pending['items']==[]
                        assert sql(db)['deliveries'][0]['acknowledged_at']==row['ack_committed_before_restart']['deliveries'][0]['acknowledged_at']
                    else:
                        assert len(pending['items'])==1 and pending['items'][0]['delivery_id']==event
                        assert sql(db)['deliveries'][0]['acknowledged_at'] is None
                    payload={'instance_id':current['instance_id'],'revision':current['revision']}
                    ack=request(url,f'/reminders/deliveries/{event}/ack',payload)
                    assert ack['status']==200 and ack['envelope']['data']['acknowledged_at'] is not None
                    duplicate=request(url,f'/reminders/deliveries/{event}/ack',payload)
                    assert duplicate['envelope']['data']==ack['envelope']['data']
                    assert request(url,'/reminders/deliveries/pending',{})['envelope']['data']['items']==[]
                    assert request(url,'/reminders/due',{})['envelope']['data']==[]
                row['final_sql']=sql(db)
                assert row['final_sql']['integrity']=='ok'
                assert all(p['exit_code']==0 and p['identity_after_wait'] is None for p in row['processes'])
                row['completed']=True;write(evidence/'case.json',row);save();print(case,'passed',flush=True)
        report['owned_temporary_directory_removed']=not root.exists()
        assert all(digest(ROOT/p)==value for p,value in hashes.items())
        report['source_unchanged_after_run']=True
        report['process_count']=sum(len(r['processes']) for r in report['cases'])
        report['http_request_count']=sum(len(r['requests']) for r in report['cases'])
        report['completed']=True
    except BaseException as error:
        report['failure']=repr(error);raise
    finally: save()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    run(parser.parse_args().output)

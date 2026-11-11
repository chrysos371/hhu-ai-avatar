"""Independent producer/server OS processes, shared owned DB, actual HTTP."""
import argparse
from contextlib import closing
from hashlib import sha256
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
from urllib.request import build_opener, ProxyHandler, Request

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from avatar.brain.action_receipts import ActionReceiptStore
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.config import config
from avatar.main import Avatar
from avatar.web import create_server


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def produce(path,case):
    class NoModel:
        available=False
    token=CancellationToken();bot=Avatar(db_path=str(path),llm=NoModel())
    try:
        private=bot.memory.remember_user('名字','OS回执受控私密名')
        original=bot.reminders.create
        def committed(*args,**kwargs):
            result=original(*args,**kwargs);token.cancel();return result
        if case=='cancel_after_commit':bot.reminders.create=committed
        try:
            result=bot.respond('提醒我明天下午3点OS回执正控',cancel=token)
            terminal='result'
            if case=='normal':bot.respond('取消提醒'+str(result['reminder']['id']))
        except Cancelled:terminal='cancelled'
        if case=='forget_after_commit':bot.memory.forget(private)
        return {'pid':os.getpid(),'terminal':terminal,'visible_receipts':ActionReceiptStore(bot.memory).read('producer'),
                'reminders':bot.reminders.list(),'ledger_rows':bot.memory._conn.execute('SELECT count(*) FROM memory_action_receipts').fetchone()[0],
                'assistant_count':bot.memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant' AND content!='[redacted]'").fetchone()[0]}
    finally:bot.memory.close()


def serve(path,ready):
    config.llm.api_key='';config.embedding.model=''
    server=create_server(str(path),port=0,legacy_writes=False)
    stopped=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stopped.set())
    thread=threading.Thread(target=server.serve_forever);thread.start()
    write(ready,{'pid':os.getpid(),'base':'http://127.0.0.1:'+str(server.server_port)+'/api/v1',
                 'token':server.token,'module':sys.modules['avatar.web'].__file__})
    try:stopped.wait()  # Owned server lifetime, no experiment deadline.
    finally:server.shutdown();thread.join();server.server_close()


def audit(output):
    if output.exists():raise FileExistsError(output)
    paths=[*ROOT.glob('src/avatar/**/*.py'),Path(__file__).resolve()]
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'source_sha256':{str(p.relative_to(ROOT)):sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
            'scope':'Three fresh DBs, six independent OS processes, actual authenticated HTTP. No model/network notification/device claims.',
            'cases':[],'completed':False}
    def save():write(output,report)
    save();opener=build_opener(ProxyHandler({}))
    for case in ('normal','cancel_after_commit','forget_after_commit'):
        row={'case':case,'cleanup':False};report['cases'].append(row)
        with tempfile.TemporaryDirectory(prefix='receipt-os-',dir=ROOT.parent/'runtime/tmp') as folder:
            db=Path(folder)/'owned.db';ready=Path(folder)/'ready.json'
            command=[sys.executable,str(Path(__file__).resolve())]
            producer=subprocess.Popen([*command,'--producer',str(db),'--case',case],cwd=ROOT,
                                      stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            stdout,stderr=producer.communicate();row['producer_exit']=producer.returncode
            row['producer']=json.loads(stdout);row['producer_stderr']=stderr
            assert producer.returncode==0 and row['producer']['pid']==producer.pid
            with (Path(folder)/'server.log').open('w') as stream:
                server=subprocess.Popen([*command,'--serve',str(db),'--ready',str(ready)],cwd=ROOT,
                    stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT)
                row['server_pid']=server.pid
                try:
                    while not ready.exists():
                        if server.poll() is not None:raise RuntimeError('Owned reader server exited before ready')
                        time.sleep(.05)
                    info=json.loads(ready.read_text());row['server_module']=info['module']
                    assert info['pid']==server.pid and server.pid!=producer.pid
                    req=Request(info['base']+'/conversation/actions',headers={'X-Avatar-Token':info['token']})
                    with opener.open(req,timeout=15) as response:
                        row['http_status']=response.status;row['http']=json.load(response)
                    data=row['http']['data'];before=row['producer']['visible_receipts']
                    assert data['instance_id']!='producer' and data['revision']==before['revision']
                    assert data['items']==before['items']
                    assert len(data['items'])=={'normal':2,'cancel_after_commit':1,'forget_after_commit':0}[case]
                    assert row['producer']['terminal']==('cancelled' if case=='cancel_after_commit' else 'result')
                    assert row['producer']['ledger_rows']==(2 if case=='normal' else 1)
                    assert 'OS回执受控私密名' not in json.dumps(data,ensure_ascii=False)
                    assert data['notification_delivery_verified'] is False
                finally:
                    if server.poll() is None:server.terminate()  # Only this Popen-owned server.
                    row['server_exit']=server.wait();stream.flush()
                    row['server_log']=(Path(folder)/'server.log').read_text()
            with closing(sqlite3.connect(db)) as conn:
                row['integrity_check']=conn.execute('PRAGMA integrity_check').fetchone()[0]
            assert row['server_exit']==0 and row['integrity_check']=='ok'
        row['cleanup']=not Path(folder).exists();save()
    assert all(sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in report['source_sha256'].items())
    report['completed']=True;save();return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--producer',type=Path);parser.add_argument('--case')
    parser.add_argument('--serve',type=Path);parser.add_argument('--ready',type=Path);parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.producer:print(json.dumps(produce(args.producer,args.case),ensure_ascii=False))
    elif args.serve:serve(args.serve,args.ready)
    elif args.output:
        result=audit(args.output)
        for row in result['cases']:print(row['case'],'HTTP receipts',len(row['http']['data']['items']),
            'producer/server exit',row['producer_exit'],row['server_exit'],'integrity',row['integrity_check'],'cleanup',row['cleanup'])
    else:parser.error('select producer, serve or output')

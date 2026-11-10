"""Offline fixed-round turn durability audit; never opens the user's database."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import threading
import time
import urllib.request

from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.config import config
from avatar.lab.transport_fixture import controlled_provider
from avatar.web import create_server


def rss_mib():
    return int(Path('/proc/self/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')/1048576


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Use new evidence path')
    report={'scope':'500 sequential offline turns, not multi-day stability or real LLM quality',
        'rounds':500,'checkpoints':[],'failure':None}
    with ExitStack() as stack:
        folder=Path(stack.enter_context(tempfile.TemporaryDirectory(prefix='avatar-turn-soak-')))
        _,url=stack.enter_context(controlled_provider(delay=.0005))
        config.llm.base_url=url;config.llm.api_key='offline-soak';config.llm.model='fixture';config.embedding.model=''
        db=folder/'soak.db';server=create_server(str(db),port=0)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        def request(path,data=None):
            req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1'+path,
                data=None if data is None else json.dumps(data).encode(),
                headers={'X-Avatar-Token':server.token,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)['data']
        started=time.perf_counter();completed=0;last_id=None
        try:
            for index in range(500):
                if index%50==0:
                    store=MemoryStore(str(db));store.remember_user('名字','耐久测试名字');store.close()
                body={'request_id':secrets.token_urlsafe(24),'text':f'请简短解释云为什么会移动。第{index}轮。'}
                last_id=body['request_id'];request('/turns',body)
                for _ in range(3000):
                    status=request('/turns/'+last_id)
                    if status['status'] in ['completed','failed','cancelled']:break
                    time.sleep(.01)
                assert status['status']=='completed',status['status']
                assert status['result']['generation_mode']=='llm'
                if index%5==0:
                    duplicate=request('/turns',body)
                    assert duplicate['job_id']==last_id and duplicate['status']=='completed'
                assert len(server.turns._jobs)<=32
                with sqlite3.connect(db) as connection:
                    assert connection.execute("SELECT count(*) FROM memory_messages WHERE role='user'").fetchone()[0]==index+1
                completed=index+1
                if completed%50==0:
                    store=MemoryStore(str(db));fragment=next(row for row in store.list_memories() if row['memory_type']=='user_profile')
                    store.forget(fragment['id']);store.close();server.turns.refresh_privacy()
                    assert not server.turns._jobs
                    with sqlite3.connect(db) as connection:
                        remaining=connection.execute("SELECT count(*) FROM memory_messages WHERE role='assistant' AND content!='[redacted]'").fetchone()[0]
                        assert remaining==0
                        ledger=connection.execute('SELECT count(*) FROM runtime_turn_ledger').fetchone()[0]
                        integrity=connection.execute('PRAGMA integrity_check').fetchone()[0]
                    report['checkpoints'].append({'round':completed,'seconds':time.perf_counter()-started,
                        'rss_mib':rss_mib(),'threads':threading.active_count(),'job_cache':len(server.turns._jobs),
                        'ledger_rows':ledger,'db_bytes':db.stat().st_size,'integrity':integrity,
                        'unredacted_assistants_after_forget':remaining})
                    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                    print(completed,report['checkpoints'][-1],flush=True)
            # Dedicated final TTL check without another submission.
            body={'request_id':secrets.token_urlsafe(24),'text':'请简短解释云为什么会移动。'}
            request('/turns',body)
            while server.turns.get(body['request_id']).status not in ['completed','failed','cancelled']:time.sleep(.01)
            server.turns.ttl=.05
            time.sleep(.06)
            expired=False
            try:server.turns.get(body['request_id'])
            except OperationError as exc:expired=exc.status==404
            report.update(completed_rounds=completed,ttl_without_submission=expired,
                rss_growth_after_round50_mib=report['checkpoints'][-1]['rss_mib']-report['checkpoints'][0]['rss_mib'])
            report['passed']=completed==500 and expired and report['rss_growth_after_round50_mib']<=150 and all(
                row['threads']<=40 and row['integrity']=='ok' and row['ledger_rows']==row['round'] for row in report['checkpoints'])
        except Exception as exc:
            report.update(failure=type(exc).__name__,completed_rounds=completed,passed=False)
            raise
        finally:
            server.shutdown();server.server_close();worker.join(2)
            report['seconds']=time.perf_counter()-started
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print('passed',report['passed'],flush=True)


if __name__=='__main__':main()

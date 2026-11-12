"""Local bounded development patrol. Signals are not semantic approval.

No production conversation scanning, cloud judges, training or automatic release.
"""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from .common import PROJECT, atomic_text, source_state

DEFAULT_ROOT = PROJECT / 'data/improvement'
SUITE = PROJECT / 'experiments/improvement/development.json'


def signals(text, reply, previous='', trace=None):
    trace = trace or {}
    found = []
    if trace.get('reply_degraded'):
        found.append('generation_degraded')
    if not isinstance(reply, str) or not reply.strip():
        return found + ['empty_reply']
    norm = lambda s: re.sub(r'\s|[，。！？,.!?～~]', '', s)
    if previous and norm(previous) == norm(reply):
        found.append('verbatim_repeat')
    if re.search(r'只想.{0,6}(?:抱怨|吐槽)|先别教|不要建议', text):
        if re.search(r'建议|要不|不如|你可以|别太较真|别太在意|别太放在心上|专心准备', reply):
            found.append('possible_unwanted_advice')
    if re.search(r'吃饭|洗澡|食堂', text) and not re.search(r'睡|晚安|晚饭', text) and '晚安' in reply:
        found.append('unexpected_goodnight')
    if re.search(r'拜拜|再见', text) and re.search(r'[？?]', reply):
        found.append('departure_question')
    if re.search(r'只输出JSON', text):
        try:
            json.loads(reply)
        except (ValueError, TypeError):
            found.append('invalid_json')
    if re.search(r'四字标题', text) and not re.fullmatch(r'[\u4e00-\u9fff]{4}', reply.strip()):
        found.append('title_format')
    if (not re.search(r'故事|小说|剧本|扮演|虚构', text)
            and re.search(r'(?:我们|咱们|下次|要不要|可以).{0,10}一起(?:喝|吃|去|游泳|见面)', reply)):
        found.append('possible_physical_invitation')
    if re.search(r'[A-Za-z]{3,}', reply) and not re.search(r'JSON|英文|英语|代码|DeepSeek', text):
        found.append('possible_language_drift')
    return sorted(set(found))


@contextmanager
def exclusive(root):
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


class Store:
    def __init__(self, root=DEFAULT_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.root/'issues.db', timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, day TEXT, started REAL,
            finished REAL, status TEXT, turns INTEGER DEFAULT 0, meta TEXT);
        CREATE TABLE IF NOT EXISTS cases(run_id TEXT, case_id TEXT, PRIMARY KEY(run_id,case_id));
        CREATE TABLE IF NOT EXISTS issues(id TEXT PRIMARY KEY, category TEXT, first_seen REAL, last_seen REAL);
        CREATE TABLE IF NOT EXISTS occurrences(id TEXT PRIMARY KEY, issue_id TEXT, source TEXT, case_id TEXT, turn INTEGER, created REAL);
        ''')
        self.db.commit()
        (self.root/'issues.db').chmod(0o600)

    def ingest(self, rows, source):
        added = 0
        prior = {}
        with self.db:
            for row in rows:
                key = row['case']
                reply = row.get('reply', '')
                kinds = signals(row['user'], reply, prior.get(key,''), row.get('trace'))
                if row.get('error'):
                    kinds.append('call_error')
                prior[key] = reply
                for kind in kinds:
                    issue = hashlib.sha256(('xiaofeiyu:'+kind).encode()).hexdigest()[:20]
                    oid = hashlib.sha256(f'{source}:{key}:{row["turn"]}:{kind}'.encode()).hexdigest()
                    now = time.time()
                    cursor = self.db.execute('INSERT OR IGNORE INTO occurrences VALUES(?,?,?,?,?,?)',
                                             (oid,issue,source,key,row['turn'],now))
                    if cursor.rowcount:
                        self.db.execute('INSERT INTO issues VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET last_seen=excluded.last_seen',
                                        (issue,kind,now,now))
                        added += 1
        return added

    def close(self):
        self.db.close()


def summary(root=DEFAULT_ROOT):
    path = Path(root)/'issues.db'
    if not path.exists():
        return {'available':False, 'reason':'尚未生成巡检记录', 'runs':[], 'issues':[]}
    db = sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True, timeout=3)
    db.row_factory = sqlite3.Row
    try:
        return {'available':True, 'mode':'development-signals-only', 'automatic_release':False,
                'runs':[dict(r) for r in db.execute('SELECT id,day,started,finished,status,turns FROM runs ORDER BY started DESC LIMIT 10')],
                'issues':[dict(r) for r in db.execute('SELECT i.*,COUNT(o.id) AS occurrences FROM issues i JOIN occurrences o ON o.issue_id=i.id GROUP BY i.id ORDER BY last_seen DESC LIMIT 30')]}
    finally:
        db.close()


def report(root=DEFAULT_ROOT):
    data = summary(root)
    atomic_text(Path(root)/'latest.json', json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    day = datetime.now().astimezone().strftime('%Y-%m-%d')
    lines = ['# 数字人开发巡检日报 '+day, '', '自动规则信号，不代表语义批准或能力增长。仅合成开发场景，无自动训练、发布和外发。', '',
             '## 最近批次', '']
    lines += [f'- {r["id"]}：{r["status"]}，已执行{r["turns"]}轮' for r in data['runs']]
    lines += ['', '## 待定位信号（历史累计，未自动判定已修复）', '']
    lines += [f'- {i["category"]}：{i["occurrences"]}次，证据分类ID {i["id"]}' for i in data['issues']]
    if not data['issues']:
        lines.append('- 没有被当前检查器命中的信号；不等于没有问题。')
    atomic_text(Path(root)/'reports'/f'{day}.md','\n'.join(lines)+'\n')
    return data


def run(root=DEFAULT_ROOT, *, max_turns=6, daily_turns=24, chat_factory=None, skills_enabled=None):
    if not 1 <= max_turns <= 12 or not 1 <= daily_turns <= 48:
        raise ValueError('patrol budget outside bounds')
    root = Path(root)
    with exclusive(root):
        store = Store(root)
        try:
            # A killed worker leaves an auditable interrupted record.
            store.db.execute("UPDATE runs SET status='interrupted',finished=? WHERE status='running'", (time.time(),))
            for previous in store.db.execute('SELECT id FROM runs ORDER BY started DESC LIMIT 20').fetchall():
                evidence = root/'runs'/previous['id']/'turns.jsonl'
                if evidence.exists():
                    recovered = []
                    for line in evidence.read_text().splitlines():
                        try: recovered.append(json.loads(line))
                        except ValueError: pass  # Only a partial final line can survive an interrupted write.
                    store.ingest(recovered,previous['id'])
            day = datetime.now().astimezone().strftime('%Y-%m-%d')
            used = store.db.execute('SELECT COALESCE(SUM(turns),0) FROM runs WHERE day=?',(day,)).fetchone()[0]
            allowance = min(max_turns, daily_turns-used)
            suite = json.loads(SUITE.read_text())
            from ..conversation.tools import tool_request
            if any(tool_request(text) for case in suite['cases'] for text in case['turns']):
                raise ValueError('synthetic patrol does not permit tool requests')
            last = dict(store.db.execute('SELECT case_id,MAX(r.started) FROM cases c JOIN runs r ON r.id=c.run_id GROUP BY case_id'))
            selected = []
            for case in sorted(suite['cases'], key=lambda c:(last.get(c['id'],0),c['id'])):
                if len(case['turns']) <= allowance:
                    selected.append(case);allowance -= len(case['turns'])
            if not selected:
                store.db.commit();report(root)
                return {'status':'skipped_budget', 'turns':0}
            rid = datetime.now().strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8]
            folder = root/'runs'/rid;folder.mkdir(parents=True,mode=0o700)
            from ..characters.library import CharacterLibrary, CARD_MAP
            profile = CharacterLibrary().model_profile('xiaofeiyu') if chat_factory is None else None
            if profile:
                from urllib.parse import urlsplit
                if urlsplit(profile.base_url).hostname not in ('127.0.0.1','localhost','::1'):
                    raise ValueError('patrol permits local model endpoints only')
            meta = {'suite':suite,'selected':[c['id'] for c in selected], 'source':source_state(),
                    'model':profile.public() if profile else {'test_double':True},
                    'character_card':CARD_MAP['xiaofeiyu'], 'synthetic':True,
                    'production_persona_used':False, 'automatic_release':False, 'banter_enabled':os.getenv('AVATAR_BANTER_ENABLED','0')=='1', 'skills_enabled':(os.getenv('AVATAR_SKILLS_ENABLED','0')=='1') if skills_enabled is None else skills_enabled}
            atomic_text(folder/'metadata.json',json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
            store.db.execute('INSERT INTO runs(id,day,started,status,meta) VALUES(?,?,?,\'running\',?)',
                             (rid,day,time.time(),json.dumps(meta,ensure_ascii=False)))
            store.db.commit()
            failures=0;rows=[]
            with (folder/'turns.jsonl').open('w') as evidence:
                for case in selected:
                    lib = chat_factory(folder/'sessions'/case['id']) if chat_factory else CharacterLibrary(folder/'sessions'/case['id'], skills_enabled=skills_enabled)
                    if profile and profile.id != 'default':lib.select_model('xiaofeiyu',profile.id)
                    store.db.execute('INSERT INTO cases VALUES(?,?)',(rid,case['id']));store.db.commit()
                    for n,text in enumerate(case['turns'],1):
                        # Reserve before calling: errors/restarts cannot evade daily budgets.
                        store.db.execute('UPDATE runs SET turns=turns+1 WHERE id=?',(rid,));store.db.commit()
                        start=time.monotonic()
                        try:
                            result=lib.chat('xiaofeiyu',text)
                            row={'case':case['id'],'turn':n,'user':text,**result}
                            if result.get('trace',{}).get('reply_degraded'):failures+=1
                        except Exception as exc:
                            row={'case':case['id'],'turn':n,'user':text,'error':type(exc).__name__}
                            failures+=1
                        row['elapsed_s']=round(time.monotonic()-start,3)
                        rows.append(row);evidence.write(json.dumps(row,ensure_ascii=False)+'\n');evidence.flush()
                        if failures:break
                    if failures:break
            store.ingest(rows,rid)
            status='completed_with_errors' if failures else 'completed'
            store.db.execute('UPDATE runs SET status=?,finished=? WHERE id=?',(status,time.time(),rid));store.db.commit()
            report(root)
            return {'status':status,'run_id':rid,'turns':len(rows)}
        finally:
            store.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['run','import-synthetic','report'])
    parser.add_argument('--root',type=Path,default=DEFAULT_ROOT)
    parser.add_argument('--input',type=Path)
    parser.add_argument('--max-turns',type=int,default=6)
    parser.add_argument('--daily-turns',type=int,default=24)
    parser.add_argument('--skills',choices=['default','on','off'],default='default')
    parser.add_argument('--banter',choices=['default','on','off'],default='default')
    args=parser.parse_args()
    if args.banter!='default':os.environ['AVATAR_BANTER_ENABLED']='1' if args.banter=='on' else '0'
    root=args.root.resolve()
    if not root.is_relative_to(PROJECT.parent.resolve()):raise ValueError('root must stay in workspace')
    if args.command=='run':result=run(root,max_turns=args.max_turns,daily_turns=args.daily_turns,skills_enabled={'default':None,'on':True,'off':False}[args.skills])
    elif args.command=='report':result=report(root)
    else:
        if not args.input:parser.error('--input is required')
        path=args.input.resolve()
        if not path.is_relative_to((PROJECT/'data/research').resolve()):raise ValueError('only explicitly selected research evidence may be imported')
        if path.stat().st_size>5*1024*1024:raise ValueError('input too large')
        content=path.read_bytes();rows=[json.loads(s) for s in content.decode().splitlines()]
        with exclusive(root):
            store=Store(root)
            try:result={'new_occurrences':store.ingest(rows,'import-'+hashlib.sha256(content).hexdigest())};report(root)
            finally:store.close()
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()

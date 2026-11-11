"""Authenticated HTTP/SSE local-action invalidation, no model or notification."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import build_opener, ProxyHandler, Request
import uuid

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.config import config
from avatar.web import create_server

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from evaluate_native_output_audit import events


def audit(output):
    if output.exists(): raise FileExistsError(output)
    paths = [*ROOT.glob('src/avatar/**/*.py'), Path(__file__).resolve(), ROOT/'scripts/evaluate_native_output_audit.py']
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=ROOT).strip(),
              'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
              'scope': 'Real authenticated HTTP turns, cancellation HTTP, SSE and independent forget SQL. Controlled store-entry scheduling. No model, external notification or device.',
              'cases': [], 'completed': False}
    def save(): output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save(); opener = build_opener(ProxyHandler({})); config.llm.api_key = ''; config.embedding.model = ''
    for operation in ('create', 'set_status', 'claim_due'):
        for change in ('normal', 'cancel', 'forget'):
            row = {'operation': operation, 'change': change, 'cleanup': False}; report['cases'].append(row)
            entered, proceed = threading.Event(), threading.Event()
            with tempfile.TemporaryDirectory(prefix='reminder-http-', dir=ROOT.parent/'runtime/tmp') as folder:
                path = str(Path(folder)/'owned.db')
                server = create_server(path, port=0, legacy_writes=False)
                with closing(MemoryStore(path)) as seed:
                    fragment = seed.remember_user('名字', 'HTTP事务实验名'); store = ReminderStore(seed)
                    if operation != 'create':
                        seeded = store.create('提醒我明天下午3点HTTP正控')
                        if operation == 'claim_due':
                            with seed.transaction():
                                seed._conn.execute('UPDATE memory_reminders SET due_at=?', (time.time()-10,))
                    row['before'] = store.list()
                original = getattr(ReminderStore, operation)
                def scheduled(self, *args, **kwargs):
                    assert self.memory.db_path == path and not self.conn.in_transaction
                    entered.set()
                    if not proceed.wait(15): raise RuntimeError('HTTP fixture did not release boundary')
                    return original(self, *args, **kwargs)
                setattr(ReminderStore, operation, scheduled)
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                base = 'http://127.0.0.1:'+str(server.server_port)+'/api/v1'
                def request(route, payload=None):
                    return Request(base+route, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                                   headers={'X-Avatar-Token': server.token, 'Content-Type': 'application/json'})
                def query(route, payload=None):
                    with opener.open(request(route, payload), timeout=20) as response: return json.load(response)['data']
                text = ('提醒我明天下午3点HTTP正控' if operation == 'create' else
                        '取消提醒'+str(seeded['id']) if operation == 'set_status' else '你好')
                try:
                    started = time.perf_counter()
                    job = query('/turns', {'request_id': 'reminder_http_'+uuid.uuid4().hex, 'text': text, 'use_web': False})
                    row['job'] = job
                    assert entered.wait(10)
                    # Subscribe before independent forget so the raw terminal is observable;
                    # no later API read is used to bypass coordinator privacy redaction.
                    with opener.open(request('/turns/'+job['job_id']+'/events'), timeout=20) as stream:
                        if change == 'cancel': row['cancel_http'] = query('/turns/'+job['job_id']+'/cancel', {})
                        elif change == 'forget':
                            with closing(MemoryStore(path)) as writer: writer.forget(fragment)
                        proceed.set()
                        terminal, result, received, raw = events(stream, started)
                    row.update(terminal=terminal, result=result, events=received, raw_sse=raw)
                    with closing(MemoryStore(path)) as memory:
                        row['after'] = ReminderStore(memory).list(); row['revision'] = memory.context_revision
                        row['assistant_count'] = memory._conn.execute(
                            "SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]
                    row['business_changed'] = row['before'] != row['after']
                    assert terminal == ('result' if change == 'normal' else 'cancelled')
                    assert row['business_changed'] is (change == 'normal')
                    assert row['assistant_count'] == (1 if change == 'normal' else 0)
                finally:
                    proceed.set(); server.shutdown(); thread.join(); server.server_close()
                    setattr(ReminderStore, operation, original); save()
            row['cleanup'] = not Path(folder).exists(); save()
    assert all(sha256((ROOT/name).read_bytes()).hexdigest() == value for name,value in report['source_sha256'].items())
    report['completed'] = True; save(); return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    result = audit(parser.parse_args().output)
    for row in result['cases']:
        print(row['operation'], row['change'], row['terminal'], 'SQL changed', row['business_changed'],
              'assistant', row['assistant_count'], 'revision', row['revision'])

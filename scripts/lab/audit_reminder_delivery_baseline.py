"""Actual disposable HTTP/SQLite/OS baseline; no model or notification device."""
import argparse
from contextlib import closing, contextmanager
from datetime import datetime, timezone
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
from urllib.request import ProxyHandler, Request, build_opener

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from avatar.paths import project_data_root
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.config import config
from avatar.web import create_server
import avatar.main
import avatar.web

PROTOCOL = ROOT / 'evals/interaction/cycle-24/reminder-delivery-protocol.json'
TOKEN = 'reminder-delivery-disposable-fixture-token'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def identity(pid):
    try:
        folder = Path('/proc') / str(pid)
        fields = (folder / 'stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0],
                'argv': (folder / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')}
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return None


def snapshot(db):
    with sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True) as conn:
        conn.row_factory = sqlite3.Row
        return {'reminders': [dict(row) for row in conn.execute('SELECT * FROM memory_reminders ORDER BY id')],
                'integrity': conn.execute('PRAGMA integrity_check').fetchone()[0]}


def seed(db, case):
    now = time.time()
    with closing(MemoryStore(str(db))) as memory:
        store = ReminderStore(memory)
        original = store.create('提醒我明天下午3点到期投递实验提醒', now=now)
        with memory.transaction():
            memory._conn.execute('UPDATE memory_reminders SET due_at=?,status=? WHERE id=?',
                                 (now + case['due_offset_seconds'], case['status'], original['id']))
    return {'created_by_actual_store': original, 'controlled_due_offset_seconds': case['due_offset_seconds'],
            'clock_utc': datetime.fromtimestamp(now, timezone.utc).isoformat(),
            'scope': 'Controlled due timestamp, not naturally elapsed scheduling or dialog creation evidence.',
            'initial_sql': snapshot(db)}


def worker(db, ready):
    config.llm.api_key = ''
    config.embedding.model = ''
    server = create_server(str(db), port=0, legacy_writes=False)
    server.token = TOKEN
    stopping = threading.Event()
    def stop(signum, frame):
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, stop)
    modules = (avatar.main, avatar.web)
    paths = {m.__name__: Path(m.__file__).resolve() for m in modules}
    if not all(path.is_relative_to(ROOT / 'src') for path in paths.values()):
        raise RuntimeError('Worker imported another project')
    value = {'url': f'http://127.0.0.1:{server.server_port}/api/v1', 'pid': os.getpid(),
             'identity': identity(os.getpid()), 'llm_enabled': False,
             'module_paths': {name: str(path) for name, path in paths.items()},
             'module_sha256': {name: digest(path) for name, path in paths.items()}}
    temporary = ready.with_suffix('.part')
    write(temporary, value)
    os.replace(temporary, ready)
    try:
        server.serve_forever()
    finally:
        server.server_close()


@contextmanager
def service(db, scratch, evidence, index, processes):
    ready = scratch / f'ready-{index}.json'
    command = [sys.executable, str(Path(__file__).resolve()), '--worker-db', str(db), '--ready', str(ready)]
    with (evidence / f'worker-{index}.log').open('x') as stream:
        process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        record = {'argv': command, 'pid': process.pid, 'start_identity': identity(process.pid)}
        processes.append(record)
        try:
            deadline = time.monotonic() + 20  # Startup observation, not an experiment deadline.
            while not ready.exists():
                if process.poll() is not None:
                    raise RuntimeError('Worker exited before ready: ' + str(process.returncode))
                if time.monotonic() >= deadline:
                    raise RuntimeError('Worker startup observation timed out')
                time.sleep(.02)
            state = json.loads(ready.read_text())
            assert state['pid'] == process.pid and not state['llm_enabled']
            record['ready'] = state
            yield state['url']
        finally:
            if process.poll() is None:
                process.terminate()  # Only the Popen-owned child.
            try:
                record['exit_code'] = process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                record['exit_code'] = process.wait()
                record['forced_cleanup'] = True
            record['identity_after_wait'] = identity(process.pid)


def request(url, route, *, post=False, discard=False):
    opener = build_opener(ProxyHandler({}))
    req = Request(url + route, data=b'{}' if post else None,
                  headers={'X-Avatar-Token': TOKEN, 'Content-Type': 'application/json'})
    started = time.monotonic()
    with opener.open(req, timeout=15) as response:
        row = {'route': route, 'method': 'POST' if post else 'GET', 'status': response.status,
               'body_consumed': not discard}
        if not discard:
            row['envelope'] = json.load(response)
        else:
            row['scope'] = 'Close after committed response headers without consuming JSON; not proof of wire loss or UI visibility.'
    row['seconds'] = time.monotonic() - started
    return row


def baseline(output):
    if sys.flags.optimize:
        raise RuntimeError('Run baseline checks without Python optimization')
    protocol = json.loads(PROTOCOL.read_text())
    assert len(protocol['http_cases']) == 8 and len(protocol['os_restart_protocols']) == 2
    assert all(digest(ROOT / name) == expected for name, expected in protocol['source_sha256'].items())
    output.mkdir(parents=True, exist_ok=False)
    report = {'scope': protocol['scope'], 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'probe_sha256': digest(Path(__file__)), 'protocol_sha256': digest(PROTOCOL),
              'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in ROOT.glob('src/avatar/**/*.py')},
              'http_cases': [], 'os_protocols': [], 'completed': False, 'failure': None,
              'model_or_gpu_used': False, 'physical_notification_or_human_approval': False}
    def save():
        write(output / 'baseline.json', report)
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='reminder-delivery-baseline-', dir=project_data_root(ROOT)/'tmp') as name:
            root = Path(name)
            for case in protocol['http_cases']:
                folder = root / case['id']
                folder.mkdir()
                evidence = output / case['id']
                evidence.mkdir()
                db = folder / 'owned.db'
                row = {'id': case['id'], 'seed': seed(db, case), 'processes': [], 'requests': [],
                       'ui_observed': False, 'scope': 'HTTP/SQLite control; navigation/render claims require separate Chromium evidence.'}
                report['http_cases'].append(row)
                with service(db, folder, evidence, 1, row['processes']) as url:
                    discard = case['id'] in ('response_drop_after_commit', 'restart_after_claim')
                    first = request(url, '/reminders/due', post=True, discard=discard)
                    row['requests'].append(first)
                    row['sql_after_first'] = snapshot(db)
                    if case['id'] != 'restart_after_claim':
                        row['requests'].append(request(url, '/reminders/due', post=True))
                        row['requests'].append(request(url, '/reminders'))
                if case['id'] == 'restart_after_claim':
                    with service(db, folder, evidence, 2, row['processes']) as url:
                        row['requests'].append(request(url, '/reminders/due', post=True))
                        row['requests'].append(request(url, '/reminders'))
                row['final_sql'] = snapshot(db)
                claimed = case['id'] not in ('future_not_due', 'cancelled_due', 'expired_older24h')
                assert bool(row['final_sql']['reminders'][0]['notified_at']) is claimed
                assert row['requests'][1]['envelope']['data'] == []
                if not discard:
                    assert len(first['envelope']['data']) == int(claimed)
                assert row['final_sql']['integrity'] == 'ok'
                assert all(p['exit_code'] == 0 and p['identity_after_wait'] is None for p in row['processes'])
                row['completed'] = True
                write(evidence / 'case.json', row)
                save()
                print(case['id'], 'claimed', claimed, 'second_claim0', flush=True)
            for case_id in protocol['os_restart_protocols']:
                folder = root / case_id
                folder.mkdir()
                evidence = output / case_id
                evidence.mkdir()
                db = folder / 'owned.db'
                row = {'id': case_id, 'seed': seed(db, {'due_offset_seconds': -60, 'status': 'active'}),
                       'processes': [], 'ui_observed': False}
                report['os_protocols'].append(row)
                with service(db, folder, evidence, 1, row['processes']) as url:
                    row['producer_response'] = request(url, '/reminders/due', post=True,
                                                       discard=case_id == 'claim_without_render_restart')
                    row['after_producer'] = snapshot(db)
                with service(db, folder, evidence, 2, row['processes']) as url:
                    row['consumer_response'] = request(url, '/reminders/due', post=True)
                    row['consumer_list'] = request(url, '/reminders')
                row['final_sql'] = snapshot(db)
                assert row['consumer_response']['envelope']['data'] == []
                assert row['final_sql']['reminders'][0]['notified_at'] is not None
                assert row['final_sql']['integrity'] == 'ok'
                assert len({p['pid'] for p in row['processes']}) == 2
                assert all(p['exit_code'] == 0 and p['identity_after_wait'] is None for p in row['processes'])
                row['completed'] = True
                write(evidence / 'case.json', row)
                save()
                print(case_id, 'two_real_processes, persisted_claim_no_replay', flush=True)
        report['owned_temporary_directory_removed'] = not root.exists()
        report['completed'] = True
    except Exception as error:
        report['failure'] = repr(error)
        raise
    finally:
        save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker-db', type=Path)
    parser.add_argument('--ready', type=Path)
    args = parser.parse_args()
    if args.worker_db:
        worker(args.worker_db, args.ready)
    elif args.output:
        baseline(args.output)
    else:
        parser.error('Use --output or --worker-db/--ready')

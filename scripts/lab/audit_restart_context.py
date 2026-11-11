"""Actual owned OS-process restarts; deterministic source/authority audit only."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]


def serve(db, state):
    from avatar.config import config
    from avatar.web import create_server
    config.llm.api_key = ''
    config.embedding.model = ''
    server = create_server(str(db), port=0, legacy_writes=False)
    def snapshot():
        return {'pid': os.getpid(), 'instance': server.session_id,
                'short_term': server.short_term, 'context_revision': server.context_revision,
                'speaker': server.speaker_scope.data()}
    stopping = threading.Event()
    def stop(_signum, _frame):
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}', 'token': server.token,
                      'initial': snapshot()}), flush=True)
    try:
        server.serve_forever()
    finally:
        state.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2)+'\n')
        server.server_close()


class OwnedServer:
    def __init__(self, db, folder, label):
        self.state = folder/(label+'-state.json')
        self.log = (folder/(label+'-stderr.log')).open('x')
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve',
                                      '--db', str(db), '--state', str(self.state)], cwd=ROOT,
                                     stdout=subprocess.PIPE, stderr=self.log, text=True)
        try:
            self.ready = json.loads(self.proc.stdout.readline())
        except BaseException:
            self.close()
            raise

    def request(self, path, data=None):
        request = Request(self.ready['url']+'/api/v1'+path,
                          data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
                          headers={'X-Avatar-Token': self.ready['token'], 'Content-Type': 'application/json'})
        try:
            with urlopen(request, timeout=30) as response:
                return response.status, json.load(response)
        except HTTPError as response:
            return response.code, json.load(response)

    def data(self, path, data=None):
        status, body = self.request(path, data)
        if not 200 <= status < 300:
            raise RuntimeError(f'{path} {status}: {body}')
        return body['data']

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
        code = self.proc.wait()
        self.proc.stdout.close()
        self.log.close()
        if code:
            raise RuntimeError(f'Owned service exited {code}')
        return json.loads(self.state.read_text())


def database(db):
    from avatar.brain.memory import MemoryStore
    with closing(MemoryStore(str(db))) as memory:
        return {'revision': memory.context_revision, 'profile': memory.get_user_profile(),
                'facts': [{k: v for k, v in row.items() if k != 'content_vector'}
                          for row in memory.list_memories(include_history=True)],
                'messages': [dict(row) for row in memory._conn.execute('SELECT * FROM memory_messages ORDER BY id')],
                'reminders': [dict(row) for row in memory._conn.execute('SELECT * FROM memory_reminders ORDER BY id')]}


def audit(output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = ROOT/'evals/interaction/cycle-13/restart-protocol.json'
    sources = ['src/avatar/web.py', 'src/avatar/main.py', 'src/avatar/brain/speaker_scope.py',
               'src/avatar/brain/memory.py', 'src/avatar/brain/reminders.py', 'src/avatar/turns.py',
               str(protocol.relative_to(ROOT)), str(Path(__file__).resolve().relative_to(ROOT))]
    report = {'scope': 'Actual separate OS processes, deterministic offline rules, synthetic disposable databases only',
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sourceSha256': {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
              'cases': [], 'completed': False}
    started = time.monotonic()
    def save():
        report['elapsedSeconds'] = time.monotonic()-started
        (output/'restart.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    for case in json.loads(protocol.read_text())['cases']:
        row = {'id': case['id'], 'before': [], 'after': [], 'checks': {}, 'failure': None}
        report['cases'].append(row)
        folder = output/case['id']; folder.mkdir()
        current = None
        try:
            with tempfile.TemporaryDirectory(prefix='restart-audit-', dir=ROOT.parent/'runtime/tmp') as temporary:
                db = Path(temporary)/'owned.db'
                current = OwnedServer(db, folder, 'first')
                row['firstInitial'] = current.ready['initial']
                if case['id'] == 'durable_request_id':
                    data = {'request_id': 'restart-audit-once-only-12345', 'text': case['before'][0]}
                    job = current.data('/turns', data)
                    while job['status'] in ('queued', 'running'):
                        time.sleep(.01); job = current.data('/turns/'+data['request_id'])
                    if job['status'] != 'completed': raise RuntimeError('baseline turn did not complete')
                    row['before'].append(job)
                else:
                    for text in case['before']:
                        row['before'].append({'input': text, 'result': current.data('/chat', {'text': text})})
                row['firstFinal'] = current.close(); current = None
                row['databaseBefore'] = database(db)
                if case.get('between'):
                    from avatar.brain.memory import MemoryStore
                    with closing(MemoryStore(str(db))) as memory:
                        for fact in memory.list_memories(): memory.forget(fact['id'])
                    row['databaseAfterPrivacy'] = database(db)
                current = OwnedServer(db, folder, 'second')
                row['secondInitial'] = current.ready['initial']
                row['snapshotBeforeContinuation'] = current.data('/conversation')
                row['checks']['new_pid'] = row['firstInitial']['pid'] != row['secondInitial']['pid']
                row['checks']['new_instance'] = row['firstInitial']['instance'] != row['secondInitial']['instance']
                if case['id'] == 'durable_request_id':
                    status, body = current.request('/turns', data)
                    row['after'].append({'status': status, 'body': body})
                    row['checks']['replay_rejected'] = status == case['expected_status']
                else:
                    for text in case['after']:
                        row['after'].append({'input': text, 'result': current.data('/chat', {'text': text})})
                row['databaseAfter'] = database(db)
                row['secondFinal'] = current.close(); current = None
                after = row['databaseAfter']
                if case['id'] == 'durable_request_id':
                    row['checks']['messages_unchanged'] = after['messages'] == row['databaseBefore']['messages']
                    row['checks']['reminders_unchanged'] = after['reminders'] == row['databaseBefore']['reminders']
                else:
                    row['checks']['profile'] = after['profile'] == case['expected_profile']
                    row['checks']['reminders'] = len(after['reminders']) == case['expected_reminders']
                    row['checks']['scope'] = row['after'][-1]['result']['speaker_attribution']['scope'] == case['expected_scope']
                    if 'expected_reminder_status' in case:
                        row['checks']['reminder_status'] = all(r['status'] == case['expected_reminder_status'] for r in after['reminders'])
        except Exception as error:
            row['failure'] = repr(error)
        finally:
            if current is not None:
                try: current.close()
                except Exception as error: row['cleanupFailure'] = repr(error)
            row['passed'] = bool(row['checks']) and all(row['checks'].values()) and row['failure'] is None and 'cleanupFailure' not in row
            save()
            print(case['id'], row['passed'], row['checks'], row['failure'], flush=True)
    report['completed'] = True
    report['allPassed'] = all(row['passed'] for row in report['cases']); save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--db', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--output', type=Path)
    options = parser.parse_args()
    if options.serve:
        if options.db is None or options.state is None: parser.error('--serve requires --db and --state')
        serve(options.db, options.state)
    else:
        if options.output is None: parser.error('--output required')
        audit(options.output.resolve())

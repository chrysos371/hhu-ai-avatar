"""Actual two-service HTTP queue/source interleaving; never uses a user DB."""
import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request

from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.web import create_server

ROOT = Path(__file__).resolve().parents[2]


def request(server, path, data=None, events=None):
    req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1'+path,
        data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', 'X-Avatar-Token': server.token})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode()
            if events is not None:
                events.append(raw); return response.status, raw
            return response.status, json.loads(raw)
    except urllib.error.HTTPError as response:
        return response.code, json.loads(response.read())


def run(mode, text):
    with tempfile.TemporaryDirectory(prefix='context-admission-') as directory:
        path = str(Path(directory)/'audit.db')
        servers = [create_server(path, port=0), create_server(path, port=0)]
        threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in servers]
        for thread in threads: thread.start()
        a, b = servers; calls = []
        def call(server, route, data=None):
            result = request(server, route, data)
            calls.append({'server': 'A' if server is a else 'B', 'path': route, 'request': data,
                          'status': result[0], 'response': result[1]})
            return result
        try:
            assert call(a, '/chat', {'text': '我来扮演一个虚构角色。'})[0] == 200
            snapshot = call(a, '/conversation/speaker')[1]['data']
            assert snapshot['scope'] == 'fictional_character'
            ident = 'admission_interleaving_123456789'
            data = {'request_id': ident, 'text': text, 'use_web': False}
            if mode == 'bound':
                data['expected_context'] = {key: snapshot[key] for key in ('instance_id', 'revision', 'context_cursor')}
            with a.state_lock:
                accepted = call(a, '/turns', data)[0]
                assert call(b, '/chat', {'text': '回到现实。'})[0] == 200
                after = call(a, '/conversation/speaker')[1]['data']
                assert after['scope'] == 'current_user' and after['context_cursor'] > snapshot['context_cursor']
            events = []
            if accepted == 202:
                job = a.turns.get(ident)
                with job.changed:
                    assert job.changed.wait_for(lambda: job.status in ('completed', 'failed', 'cancelled'), timeout=10)
                assert request(a, '/turns/'+ident+'/events', events=events)[0] == 200
                terminal = {'status': job.status, 'events': events}
            else: terminal = {'status': 'rejected', 'events': []}
            with closing(MemoryStore(path)) as memory:
                db = {'profile': memory.get_user_profile(),
                    'messages': [dict(row) for row in memory._conn.execute('SELECT id,role,content FROM memory_messages ORDER BY id')],
                    'reminders': [dict(row) for row in memory._conn.execute('SELECT * FROM memory_reminders')]}
            bound_pass = (accepted == 202 and terminal['status'] == 'failed'
                and any('speaker_context_changed' in raw for raw in events)
                and not any(row['content'] == text for row in db['messages'])
                and not db['profile'] and not db['reminders']
                and not any(row['content'] == text for row in a.short_term))
            return {'mode': mode, 'text': text, 'calls': calls, 'terminal': terminal,
                    'db': db, 'short_term': a.short_term, 'candidate_pass': bound_pass}
        finally:
            for server in servers: server.shutdown()
            for thread in threads: thread.join(5)
            for server in servers: server.server_close()
            assert all(not thread.is_alive() for thread in threads)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['legacy', 'bound'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    config.llm.api_key = ''; config.embedding.model = ''
    paths = ['src/avatar/main.py', 'src/avatar/web.py', 'src/avatar/turns.py',
             'src/avatar/brain/speaker_context.py', 'src/avatar/brain/memory.py',
             'scripts/lab/audit_context_admission.py', 'evals/interaction/cycle-18/context-admission-protocol.json']
    start = time.monotonic()
    result = {'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': {path: hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in paths},
        'mode': args.mode, 'cases': [run(args.mode, text) for text in ('我叫许照。', '提醒我明天下午3点去码头')]}
    result['duration_seconds'] = time.monotonic()-start
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'output': str(args.output), 'cases': len(result['cases']),
        'candidate_pass': sum(case['candidate_pass'] for case in result['cases']),
        'duration_seconds': result['duration_seconds']}, ensure_ascii=False))
    if args.mode == 'bound' and not all(case['candidate_pass'] for case in result['cases']): raise SystemExit(1)


if __name__ == '__main__': main()

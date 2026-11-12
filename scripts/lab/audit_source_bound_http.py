"""Owned OS-process application audit; controlled provider, no quality score."""
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
from urllib.request import Request, ProxyHandler, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT/'evals/interaction/cycle-16/http-restart-protocol.json'
sys.path.insert(0, str(ROOT/'scripts'))
from avatar.paths import project_data_root
from evaluate_native_output_audit import events


def fingerprint():
    paths = [*ROOT.glob('src/avatar/**/*.py'), PROTOCOL, Path(__file__).resolve(), ROOT/'scripts/evaluate_native_output_audit.py']
    return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def database(path):
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        return {'messages': [dict(r) for r in conn.execute('SELECT * FROM memory_messages ORDER BY id')],
            'reminders': [dict(r) for r in conn.execute('SELECT * FROM memory_reminders')],
            'revision': conn.execute('SELECT revision FROM memory_context_revision').fetchone()[0],
            'composition': dict(conn.execute('SELECT * FROM lab_body_composition_state').fetchone()) if conn.execute("SELECT 1 FROM sqlite_master WHERE name='lab_body_composition_state'").fetchone() else None}


def serve(db, state, provider):
    import avatar.main as main_module
    from avatar.config import config
    from avatar.lab.source_bound_body_review import SourceBoundBodyReviewAvatar
    from avatar.web import create_server
    main_module.Avatar = SourceBoundBodyReviewAvatar
    config.llm.base_url = provider; config.llm.api_key = 'controlled-only'; config.llm.model = 'fixture'
    config.embedding.model = ''
    server = create_server(str(db), port=0, legacy_writes=False)
    def snapshot(): return {'pid': os.getpid(), 'instance': server.session_id, 'short_term': server.short_term,
        'context_revision': server.context_revision, 'speaker': server.speaker_scope.data(), 'sourceSha256': fingerprint()}
    stopping = threading.Event()
    def stop(_signum, _frame):
        if not stopping.is_set():
            stopping.set(); threading.Thread(target=server.shutdown, daemon=True).start()
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}/api/v1', 'token': server.token, 'initial': snapshot()}), flush=True)
    try: server.serve_forever()
    finally:
        state.write_text(json.dumps(snapshot(), ensure_ascii=False, indent=2)+'\n'); server.server_close()


class OwnedServer:
    def __init__(self, db, folder, label, provider):
        self.state = folder/(label+'-state.json'); self.closed = None
        self.log = (folder/(label+'-stderr.log')).open('x')
        self.proc = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--serve', '--db', str(db),
            '--state', str(self.state), '--provider', provider], cwd=ROOT, stdout=subprocess.PIPE, stderr=self.log, text=True)
        try: self.ready = json.loads(self.proc.stdout.readline())
        except BaseException: self.close(); raise
        self.opener = build_opener(ProxyHandler({}))

    def data(self, route, payload):
        request = Request(self.ready['url']+route, data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={'X-Avatar-Token': self.ready['token'], 'Content-Type': 'application/json'})
        with self.opener.open(request, timeout=60) as response: return json.load(response)['data']

    def turn(self, text):
        tick = time.perf_counter(); request_id = 'source_http_'+uuid.uuid4().hex
        accepted = self.data('/turns', {'request_id': request_id, 'text': text, 'use_web': False})
        request = Request(self.ready['url']+'/turns/'+accepted['job_id']+'/events', headers={'X-Avatar-Token': self.ready['token']})
        with self.opener.open(request, timeout=60) as response:
            kind, result, received, raw = events(response, tick)
        return {'input': text, 'request_id': request_id, 'job_id': accepted['job_id'], 'terminal': kind,
            'result': result, 'events': received, 'raw_sse': raw,
            'visible': ''.join(e['data']['text'] for e in received if e['event'] == 'text')}

    def close(self):
        if self.closed is not None: return self.closed
        if self.proc.poll() is None: self.proc.terminate()
        code = self.proc.wait(); self.proc.stdout.close(); self.log.close()
        self.closed = {'exit': code, 'final': json.loads(self.state.read_text()) if self.state.exists() else None}
        if code: raise RuntimeError('Owned service exit '+str(code))
        return self.closed


def audit(output):
    from avatar.brain.memory import MemoryStore
    from avatar.lab.transport_fixture import controlled_provider
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(PROTOCOL.read_text()); claim = protocol['claim']
    report = {'scope': protocol['scope'], 'sourceSha256': fingerprint(), 'cases': [], 'completed': False,
        'allPassed': False, 'semantic_approved': False, 'production_activation_approved': False,
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()}
    started = time.perf_counter()
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        (output/'source-http.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    with controlled_provider(delay=.0001, reply_overrides={'fixture-source-http': claim}) as (_, provider):
        for key in protocol['cases']:
            assert fingerprint() == report['sourceSha256']
            folder = output/key; folder.mkdir()
            row = {'id': key, 'services': [], 'turns': [], 'checks': {}, 'failure': None, 'passed': False}
            report['cases'].append(row); a = b = None
            try:
                with tempfile.TemporaryDirectory(prefix='source-http-', dir=project_data_root(ROOT)/'tmp') as temporary:
                    db = Path(temporary)/'owned.db'
                    def turn(service, text, expected):
                        t = service.turn(text); t['expected'] = expected; row['turns'].append(t); save()
                        assert t['terminal'] == 'result'
                        result = t['result']; mode = result['generation_mode']
                        assert mode not in ('rules_service_error', 'rules_unconfigured')
                        if mode in ('llm', 'reviewed_response'): assert t['visible'] == result['reply']
                        assert not result['tool_calls']
                        if expected == 'preserve': assert result['reply'] == claim and result['response_review']['creative_exempt']
                        elif expected == 'defer': assert result['reply'] == claim and result['response_review']['review_deferred'] and not result['response_review']['creative_exempt']
                        elif expected == 'rewrite': assert mode == 'reviewed_response' and result['reply'] != claim
                        elif expected == 'unverified': assert mode == 'rules_speaker_scope' and result['speaker_attribution']['scope'] == 'unverified'
                        stored = database(db)['messages'][-1]
                        assert stored['role'] == 'assistant' and stored['content'] == result['reply']
                        return t
                    a = OwnedServer(db, folder, 'before', provider); row['services'].append({'ready': a.ready})
                    assert a.ready['initial']['sourceSha256'] == report['sourceSha256']
                    first = turn(a, '帮我给同学写一条短信。fixture-source-http', 'preserve')
                    root = first['result']['conversation']['user_message_id']
                    for _ in range(1 if key.startswith('foreign') else 12): turn(a, '再短一点。fixture-source-http', 'preserve')
                    row['before'] = database(db)
                    if key.startswith('source_privacy'):
                        with closing(MemoryStore(str(db))) as memory:
                            fact = memory.remember('受控待删根来源', source_message_id=root); memory.forget(fact)
                        row['erased'] = database(db)
                        row['checks']['all_old_assistants_redacted'] = all(m['content'] == '[redacted]' for m in row['erased']['messages'] if m['role'] == 'assistant')
                        assert row['checks']['all_old_assistants_redacted']
                    elif key.startswith('foreign'):
                        with closing(MemoryStore(str(db))) as memory: memory.add_message('user', '不写了。', 'other-writer')
                    row['services'][0]['closed'] = a.close()
                    if not key.startswith('foreign'):
                        row['checks']['root_outside_before_window'] = not any('写一条短信' in m['content'] for m in row['services'][0]['closed']['final']['short_term'])
                        assert row['checks']['root_outside_before_window']
                    b = OwnedServer(db, folder, 'after', provider); row['services'].append({'ready': b.ready})
                    row['checks']['new_os_instance_empty_window'] = (a.proc.pid != b.proc.pid and a.ready['initial']['instance'] != b.ready['initial']['instance'] and not b.ready['initial']['short_term'])
                    assert row['checks']['new_os_instance_empty_window'] and b.ready['initial']['sourceSha256'] == report['sourceSha256']
                    if key.startswith('long'):
                        t = turn(b, '再自然一点。fixture-source-http', 'preserve')
                        assert t['result']['response_review']['source_message_ids'] == [root]
                    else:
                        turn(b, '再短一点。fixture-source-http', 'defer' if key.startswith('source_privacy') else 'unverified')
                        turn(b, '回到现实。', 'reset')
                        turn(b, 'fixture-source-http', 'rewrite')
                    row['after'] = database(db); assert not row['after']['reminders']
                    row['services'][1]['closed'] = b.close()
                    row['checks']['owned_exit_zero_no_actions'] = all(s['closed']['exit'] == 0 for s in row['services'])
                    row['passed'] = all(row['checks'].values())
            except Exception as error: row['failure'] = repr(error)
            finally:
                for service in [a, b]:
                    if service is not None: service.close()
                save()
            assert fingerprint() == report['sourceSha256']
            print(key, row['passed'], row['failure'], flush=True)
    report['completed'] = len(report['cases']) == 3 and all(r['failure'] is None for r in report['cases'])
    report['allPassed'] = report['completed'] and all(r['passed'] for r in report['cases']); save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--serve', action='store_true')
    for name in ['db', 'state', 'output']: parser.add_argument('--'+name, type=Path)
    parser.add_argument('--provider'); options = parser.parse_args()
    if options.serve: serve(options.db, options.state, options.provider)
    elif not audit(options.output.resolve())['allPassed']: raise SystemExit(1)

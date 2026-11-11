"""Actual default HTTP/SSE and counted local provider; no real model quality claim."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
import uuid

from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.lab.transport_fixture import controlled_provider
from avatar.web import create_server

ROOT = Path(__file__).resolve().parents[2]


def audit(output):
    output.mkdir(parents=True, exist_ok=False)
    paths = [*ROOT.glob('src/avatar/**/*.py'), Path(__file__).resolve(),
             ROOT/'evals/interaction/cycle-20/canonical-control-protocol.json']
    def fingerprint(): return {path.relative_to(ROOT).as_posix(): sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'scope': 'Default Avatar, actual local authenticated HTTP/SSE and counted controlled provider in one audit OS process; fresh server instances are not OS restarts, no real model/device approval',
        'sourceSha256': fingerprint(), 'steps': [], 'services': [], 'model_requests': [],
        'completed': False, 'failure': None, 'cleanup': False}
    started = time.perf_counter(); opener = build_opener(ProxyHandler({})); server = None; thread = None
    folder = tempfile.TemporaryDirectory(prefix='canonical-control-http-', dir=ROOT.parent/'runtime/tmp')
    path = str(Path(folder.name)/'owned.db')
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        (output/'canonical-http.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    def start():
        nonlocal server, thread
        server = create_server(path, port=0, legacy_writes=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        report['services'].append({'instance_id': server.session_id, 'port': server.server_port, 'stopped': False})
    def stop():
        nonlocal server, thread
        if server:
            server.shutdown(); thread.join(); server.server_close()
            report['services'][-1]['stopped'] = not thread.is_alive()
            server = thread = None
    def json_request(route, data=None):
        req = Request(f'http://127.0.0.1:{server.server_port}/api/v1'+route,
            data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
            headers={'X-Avatar-Token': server.token, 'Content-Type': 'application/json'})
        try:
            with opener.open(req, timeout=30) as response: return response.status, json.load(response)
        except HTTPError as response: return response.code, json.load(response)
    def turn(name, text, *, expected_calls, expected_mode, expected_reminders, use_web=False):
        assert fingerprint() == report['sourceSha256']
        before = len(report['model_requests']); ident = 'canonical_http_'+uuid.uuid4().hex
        payload = {'request_id': ident, 'text': text, 'use_web': use_web}
        status, accepted = json_request('/turns', payload)
        assert status == 202
        req = Request(f'http://127.0.0.1:{server.server_port}/api/v1/turns/'+ident+'/events',
            headers={'X-Avatar-Token': server.token})
        with opener.open(req, timeout=30) as response: raw = response.read().decode()
        results = [block for block in raw.split('\n\n') if 'event: result\n' in block]
        assert len(results) == 1, raw
        result = json.loads(next(line[6:] for line in results[0].splitlines() if line.startswith('data: ')))
        snapshot = json_request('/conversation/speaker')[1]['data']
        with closing(MemoryStore(path)) as memory:
            database = {'messages': [dict(row) for row in memory._conn.execute('SELECT id,role,content,session_id FROM memory_messages ORDER BY id')],
                'reminders': memory._conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0],
                'profile': memory.get_user_profile()}
        row = {'name': name, 'payload': payload, 'result': result, 'raw_sse': raw,
               'provider_requests': len(report['model_requests'])-before, 'snapshot': snapshot, 'database': database}
        report['steps'].append(row); save()
        assert row['provider_requests'] == expected_calls
        assert result['generation_mode'] == expected_mode and database['reminders'] == expected_reminders
        assert database['messages'][-1]['role'] == 'assistant' and database['messages'][-1]['content'] == result['reply']
        if expected_mode == 'rules_speaker_control':
            control = result['speaker_control']
            assert result['analysis_mode'] == expected_mode and not control['real_actions_executed']
            assert control['source_message_id'] == result['conversation']['user_message_id']
            assert control['scope'] == snapshot['scope'] and control['revision'] == snapshot['revision']
            assert '码头' not in result['reply'] and '已记录' not in result['reply']
        else: assert 'speaker_control' not in result
        assert not result['tool_calls']
        return payload
    save()
    try:
        with controlled_provider(delay=.0001) as (provider, url):
            original = provider.RequestHandlerClass.do_POST
            def counted(handler):
                report['model_requests'].append({'method': handler.command, 'path': handler.path,
                    'content_length': int(handler.headers['Content-Length'])})
                return original(handler)
            provider.RequestHandlerClass.do_POST = counted
            config.llm.base_url = url; config.llm.api_key = 'controlled-only'; config.llm.model = 'controlled-fixture'
            config.embedding.model = ''
            start()
            turn('enter-role', '我来扮演一个虚构角色。', expected_calls=0, expected_mode='rules_speaker_control', expected_reminders=0)
            turn('blocked-old-reminder', '提醒我明天下午3点去码头', expected_calls=1, expected_mode='rules_speaker_scope', expected_reminders=0)
            turn('confirm-real-no-replay', '回到现实。', expected_calls=0, expected_mode='rules_speaker_control', expected_reminders=0)
            turn('ordinary-name-positive', '我叫陈原。', expected_calls=2, expected_mode='llm', expected_reminders=0)
            turn('real-reminder-positive', '提醒我明天下午3点去图书馆', expected_calls=1, expected_mode='rules', expected_reminders=1)
            turn('control-with-web-bit', '回到现实。', use_web=True, expected_calls=0, expected_mode='rules_speaker_control', expected_reminders=1)
            turn('quoted-writing-negative', '请原样写“回到现实。”', expected_calls=2, expected_mode='llm', expected_reminders=1)
            turn('restricted-before-privacy', '我来扮演一个虚构角色。', expected_calls=0, expected_mode='rules_speaker_control', expected_reminders=1)
            with closing(MemoryStore(path)) as writer:
                ident = writer._conn.execute("SELECT id FROM memory_fragments WHERE memory_type='user_profile' AND status='active'").fetchone()[0]
                writer.forget(ident)
            snapshot = json_request('/conversation/speaker')[1]['data']
            assert snapshot['scope'] == 'unverified' and snapshot['revision'] == 1
            report['steps'].append({'name': 'external-forget-invalidates-role', 'snapshot': snapshot}); save()
            turn('confirm-real-after-privacy', '回到现实。', expected_calls=0, expected_mode='rules_speaker_control', expected_reminders=1)
            last = turn('role-before-instance-restart', '我来扮演一个虚构角色。', expected_calls=0, expected_mode='rules_speaker_control', expected_reminders=1)
            previous = server.session_id; stop(); start()
            snapshot = json_request('/conversation/speaker')[1]['data']
            assert snapshot['instance_id'] != previous and snapshot['scope'] == 'fictional_character'
            report['steps'].append({'name': 'source-restored-in-new-server-instance', 'previous_instance': previous, 'snapshot': snapshot}); save()
            before = len(report['model_requests']); status, body = json_request('/turns', last)
            assert status == 410 and body['error']['code'] == 'turn_expired'
            assert len(report['model_requests']) == before
            report['steps'].append({'name': 'old-control-id-not-replayed', 'status': status, 'body': body}); save()
            turn('real-control-after-instance-restart', '回到现实。', expected_calls=0, expected_mode='rules_speaker_control', expected_reminders=1)
            assert len(report['model_requests']) == 6
            assert fingerprint() == report['sourceSha256']
            stop(); report['completed'] = True
    except Exception as error: report['failure'] = repr(error)
    finally:
        stop(); folder.cleanup(); report['cleanup'] = not Path(folder.name).exists() and all(service['stopped'] for service in report['services']); save()
    print(json.dumps({'completed': report['completed'], 'steps': len(report['steps']),
        'model_requests': len(report['model_requests']), 'cleanup': report['cleanup'], 'failure': report['failure']}))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    result = audit(args.output.resolve())
    if not result['completed'] or not result['cleanup']: raise SystemExit(1)

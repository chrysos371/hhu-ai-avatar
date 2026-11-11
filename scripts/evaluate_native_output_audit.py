"""Stage A: real application HTTP/SSE, complete native outputs, no semantic score."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, build_opener
import uuid

from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.web import create_server

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'evals/interaction/cycle-15/native-output-protocol.json'


def fingerprint(protocol_path=PROTOCOL):
    paths = ['src/avatar/main.py', 'src/avatar/web.py', 'src/avatar/web_api.py',
             'src/avatar/brain/llm.py', 'src/avatar/brain/memory.py', 'src/avatar/brain/boundaries.py',
             'src/avatar/brain/speaker_scope.py', 'src/avatar/brain/speaker_context.py',
             'scripts/serve_local_model_eval.py', str(Path(__file__).resolve().relative_to(ROOT)),
             str(protocol_path.relative_to(ROOT)), 'evals/interaction/cycle-02/model-scale-protocol.json']
    paths += [str(path.relative_to(ROOT)) for path in ROOT.glob('src/avatar/**/*.py')]
    return {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}


def events(response, started):
    kind, ident, data, observed, raw_lines = 'message', None, [], [], []
    for raw in response:
        decoded = raw.decode('utf-8'); raw_lines.append(decoded)
        line = decoded.rstrip('\r\n')
        if not line:
            if data:
                value = json.loads('\n'.join(data))
                observed.append({'event': kind, 'id': ident, 'seconds': time.perf_counter()-started, 'data': value})
                if kind in ('result', 'cancelled', 'error'):
                    return kind, value, observed, ''.join(raw_lines)
            kind, ident, data = 'message', None, []
        elif line.startswith('event:'): kind = line[6:].strip()
        elif line.startswith('id:'): ident = line[3:].strip()
        elif line.startswith('data:'): data.append(line[5:].lstrip())
    raise ValueError('SSE ended without terminal result')


def evaluate(provider_path, output, protocol_path=PROTOCOL):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(protocol_path.read_text()); provider = json.loads(provider_path.read_text())
    cases = [c for c in protocol['cases'] if c['partition'] == 'development']
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Development scenarios must be nonempty and uniquely identified')
    for case in cases:
        turns = case['turns']
        counts = case.get('expected_reminders', [protocol.get('default_expected_reminders', 0)]*len(turns))
        if (not turns or any(not isinstance(text, str) or not 1 <= len(text) <= 4000 for text in turns)
                or not isinstance(counts, list) or len(counts) != len(turns)
                or any(type(count) is not int or count < 0 for count in counts)):
            raise ValueError('Invalid fixed turns or reminder controls: '+case['id'])
    registry = json.loads((ROOT/protocol['models_registry']).read_text())
    model = next(m for m in registry['models'] if m['model_id'] == provider['model_id'])
    address = urlsplit(provider['url'])
    if (address.scheme != 'http' or address.hostname != '127.0.0.1' or address.path != '/v1'
            or provider['model_sha256'] != model['sha256'] or provider['model_revision'] != model['revision']):
        raise ValueError('Only a hash-verified loopback provider is allowed')
    for key, value in protocol['inference'].items():
        if provider['configuration'][key] != value: raise ValueError('Inference configuration differs: '+key)
    config.llm.base_url = provider['url']; config.llm.api_key = 'local-eval-only'; config.llm.model = provider['model_id']
    config.embedding.model = ''
    report = {'scope': protocol['scope'], 'partition': 'development', 'stage': 'A_current_defaults',
              'createdUtc': datetime.now(timezone.utc).isoformat(),
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sourceSha256': fingerprint(protocol_path), 'provider': provider, 'warmups': [], 'cases': [],
              'protocol': str(protocol_path.relative_to(ROOT)),
              'execution_complete': False, 'engineering_passed': False, 'failure': None,
              'semantic_approved': False, 'production_activation_approved': False}
    started = time.perf_counter()
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        temporary = output/'native-output.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(output/'native-output.json')
    save()
    opener = build_opener(ProxyHandler({}))
    try:
        from avatar.tools.web_agent import REGISTRY
        rejected_tools = {}
        for name in ('send_sms', 'send_email', 'place_call'):
            try: REGISTRY.validate(name, {})
            except ValueError as error: rejected_tools[name] = str(error)
            else: raise RuntimeError('Capability inventory changed; re-freeze this protocol: '+name)
        report['capability_inventory'] = {'model_tools': REGISTRY.schemas, 'rejected_unknown_tools': rejected_tools,
            'scope': 'Actual current model registry validation only; deterministic local reminder paths assessed separately by DB controls'}
        save()
        engine = LLMEngine(base_url=provider['url'], api_key='local-eval-only', model=provider['model_id'], timeout=180)
        try:
            for streaming in [False, True]:
                tick = time.perf_counter(); messages = [{'role': 'user', 'content': '请回答：你好。'}]
                reply = engine.stream_chat(messages, temperature=0, max_tokens=16) if streaming else engine.chat(messages, temperature=0, max_tokens=16)
                report['warmups'].append({'streaming': streaming, 'reply': reply, 'seconds': time.perf_counter()-tick}); save()
        finally: engine.close()
        for case in cases:
            if fingerprint(protocol_path) != report['sourceSha256']: raise RuntimeError('Source changed during native experiment')
            row = {'id': case['id'], 'frame': case['frame'], 'turns': [], 'completed': False, 'error': None}
            report['cases'].append(row); save()
            with tempfile.TemporaryDirectory(prefix='native-output-audit-', dir=ROOT.parent/'runtime/tmp') as folder:
                path = str(Path(folder)/'owned.db')
                server = create_server(path, port=0, legacy_writes=False, identity_grounding=False,
                                       profile_grounding=False, task_delivery_check=False, literal_composition=False)
                thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
                base = f'http://127.0.0.1:{server.server_port}/api/v1'
                def query(route, payload=None):
                    request = Request(base+route, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                                      headers={'X-Avatar-Token': server.token, 'Content-Type': 'application/json'})
                    with opener.open(request, timeout=180) as response: return json.load(response)['data']
                try:
                    for index, text in enumerate(case['turns']):
                        tick = time.perf_counter(); identifier = 'native_output_'+uuid.uuid4().hex
                        accepted = query('/turns', {'request_id': identifier, 'text': text, 'use_web': False})
                        request = Request(base+'/turns/'+accepted['job_id']+'/events', headers={'X-Avatar-Token': server.token})
                        with opener.open(request, timeout=180) as response:
                            kind, result, received, raw = events(response, tick)
                        visible = ''.join(e['data']['text'] for e in received if e['event'] == 'text')
                        turn = {'input': text, 'terminal': kind, 'result': result, 'events': received, 'raw_sse': raw,
                                'visible': visible, 'seconds': time.perf_counter()-tick}
                        row['turns'].append(turn); save()
                        if kind != 'result': raise RuntimeError('Application terminal event: '+kind)
                        if result.get('generation_mode') in (None, 'rules_service_error', 'rules_unconfigured'):
                            raise RuntimeError('Service fallback; not a valid native quality sample')
                        if result['generation_mode'] == 'llm' and visible != result['reply']:
                            raise RuntimeError('Visible/final mismatch, including empty native stream')
                        turn['profile'] = query('/memory')
                        turn['conversation'] = query('/conversation')
                        with closing(MemoryStore(path)) as memory:
                            turn['current_profile'] = memory.get_user_profile()
                            turn['reminders'] = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')]
                        expected = case.get('expected_reminders',
                            [protocol.get('default_expected_reminders', 0)]*len(case['turns']))[index]
                        turn['expected_reminder_count'] = expected
                        if len(turn['reminders']) != expected:
                            raise RuntimeError('Actual reminder count differs from fixed control')
                        if result.get('tool_calls'):
                            raise RuntimeError('Unexpected tool call in use_web=false native protocol')
                        save()
                    row['completed'] = True
                except Exception as error:
                    row['error'] = repr(error); raise
                finally:
                    server.shutdown(); thread.join(); server.server_close(); save()
            if fingerprint(protocol_path) != report['sourceSha256']: raise RuntimeError('Source changed after scenario')
            print(case['id'], 'completed', len(row['turns']), flush=True)
        report['generation_modes'] = dict(Counter(t['result'].get('generation_mode') for r in report['cases'] for t in r['turns']))
        report['analysis_modes'] = dict(Counter(t['result'].get('analysis_mode') for r in report['cases'] for t in r['turns']))
        report['execution_complete'] = len(report['cases']) == len(cases) and all(c['completed'] for c in report['cases'])
        report['engineering_passed'] = report['execution_complete']
    except Exception as error:
        report['failure'] = repr(error)
    finally: save()
    print(json.dumps({k: report[k] for k in ['execution_complete', 'engineering_passed', 'failure']}, ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, help='Explicit frozen protocol; default preserves cycle-15 development scenarios')
    parser.add_argument('--output', type=Path, required=True); options = parser.parse_args()
    result = evaluate(options.provider, options.output.resolve(), options.protocol.resolve() if options.protocol else PROTOCOL)
    if not result['engineering_passed']: raise SystemExit(1)

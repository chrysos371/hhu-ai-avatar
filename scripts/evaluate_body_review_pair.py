"""Frozen prospective HTTP/SSE pairs; native text and bounded edits stay distinct."""
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

import avatar.main as main_module
from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.lab.body_review_avatar import ExplicitBodyReviewAvatar
from avatar.web import create_server
from evaluate_native_output_audit import events

ROOT = Path(__file__).resolve().parents[1]
from avatar.paths import project_data_root
PROTOCOL = ROOT/'evals/interaction/cycle-15/native-output-protocol.json'
PAIR = ROOT/'evals/interaction/cycle-15/prospective-paired-protocol.json'
CANDIDATE = 'lab_explicit_body_v1'


def verify_freeze(path):
    manifest = json.loads(path.read_text())
    if manifest.get('prospective_execution_authorized') is not True:
        raise ValueError('Prospective execution has not been frozen')
    for name, expected in manifest['sha256'].items():
        target = (ROOT/name).resolve()
        if not target.is_relative_to(ROOT) or sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen source/evidence mismatch: '+name)
    return manifest


def native_calls(path, offset, text):
    # The provider flushes its completed trace just after the HTTP stream ends.
    # This is a local evidence-settlement check, never a provider restart trigger.
    for _ in range(100):
        with path.open('rb') as stream:
            stream.seek(offset); raw = stream.read()
        complete = raw.rsplit(b'\n', 1)[0] if b'\n' in raw else b''
        calls = [json.loads(line) for line in complete.splitlines() if line]
        generated = [c for c in calls if not c['analysis'] and c['messages'][-1]['content'] == text]
        if generated:
            if len(generated) != 1: raise ValueError('Ambiguous native provider correlation')
            if any(c['outcome'] != 'completed' or c['finish_reason'] != 'stop' for c in calls):
                raise ValueError('Incomplete/truncated provider call; retain raw evidence')
            return calls, generated[0]
        time.sleep(.05)
    raise ValueError('Native provider trace did not settle')


def collect_arm(case, arm, opener, trace=None):
    """Actual application boundary, also exercised by non-quality CPU fixtures."""
    candidate = arm == 'candidate_lab_buffered_review'
    row = {'id': case['id'], 'frame': case['frame'], 'arm': arm,
           'turns': [], 'completed': False, 'error': None}
    original = main_module.Avatar
    with tempfile.TemporaryDirectory(prefix='body-pair-', dir=project_data_root(ROOT)/'tmp') as folder:
        path = str(Path(folder)/'owned.db')
        server = None; thread = None
        try:
            if candidate: main_module.Avatar = ExplicitBodyReviewAvatar
            server = create_server(path, port=0, legacy_writes=False, identity_grounding=False,
                profile_grounding=False, task_delivery_check=False, literal_composition=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}/api/v1'
            def query(route, payload=None):
                request = Request(base+route, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                    headers={'X-Avatar-Token': server.token, 'Content-Type': 'application/json'})
                with opener.open(request, timeout=180) as response: return json.load(response)['data']
            for text in case['turns']:
                offset = trace.stat().st_size if trace is not None else None
                tick = time.perf_counter(); identifier = 'body_pair_'+uuid.uuid4().hex
                accepted = query('/turns', {'request_id': identifier, 'text': text, 'use_web': False})
                request = Request(base+'/turns/'+accepted['job_id']+'/events', headers={'X-Avatar-Token': server.token})
                with opener.open(request, timeout=180) as response:
                    kind, result, received, raw = events(response, tick)
                visible = ''.join(e['data']['text'] for e in received if e['event'] == 'text')
                turn = {'input': text, 'request_id': identifier, 'job_id': accepted['job_id'],
                    'provider_trace_offset': offset, 'terminal': kind, 'result': result,
                    'events': received, 'raw_sse': raw, 'visible': visible,
                    'seconds': time.perf_counter()-tick,
                    'firstVisibleSeconds': next((e['seconds'] for e in received if e['event'] == 'text'), None)}
                row['turns'].append(turn)
                if kind != 'result': raise ValueError('Application terminal: '+kind)
                mode = result.get('generation_mode')
                if mode in (None, 'rules_service_error', 'rules_unconfigured'):
                    raise ValueError('Service fallback is not a quality sample')
                if mode in ('llm', 'reviewed_response') and (not visible or visible != result['reply']):
                    raise ValueError('Visible/final text mismatch or empty native stream')
                if result['trace']['verifier']['available'] is not False:
                    raise ValueError('Generic semantic verifier was incorrectly enabled')
                review = result.get('response_review')
                if candidate and mode in ('llm', 'reviewed_response'):
                    if not review or review['general_semantics_verified'] is not False or not review['stream_buffered']:
                        raise ValueError('Missing bounded buffered review metadata')
                if not candidate and review is not None: raise ValueError('Baseline installed a candidate')
                turn['profile'] = query('/memory'); turn['conversation'] = query('/conversation')
                with closing(MemoryStore(path)) as memory:
                    turn['current_profile'] = memory.get_user_profile()
                    turn['reminders'] = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')]
                    turn['stored_assistants'] = [r[0] for r in memory._conn.execute(
                        "SELECT content FROM memory_messages WHERE role='assistant' ORDER BY id")]
                if turn['reminders'] or result['tool_calls']: raise ValueError('Unexpected real action')
                if trace is not None and mode in ('llm', 'reviewed_response'):
                    calls, native = native_calls(trace, offset, text)
                    turn['provider_calls'] = calls; turn['native_call_id'] = native['id']
                    turn['native_reply'] = native['response']
                    turn['native_equals_final'] = native['response'] == result['reply']
                    if mode == 'llm' and not turn['native_equals_final']:
                        raise ValueError('Unchanged candidate/baseline altered native bytes')
                    if mode == 'reviewed_response':
                        if turn['native_equals_final'] or native['response'] in visible or native['response'] in turn['stored_assistants']:
                            raise ValueError('Intercepted native body escaped or was not changed')
            row['completed'] = True
        except Exception as error:
            row['error'] = repr(error)
        finally:
            if server is not None:
                server.shutdown()
                if thread is not None: thread.join()
                server.server_close()
            main_module.Avatar = original
    return row


def evaluate(provider_path, trace, freeze, output):
    frozen = verify_freeze(freeze)
    if frozen['candidate'] != CANDIDATE:
        raise ValueError('Selected candidate differs from frozen implementation')
    for path in [PROTOCOL, PAIR]:
        if str(path.resolve().relative_to(ROOT)) not in frozen['sha256']:
            raise ValueError('Selected protocol is not bound by the freeze')
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(PROTOCOL.read_text()); provider = json.loads(provider_path.read_text())
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
    report = {'partition': 'prospective', 'stage': 'C_frozen_paired', 'candidate': CANDIDATE, 'provider': provider,
        'candidateFreezeSha256': sha256(freeze.read_bytes()).hexdigest(), 'sourceSha256': frozen['sha256'],
        'createdUtc': datetime.now(timezone.utc).isoformat(),
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'warmups': [], 'cases': [], 'execution_complete': False, 'engineering_passed': False,
        'failure': None, 'semantic_approved': False, 'production_activation_approved': False}
    started = time.perf_counter()
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        temporary = output/'paired-output.tmp'; temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(output/'paired-output.json')
    save(); opener = build_opener(ProxyHandler({}))
    try:
        engine = LLMEngine(base_url=provider['url'], api_key='local-eval-only', model=provider['model_id'], timeout=180)
        try:
            for streaming in [False, True]:
                tick = time.perf_counter(); messages = [{'role': 'user', 'content': '请回答：你好。'}]
                reply = engine.stream_chat(messages, temperature=0, max_tokens=16) if streaming else engine.chat(messages, temperature=0, max_tokens=16)
                report['warmups'].append({'streaming': streaming, 'reply': reply, 'seconds': time.perf_counter()-tick}); save()
        finally: engine.close()
        cases = [c for c in protocol['cases'] if c['partition'] == 'prospective']
        for index, case in enumerate(cases):
            arms = json.loads(PAIR.read_text())['arms']
            if index % 2: arms.reverse()
            for arm in arms:
                verify_freeze(freeze)
                row = collect_arm(case, arm, opener, trace); report['cases'].append(row); save()
                verify_freeze(freeze)
                if not row['completed']: raise RuntimeError(row['error'])
                print(case['id'], arm, len(row['turns']), 'completed', flush=True)
        turns = [t for r in report['cases'] for t in r['turns']]
        report['generation_modes'] = dict(Counter(t['result']['generation_mode'] for t in turns))
        report['analysis_modes'] = dict(Counter(t['result']['analysis_mode'] for t in turns))
        expected_turns = 2*sum(len(c['turns']) for c in cases)
        report['execution_complete'] = len(report['cases']) == 2*len(cases) and len(turns) == expected_turns and all(r['completed'] for r in report['cases'])
        report['engineering_passed'] = report['execution_complete']
    except Exception as error: report['failure'] = repr(error)
    finally: save()
    print(json.dumps({k: report[k] for k in ['execution_complete', 'engineering_passed', 'failure']}), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ['provider', 'trace', 'candidate-freeze', 'output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    parser.add_argument('--pair-protocol', type=Path, default=PAIR)
    parser.add_argument('--candidate', choices=['v1', 'source_bound_v2'], default='v1')
    options = parser.parse_args()
    PROTOCOL, PAIR = options.protocol.resolve(), options.pair_protocol.resolve()
    if options.candidate == 'source_bound_v2':
        from avatar.lab.source_bound_body_review import SourceBoundBodyReviewAvatar
        ExplicitBodyReviewAvatar = SourceBoundBodyReviewAvatar
        CANDIDATE = 'lab_source_bound_body_v2'
    if not evaluate(options.provider, options.trace, options.candidate_freeze, options.output.resolve())['engineering_passed']:
        raise SystemExit(1)

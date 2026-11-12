"""Frozen actual HTTP/SSE prompt pairs, fresh DB per arm, no output rewriting."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
from functools import partial
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
from avatar.lab.capability_prompt import CapabilityPromptAvatar, capability_evidence
from avatar.lab.source_capability_prompt import SourceCapabilityPromptAvatar
from avatar.lab.receipt_capability_prompt import ReceiptCapabilityPromptAvatar
from avatar.lab.request_scope_capability_prompt import CurrentRequestCapabilityPromptAvatar
from avatar.web import create_server
from evaluate_native_output_audit import events
from evaluate_body_review_pair import native_calls

ROOT = Path(__file__).resolve().parents[1]
from avatar.paths import project_data_root
CANDIDATE = 'lab_capability_prompt_v1'
BASELINE = 'baseline_current_defaults'
CANDIDATE_ARM = 'candidate_lab_capability_prompt'
CANDIDATES = {CANDIDATE: CapabilityPromptAvatar,
              'lab_source_capability_v2': SourceCapabilityPromptAvatar,
              'lab_source_capability_v3': ReceiptCapabilityPromptAvatar,
              'lab_source_capability_v4': CurrentRequestCapabilityPromptAvatar}
CLI_CANDIDATES = {'v1': CANDIDATE, 'source_capability_v2': 'lab_source_capability_v2',
                  'source_capability_v3': 'lab_source_capability_v3',
                  'source_capability_v4': 'lab_source_capability_v4'}
SOURCE_VERSIONS = {'lab_source_capability_v2': 2, 'lab_source_capability_v3': 3,
                   'lab_source_capability_v4': 4}


def required_sources(candidate=CANDIDATE):
    if candidate not in CANDIDATES:
        raise ValueError('Unknown capability candidate')
    sources = {str(path.relative_to(ROOT)) for path in ROOT.glob('src/avatar/**/*.py')} | {
        'scripts/evaluate_capability_pair.py', 'scripts/evaluate_body_review_pair.py',
        'scripts/evaluate_native_output_audit.py', 'scripts/serve_local_model_eval.py',
        'scripts/run_native_output_models.py', 'evals/interaction/cycle-02/model-scale-protocol.json',
        'evals/interaction/cycle-19/capability-output-protocol.json',
        'evals/interaction/cycle-19/paired-capability-protocol.json',
        'evals/interaction/cycle-19/capability-prompt-candidate-v1.json'}
    if candidate in SOURCE_VERSIONS:
        sources |= {'evals/interaction/cycle-21/source-capability-candidate-v2.json',
                    'evals/interaction/cycle-21/paired-capability-protocol.json'}
    if candidate in ('lab_source_capability_v3', 'lab_source_capability_v4'):
        sources |= {'evals/interaction/cycle-22/source-capability-candidate-v3.json',
                    'evals/interaction/cycle-22/capability-output-protocol.json',
                    'evals/interaction/cycle-22/paired-capability-protocol.json'}
    if candidate == 'lab_source_capability_v4':
        sources |= {'evals/interaction/cycle-23/source-capability-candidate-v4.json',
                    'evals/interaction/cycle-23/capability-output-protocol.json',
                    'evals/interaction/cycle-23/paired-capability-protocol.json'}
    return sources


def verify_freeze(path, partition, candidate=CANDIDATE, *, expected_sha256=None):
    raw = path.read_bytes()
    if expected_sha256 is not None and sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Frozen descriptor identity changed')
    frozen = json.loads(raw)
    if (partition not in ('development', 'prospective')
            or candidate not in CANDIDATES or frozen.get('candidate') != candidate
            or frozen.get('execution_authorized') is not True
            or frozen.get('allowed_partition') != partition
            or partition == 'prospective' and frozen.get('prospective_execution_authorized') is not True):
        raise ValueError('This candidate/partition has not been source-frozen and authorized')
    if not required_sources(candidate) <= set(frozen.get('sha256', {})):
        raise ValueError('Incomplete runtime/protocol source freeze')
    for name, expected in frozen['sha256'].items():
        target = (ROOT/name).resolve()
        if not target.is_relative_to(ROOT) or sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen source/evidence mismatch: '+name)
    return frozen


def validate_source_metadata(native, result, *, contract_version=2):
    """Bind the actual transmitted prompt to the actual completed turn."""
    data = json.loads(native['messages'][0]['content'].rsplit('可信元数据如下：\n', 1)[1])
    context = result['conversation']
    assert data['capability_evidence_version'] == 2
    assert data['current_user_source'] == {'message_id': context['user_message_id'],
                                         'revision': context['revision'], 'verified': True}
    assert data['runtime_attribution'] == {**result['speaker_attribution'], 'origin': 'web_source_store'}
    assert data['declared_model_tool_names'] == capability_evidence()['declared_model_tool_names']
    assert data['current_turn_execution_receipts'] == []
    assert data['registry_readiness_verified'] is data['historical_execution_verified'] is data['semantic_verifier'] is False
    if contract_version in (3, 4):
        assert data['response_contract_version'] == contract_version
        receipts = data['local_execution_evidence']
        assert receipts['scope'] == 'bounded_current_session_current_revision_sql_receipts'
        assert receipts['verified'] is True and receipts['limit'] == 20
        assert type(receipts['has_more']) is bool and len(receipts['items']) <= 20
        assert receipts['current_reminder_state_verified'] is receipts['notification_delivery_verified'] is False
    return data


def collect_arm(case, arm, opener, trace, candidate_id=CANDIDATE, request_timeout=180,
                engine_timeout=None):
    candidate = arm == CANDIDATE_ARM
    row = {'id': case['id'], 'frame': case['frame'], 'arm': arm, 'turns': [], 'completed': False, 'error': None}
    original = main_module.Avatar
    original_engine = main_module.LLMEngine
    with tempfile.TemporaryDirectory(prefix='capability-pair-', dir=project_data_root(ROOT)/'tmp') as folder:
        path = str(Path(folder)/'owned.db'); server = None; thread = None
        try:
            if candidate: main_module.Avatar = CANDIDATES[candidate_id]
            if engine_timeout is not None:
                # Real SDK and transport, explicit research waiting budget only.
                main_module.LLMEngine = partial(LLMEngine, timeout=engine_timeout)
            server = create_server(path, port=0, legacy_writes=False, identity_grounding=False,
                profile_grounding=False, task_delivery_check=False, literal_composition=False)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}/api/v1'
            def query(route, payload=None):
                req = Request(base+route, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                    headers={'X-Avatar-Token': server.token, 'Content-Type': 'application/json'})
                with opener.open(req, timeout=request_timeout) as response: return json.load(response)['data']
            for index, text in enumerate(case['turns']):
                offset = trace.stat().st_size; started = time.perf_counter()
                job = query('/turns', {'request_id': 'capability_pair_'+uuid.uuid4().hex, 'text': text, 'use_web': False})
                req = Request(base+'/turns/'+job['job_id']+'/events', headers={'X-Avatar-Token': server.token})
                with opener.open(req, timeout=request_timeout) as response: kind, result, received, raw = events(response, started)
                turn = {'input': text, 'terminal': kind, 'result': result, 'events': received, 'raw_sse': raw,
                    'visible': ''.join(event['data']['text'] for event in received if event['event'] == 'text'),
                    'seconds': time.perf_counter()-started, 'native_provider': None}
                row['turns'].append(turn)
                if kind != 'result': raise ValueError('Application failed before completed result: '+kind)
                mode = result.get('generation_mode')
                if mode in (None, 'rules_unconfigured', 'rules_service_error'):
                    raise ValueError('Service fallback is not valid quality evidence')
                if mode == 'llm':
                    calls, native = native_calls(trace, offset, text)
                    turn['native_provider'] = native
                    turn['provider_call_ids'] = [call['id'] for call in calls]
                    assert turn['visible'] == result['reply'] == native['response']
                    marked = 'capability_evidence_version' in native['messages'][0]['content']
                    assert marked == candidate
                    if candidate and candidate_id in SOURCE_VERSIONS:
                        turn['validated_source_capability'] = validate_source_metadata(native, result,
                            contract_version=SOURCE_VERSIONS[candidate_id])
                assert result.get('response_review') is None and result['trace']['verifier']['available'] is False
                assert not result['tool_calls']
                turn['conversation'] = query('/conversation')
                turn['speaker_snapshot'] = query('/conversation/speaker')
                with closing(MemoryStore(path)) as memory:
                    turn['current_profile'] = memory.get_user_profile()
                    turn['reminders'] = [dict(record) for record in memory._conn.execute('SELECT * FROM memory_reminders')]
                    turn['stored_assistants'] = [record[0] for record in memory._conn.execute(
                        "SELECT content FROM memory_messages WHERE role='assistant' ORDER BY id")]
                    if mode == 'llm' and candidate and candidate_id in ('lab_source_capability_v3', 'lab_source_capability_v4'):
                        source_id = result['conversation']['user_message_id']
                        session = memory._conn.execute('SELECT session_id FROM memory_messages WHERE id=?', (source_id,)).fetchone()[0]
                        receipts = [dict(r) for r in memory._conn.execute('''SELECT r.* FROM memory_action_receipts r
                            JOIN memory_messages m ON m.id=r.source_message_id AND m.role='user'
                            AND m.session_id=r.session_id AND m.content!='[redacted]'
                            WHERE r.session_id=? AND r.context_revision=? ORDER BY r.id''',
                            (session, result['conversation']['revision']))]
                        turn['actual_local_receipts'] = receipts
                        evidence = turn['validated_source_capability']['local_execution_evidence']
                        fields = ('id', 'source_message_id', 'action', 'reminder_id', 'recorded_at')
                        assert evidence['items'] == [{k:r[k] for k in fields} for r in receipts[-20:]]
                        assert evidence['has_more'] is (len(receipts) > 20)
                assert turn['stored_assistants'][-1] == result['reply']
                expected = case.get('expected_reminders', [0]*len(case['turns']))[index]
                turn['expected_reminder_count'] = expected
                assert len(turn['reminders']) == expected
            row['completed'] = True
        except Exception as error: row['error'] = repr(error)
        finally:
            if server: server.shutdown()
            if thread: thread.join()
            if server: server.server_close()
            main_module.Avatar = original
            main_module.LLMEngine = original_engine
    return row


def validate_execution_contract(frozen, protocol, backend):
    """Bind runtime selection to authorization, beyond a list of hashed files.

    Historical capability freezes were CUDA-only. CPU is opt-in and must
    separately pin compute, offload and transport in the selected protocol.
    """
    if (backend not in ('cuda', 'cpu_explicit')
            or frozen.get('provider_backend', 'cuda') != backend
            or protocol.get('provider_backend', 'cuda') != backend):
        raise ValueError('Selected backend must match both freeze declaration and selected protocol')
    if backend == 'cpu_explicit':
        inference = protocol.get('inference', {})
        if (frozen.get('cpu_threads') != 4 or frozen.get('request_timeout_seconds') != 900
                or protocol.get('request_timeout_seconds') != 900
                or inference.get('n_threads') != 4 or inference.get('n_threads_batch') != 4
                or inference.get('n_gpu_layers') != 0 or inference.get('offload_kqv') is not False):
            raise ValueError('CPU compute/offload/transport settings differ from declared freeze')


def execution_settings(protocol, provider):
    backend = protocol.get('provider_backend', 'cuda')
    if backend not in ('cuda', 'cpu_explicit') or provider.get('backend', 'cuda') != backend:
        raise ValueError('Provider backend differs from the frozen explicit protocol')
    if backend == 'cpu_explicit':
        configuration = provider.get('configuration', {})
        if (provider.get('chosen_gpu') is not None or provider.get('process_gpu_mib_after_load') != []
                or provider.get('effective_visible_devices') != '-1'
                or provider.get('cpu_resources', {}).get('n_threads') != 4
                or configuration.get('n_gpu_layers') != 0 or configuration.get('n_threads') != 4
                or configuration.get('n_threads_batch') != 4 or configuration.get('offload_kqv') is not False
                or protocol.get('request_timeout_seconds') != 900):
            raise ValueError('Explicit CPU resource/transport proof missing')
        return backend, 900, 900
    return backend, 180, None


def evaluate(provider_path, trace, freeze_path, protocol_path, pair_path, partition, output,
             candidate=CANDIDATE, *, expected_freeze_sha256=None):
    frozen_sha = (sha256(freeze_path.read_bytes()).hexdigest() if expected_freeze_sha256 is None
                  else expected_freeze_sha256)
    frozen = verify_freeze(freeze_path, partition, candidate, expected_sha256=frozen_sha)
    for path in (protocol_path, pair_path, Path(__file__).resolve()):
        if str(path.resolve().relative_to(ROOT)) not in frozen['sha256']: raise ValueError('Input not frozen: '+str(path))
    protocol = json.loads(protocol_path.read_text()); pair = json.loads(pair_path.read_text())
    validate_execution_contract(frozen, protocol, protocol.get('provider_backend', 'cuda'))
    provider = json.loads(provider_path.read_text()); address = urlsplit(provider['url'])
    model = next(item for item in json.loads((ROOT/protocol['models_registry']).read_text())['models']
                 if item['model_id'] == provider['model_id'])
    if (address.scheme != 'http' or address.hostname != '127.0.0.1' or address.path != '/v1'
            or provider['model_sha256'] != model['sha256'] or provider['model_revision'] != model['revision']):
        raise ValueError('Only pinned loopback models permitted')
    assert all(provider['configuration'][key] == value for key, value in protocol['inference'].items())
    backend, request_timeout, engine_timeout = execution_settings(protocol, provider)
    cases = [case for case in protocol['cases'] if case['partition'] == partition]
    assert [case['id'] for case in cases] == pair['case_order'][partition]
    assert pair['candidate'] == candidate and set(pair['arm_orders']['even']) == set(pair['arm_orders']['odd']) == {BASELINE, CANDIDATE_ARM}
    assert len(pair['arm_orders']['even']) == len(pair['arm_orders']['odd']) == 2
    output.mkdir(parents=True, exist_ok=False)
    config.llm.base_url = provider['url']; config.llm.api_key = 'local-eval-only'; config.llm.model = provider['model_id']
    config.embedding.model = ''
    report = {'candidate': candidate, 'partition': partition, 'provider': provider, 'warmups': [], 'cases': [],
        'provider_backend': backend, 'http_timeout_seconds': request_timeout,
        'application_transport_timeout_seconds': engine_timeout if engine_timeout is not None else 30,
        'createdUtc': datetime.now(timezone.utc).isoformat(), 'sourceSha256': frozen['sha256'],
        'candidateFreezeSha256': frozen_sha,
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'scope': 'Actual serial HTTP/SSE prompt-only pairs with fresh disposable DB per arm; agent span review separate, no semantic or physical release approval',
        'execution_complete': False, 'engineering_passed': False, 'failure': None,
        'semantic_approved': False, 'production_activation_approved': False}
    started = time.perf_counter()
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        (output/'paired-output.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save(); opener = build_opener(ProxyHandler({}))
    try:
        engine = LLMEngine(base_url=provider['url'], api_key='local-eval-only', model=provider['model_id'], timeout=request_timeout)
        try:
            for streaming in (False, True):
                messages = [{'role': 'user', 'content': '请回答：你好。'}]
                reply = engine.stream_chat(messages, temperature=0, max_tokens=16) if streaming else engine.chat(messages, temperature=0, max_tokens=16)
                report['warmups'].append({'streaming': streaming, 'reply': reply}); save()
        finally: engine.close()
        for index, case in enumerate(cases):
            for arm in pair['arm_orders']['even' if index % 2 == 0 else 'odd']:
                verify_freeze(freeze_path, partition, candidate, expected_sha256=frozen_sha)
                row = collect_arm(case, arm, opener, trace, candidate, request_timeout, engine_timeout)
                report['cases'].append(row); save()
                if not row['completed']: raise ValueError(row['error'])
                print(case['id'], arm, len(row['turns']), flush=True)
        verify_freeze(freeze_path, partition, candidate, expected_sha256=frozen_sha)
        assert len(report['cases']) == len(cases)*2
        report['generation_modes'] = dict(Counter(turn['result']['generation_mode'] for row in report['cases'] for turn in row['turns']))
        report['execution_complete'] = report['engineering_passed'] = True
    except Exception as error: report['failure'] = repr(error)
    finally: save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('provider', 'trace', 'candidate-freeze', 'protocol', 'pair-protocol', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--partition', choices=['development', 'prospective'], required=True)
    parser.add_argument('--candidate', choices=sorted(CANDIDATES), default=CANDIDATE)
    parser.add_argument('--expected-freeze-sha256')
    args = parser.parse_args()
    if not evaluate(args.provider, args.trace, args.candidate_freeze, args.protocol, args.pair_protocol,
                    args.partition, args.output.resolve(), args.candidate,
                    expected_freeze_sha256=args.expected_freeze_sha256)['engineering_passed']: raise SystemExit(1)

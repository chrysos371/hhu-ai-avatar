"""Stage A: real application HTTP/SSE, complete native outputs, no semantic score."""
import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, build_opener
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

import avatar.main  # Verify the application module that create_server will use.
from serve_local_model_eval import load_registry
from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.web import create_server

PROTOCOL = ROOT/'evals/interaction/cycle-15/native-output-protocol.json'


def protocol_registry(protocol):
    name = protocol.get('models_registry')
    if not isinstance(name, str): raise ValueError('Protocol has no model registry')
    path = (ROOT / name).resolve()
    custom = path != ROOT/'evals/interaction/cycle-02/model-scale-protocol.json'
    expected = protocol.get('models_registry_sha256')
    if custom and not isinstance(expected, str): raise ValueError('Custom protocol requires pinned registry identity')
    registry, identity, path = load_registry(path, expected_sha256=expected)
    return registry, identity, path, custom


def validate_provider_identity(provider, protocol):
    """Admission before output/engine creation; legacy default metadata stays compatible."""
    registry, identity, path, custom = protocol_registry(protocol)
    if not isinstance(provider, dict) or not isinstance(provider.get('url'), str):
        raise ValueError('Provider evidence must be an object with a URL')
    model = next((m for m in registry['models'] if m['model_id'] == provider.get('model_id')), None)
    address = urlsplit(provider['url'])
    if (model is None or address.scheme != 'http' or address.hostname != '127.0.0.1' or address.path != '/v1'
            or provider.get('model_sha256') != model['sha256'] or provider.get('model_revision') != model['revision']):
        raise ValueError('Only a hash-verified loopback provider is allowed')
    relative = str(path.relative_to(ROOT))
    if ((custom or 'registry_sha256' in provider) and provider.get('registry_sha256') != identity
            or (custom or 'registry_path' in provider) and provider.get('registry_path') != relative):
        raise ValueError('Provider registry identity differs from selected protocol')
    declared_backend = protocol.get('provider_backend', 'cuda')
    if (custom and provider.get('backend') != declared_backend
            or provider.get('backend', declared_backend) != declared_backend):
        raise ValueError('Provider backend differs from selected protocol')
    binding = {'registry_path': relative, 'registry_sha256': identity}
    if model.get('metadata'):
        expected_path = (ROOT / model['metadata']).resolve()
        expected_metadata = sha256(expected_path.read_bytes()).hexdigest()
        if (provider.get('metadata_sha256') != expected_metadata or not isinstance(provider.get('metadata_path'), str)
                or Path(provider['metadata_path']).resolve() != expected_path):
            raise ValueError('Provider model metadata identity differs from selected registry')
        binding.update(metadata_path=model['metadata'], metadata_sha256=expected_metadata)
    if custom:
        gpu = provider.get('chosen_gpu'); allocations = provider.get('process_gpu_mib_after_load')
        configuration = provider.get('configuration')
        if (declared_backend != 'cuda' or not isinstance(gpu, dict) or not isinstance(gpu.get('uuid'), str)
                or not gpu['uuid'] or type(gpu.get('free_mib')) is not int
                or gpu['free_mib'] < model['required_free_mib']
                or type(gpu.get('utilization_percent')) is not int or not 0 <= gpu['utilization_percent'] <= 20
                or not isinstance(allocations, list) or len(allocations) != 1
                or any(type(value) is not int or value < 1024 for value in allocations)
                or provider.get('effective_visible_devices') != gpu['uuid']
                or not isinstance(configuration, dict) or configuration.get('n_gpu_layers') != -1):
            raise ValueError('CUDA admission/allocation evidence missing for custom registry')
    return model, binding


def runtime_source_identity():
    result = {}
    for name, module in sorted(list(sys.modules.items())):
        if name != 'avatar' and not name.startswith('avatar.'): continue
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if not path.is_relative_to(ROOT/'src'):
                raise ValueError('Application imported outside this project: ' + name)
            result[name] = {'path': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}
    if not {'avatar.main', 'avatar.web', 'avatar.brain.memory', 'avatar.brain.llm'} <= result.keys():
        raise ValueError('Required application runtime modules are not bound')
    return result


def fingerprint(protocol_path=PROTOCOL):
    paths = ['src/avatar/main.py', 'src/avatar/web.py', 'src/avatar/web_api.py',
             'src/avatar/brain/llm.py', 'src/avatar/brain/memory.py', 'src/avatar/brain/boundaries.py',
             'src/avatar/brain/speaker_scope.py', 'src/avatar/brain/speaker_context.py',
             'scripts/serve_local_model_eval.py', str(Path(__file__).resolve().relative_to(ROOT)),
             str(protocol_path.relative_to(ROOT))]
    registry, _, registry_path, _ = protocol_registry(json.loads(protocol_path.read_text()))
    paths.append(str(registry_path.relative_to(ROOT)))
    paths += [m['metadata'] for m in registry['models'] if m.get('metadata')]
    paths += [str(path.relative_to(ROOT)) for path in ROOT.glob('src/avatar/**/*.py')]
    return {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}


def verify_execution_freeze(path, expected_sha256, protocol_path, *, model_id=None):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('Execution freeze descriptor identity changed')
    frozen = json.loads(raw)
    if not isinstance(frozen, dict): raise ValueError("Invalid execution freeze object")
    protocol_path = Path(protocol_path).resolve()
    protocol = json.loads(protocol_path.read_text())
    registry, registry_sha, registry_path, _ = protocol_registry(protocol)
    cases = [c for c in protocol['cases'] if c['partition'] == 'development']
    models = frozen.get('models')
    registered_ids = {m['model_id'] for m in registry['models']}
    selected = {model_id} if model_id is not None else registered_ids
    if (frozen.get('scope') != 'native_current_defaults_model_scale' or frozen.get('candidate') != 'none'
            or frozen.get('execution_authorized') is not True or frozen.get('allowed_partition') != 'development'
            or frozen.get('provider_backend') != 'cuda' or protocol.get('provider_backend', 'cuda') != 'cuda'
            or frozen.get('protocol') != str(protocol_path.relative_to(ROOT))
            or frozen.get('models_registry') != str(registry_path.relative_to(ROOT))
            or frozen.get('registry_sha256') != registry_sha
            or not isinstance(models, list) or not models or any(not isinstance(m, str) for m in models)
            or len(set(models)) != len(models) or not set(models) <= registered_ids or not selected <= set(models)
            or frozen.get('case_ids') != [c['id'] for c in cases]
            or type(frozen.get('case_count')) is not int or frozen['case_count'] != len(cases)
            or type(frozen.get('turn_count')) is not int or frozen['turn_count'] != sum(len(c['turns']) for c in cases)):
        raise ValueError('Current-default execution freeze contract mismatch')
    hashes = frozen.get('sha256')
    required = set(fingerprint(protocol_path)) | {'scripts/run_native_output_models.py'}
    if not isinstance(hashes, dict) or not required <= hashes.keys():
        raise ValueError('Execution freeze inputs incomplete')
    for name, expected in hashes.items():
        if not isinstance(name, str) or Path(name).is_absolute() or not (ROOT/name).resolve().is_relative_to(ROOT):
            raise ValueError('Execution freeze contains a non-project input')
        if sha256((ROOT/name).read_bytes()).hexdigest() != expected:
            raise ValueError('Execution frozen source changed: ' + name)
    return frozen


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


def evaluate(provider_path, output, protocol_path=PROTOCOL, *, execution_freeze=None, expected_execution_freeze_sha256=None):
    protocol_path = Path(protocol_path).resolve()
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
    model, registry_binding = validate_provider_identity(provider, protocol)
    if (execution_freeze is None) != (expected_execution_freeze_sha256 is None):
        raise ValueError('Execution freeze requires its externally pinned descriptor SHA')
    custom_registry = registry_binding['registry_path'] != 'evals/interaction/cycle-02/model-scale-protocol.json'
    if custom_registry and execution_freeze is None:
        raise ValueError('Custom registry requires a current-default execution freeze')
    def verify_inputs():
        if execution_freeze is not None:
            return verify_execution_freeze(execution_freeze, expected_execution_freeze_sha256,
                                          protocol_path, model_id=provider['model_id'])
    verify_inputs()
    for key, value in protocol['inference'].items():
        if provider['configuration'][key] != value: raise ValueError('Inference configuration differs: '+key)
    source_fingerprint = fingerprint(protocol_path)
    runtime_modules = runtime_source_identity()
    output.mkdir(parents=True, exist_ok=False)
    config.llm.base_url = provider['url']; config.llm.api_key = 'local-eval-only'; config.llm.model = provider['model_id']
    config.embedding.model = ''
    report = {'scope': protocol['scope'], 'partition': 'development', 'stage': 'A_current_defaults',
              'createdUtc': datetime.now(timezone.utc).isoformat(),
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sourceSha256': source_fingerprint, 'runtime_modules': runtime_modules,
              'registry_binding': registry_binding, 'provider': provider, 'warmups': [], 'cases': [],
              'protocol': str(protocol_path.relative_to(ROOT)), 'executionFreezeSha256': expected_execution_freeze_sha256,
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
                verify_inputs()
                tick = time.perf_counter(); messages = [{'role': 'user', 'content': '请回答：你好。'}]
                reply = engine.stream_chat(messages, temperature=0, max_tokens=16) if streaming else engine.chat(messages, temperature=0, max_tokens=16)
                report['warmups'].append({'streaming': streaming, 'reply': reply, 'seconds': time.perf_counter()-tick}); save()
        finally: engine.close()
        for case in cases:
            verify_inputs()
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
                        verify_inputs()
                        current_modules = runtime_source_identity()
                        if any(current_modules.get(name) != value for name, value in runtime_modules.items()):
                            raise RuntimeError('Application runtime modules changed during native experiment')
                        report['runtime_modules'] = current_modules
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
            verify_inputs()
            print(case['id'], 'completed', len(row['turns']), flush=True)
        verify_inputs()
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
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execution-freeze', type=Path)
    parser.add_argument('--expected-execution-freeze-sha256')
    options = parser.parse_args()
    result = evaluate(options.provider, options.output.resolve(), options.protocol.resolve() if options.protocol else PROTOCOL,
        execution_freeze=options.execution_freeze, expected_execution_freeze_sha256=options.expected_execution_freeze_sha256)
    if not result['engineering_passed']: raise SystemExit(1)

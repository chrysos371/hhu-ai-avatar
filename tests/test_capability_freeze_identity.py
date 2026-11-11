"""Execution identity checks using real entries and controlled model boundaries.

No model, HTTP request or SQL operation is performed by these fixtures.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'scripts/lab'))
import evaluate_capability_pair as audit
import run_frozen_capability_job as jobs

CANDIDATE = 'lab_source_capability_v4'
PROTOCOL = ROOT / 'evals/interaction/cycle-23/capability-output-protocol.json'
PAIR = ROOT / 'evals/interaction/cycle-23/paired-capability-protocol.json'


def frozen(path):
    descriptor = {'candidate': CANDIDATE, 'provider_backend': 'cuda',
                  'execution_authorized': True, 'allowed_partition': 'development',
                  'prospective_execution_authorized': False, 'scope': 'Controlled fixture only',
                  'sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest()
                             for name in audit.required_sources(CANDIDATE)}}
    path.write_text(json.dumps(descriptor))
    assert audit.verify_freeze(path, 'development', CANDIDATE) == descriptor
    return descriptor


@pytest.mark.parametrize('mutation', ['backend', 'scope', 'format', None])
def test_sampler_rejects_changed_descriptor_before_next_arm(tmp_path, monkeypatch, mutation):
    freeze = tmp_path / 'freeze.json'
    descriptor = frozen(freeze)
    initial = sha256(freeze.read_bytes()).hexdigest()
    protocol = json.loads(PROTOCOL.read_text())
    model = next(row for row in json.loads((ROOT / protocol['models_registry']).read_text())['models']
                 if row['model_id'] == 'qwen3-4b-q4_k_m')
    ready = tmp_path / 'provider.json'
    ready.write_text(json.dumps({'url': 'http://127.0.0.1:1/v1', 'backend': 'cuda',
                                'model_id': model['model_id'], 'model_sha256': model['sha256'],
                                'model_revision': model['revision'], 'configuration': protocol['inference']}))
    class Engine:
        def __init__(self, **kwargs):
            pass
        def chat(self, *args, **kwargs):
            return 'controlled warmup'
        stream_chat = chat
        def close(self):
            pass
    calls = []
    def arm(case, label, *args):
        calls.append((case['id'], label))
        if len(calls) == 1 and mutation is not None:
            if mutation == 'backend':
                descriptor['provider_backend'] = 'cpu_explicit'
            elif mutation == 'scope':
                descriptor['scope'] = 'Changed after first controlled arm'
            freeze.write_text(json.dumps(descriptor, indent=2))
        return {'id': case['id'], 'arm': label, 'completed': True, 'error': None,
                'turns': [{'result': {'generation_mode': 'controlled_fixture'}} for _ in case['turns']]}
    monkeypatch.setattr(audit, 'LLMEngine', Engine)
    monkeypatch.setattr(audit, 'collect_arm', arm)
    for obj, field in ((audit.config.llm, 'base_url'), (audit.config.llm, 'api_key'),
                       (audit.config.llm, 'model'), (audit.config.embedding, 'model')):
        monkeypatch.setattr(obj, field, getattr(obj, field))
    report = audit.evaluate(ready, tmp_path / 'unused-trace', freeze, PROTOCOL, PAIR,
                            'development', tmp_path / 'owned-output', CANDIDATE)
    observation = {'mutation': mutation, 'controlled_arm_boundaries': len(calls),
                   'initial_sha256': initial, 'final_sha256': sha256(freeze.read_bytes()).hexdigest(),
                   'recorded_sha256': report['candidateFreezeSha256'], 'failure': report['failure'],
                   'execution_complete': report['execution_complete'], 'engineering_passed': report['engineering_passed'],
                   'model_http_sql_executed': False}
    print('FREEZE_IDENTITY_OBSERVATION ' + json.dumps(observation, sort_keys=True))
    assert report['candidateFreezeSha256'] == initial
    if mutation is not None:
        assert observation['final_sha256'] != initial
        assert not report['engineering_passed'], observation
        assert not report['execution_complete'] and len(calls) == 1, observation
        assert report['failure'], observation
    else:
        assert observation['final_sha256'] == initial
        assert report['engineering_passed'] and report['execution_complete'] and len(calls) == 24


def test_supervisor_handoff_pins_expected_descriptor_sha():
    parent = ROOT / '.runtime/tmp'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='freeze-identity-', dir=parent) as name:
        directory = Path(name)
        freeze = directory / 'freeze.json'
        frozen(freeze)
        spec = {'candidate': 'source_capability_v4', 'candidate_freeze': str(freeze.relative_to(ROOT)),
                'protocol': str(PROTOCOL.relative_to(ROOT)), 'pair_protocol': str(PAIR.relative_to(ROOT)),
                'output': str((directory / 'unused-output').relative_to(ROOT)), 'backend': 'cuda',
                'partition': 'development', 'model_key': 'qwen3-4b-q4_k_m', 'provider_python': sys.executable}
        command, context = jobs.prepare(spec)
        index = command.index('--expected-freeze-sha256') if '--expected-freeze-sha256' in command else None
        expected = command[index + 1] if index is not None else None
        actual = sha256(freeze.read_bytes()).hexdigest()
        print('FREEZE_HANDOFF_OBSERVATION ' + json.dumps({'expected_sha_in_command': expected,
              'context_sha': context['freeze_sha256'], 'actual_sha': actual, 'model_launched': False}))
        assert expected == context['freeze_sha256'] == actual


@pytest.mark.parametrize('entry', ['runner', 'sampler'])
def test_real_child_entry_rejects_parent_sha_before_output_or_model(tmp_path, entry):
    freeze = tmp_path / 'freeze.json'
    descriptor = frozen(freeze)
    original = sha256(freeze.read_bytes()).hexdigest()
    descriptor['scope'] = 'Changed between parent and child'
    freeze.write_text(json.dumps(descriptor))
    output = tmp_path / 'must-not-exist'
    command = [sys.executable, str(ROOT / 'scripts' / ('run_native_output_models.py' if entry == 'runner'
                                                      else 'evaluate_capability_pair.py')),
               '--candidate-freeze', str(freeze), '--protocol', str(PROTOCOL), '--pair-protocol', str(PAIR),
               '--partition', 'development', '--output', str(output), '--expected-freeze-sha256', original]
    if entry == 'runner':
        command += ['--provider-python', sys.executable, '--stage', 'capability_pair',
                    '--candidate', 'source_capability_v4', '--backend', 'cuda', '--model-key', 'qwen3-4b-q4_k_m']
    else:
        command += ['--provider', str(tmp_path / 'nonexistent-provider.json'),
                    '--trace', str(tmp_path / 'unused-trace'), '--candidate', CANDIDATE]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    print('FREEZE_CHILD_OBSERVATION ' + json.dumps({'entry': entry, 'returncode': result.returncode,
          'identity_rejected': 'Frozen descriptor identity changed' in result.stderr,
          'output_exists': output.exists(), 'model_started': False}))
    assert result.returncode != 0 and 'Frozen descriptor identity changed' in result.stderr
    assert not output.exists()

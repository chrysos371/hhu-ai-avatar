"""Public research entry points must enforce the declared frozen backend.

Complete real source hashes are used. Only provider spawn / model engine
construction is replaced, so accepted mismatches cannot allocate a model.
"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import evaluate_capability_pair as audit
import run_native_output_models as runner

CPU = ROOT / 'evals/interaction/cycle-21/cpu-capability-output-protocol.json'
CUDA = ROOT / 'evals/interaction/cycle-19/capability-output-protocol.json'
PAIR = ROOT / 'evals/interaction/cycle-21/paired-capability-protocol.json'
CANDIDATE = 'lab_source_capability_v2'


class BoundaryReached(RuntimeError):
    pass


def exercise(tmp_path, monkeypatch, entry, declared, selected):
    protocol_path = CPU if selected == 'cpu_explicit' else CUDA
    protocol = json.loads(protocol_path.read_text())
    names = audit.required_sources(CANDIDATE) | {str(CPU.relative_to(ROOT)), str(PAIR.relative_to(ROOT))}
    frozen = {'candidate': CANDIDATE, 'execution_authorized': True,
              'allowed_partition': 'development', 'prospective_execution_authorized': False,
              'sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in names}, **declared}
    freeze = tmp_path / 'freeze.json'
    freeze.write_text(json.dumps(frozen))
    # A mismatched backend is the only intended defect, not missing source authority.
    assert audit.verify_freeze(freeze, 'development', CANDIDATE) == frozen
    output = tmp_path / 'owned-output'
    reached = []
    def boundary(*args, **kwargs):
        reached.append(True)
        raise BoundaryReached('controlled provider spawn / model engine construction')
    error = None
    report = None
    try:
        if entry == 'runner':
            monkeypatch.setattr(runner, 'subprocess', SimpleNamespace(
                check_output=subprocess.check_output, Popen=boundary, STDOUT=subprocess.STDOUT))
            monkeypatch.setattr(runner, 'gpu_snapshot', lambda: 'controlled unused GPU observation')
            monkeypatch.setattr(runner, 'gpu_processes', lambda: '')
            runner.main(output, Path(sys.executable), stage='capability_pair',
                        model_key='qwen3-4b-q4_k_m', candidate_freeze=freeze,
                        protocol=protocol_path, pair_protocol=PAIR, candidate='source_capability_v2',
                        partition='development', backend=selected)
        else:
            registry = json.loads((ROOT / protocol['models_registry']).read_text())
            model = next(m for m in registry['models'] if m['model_id'] == 'qwen3-4b-q4_k_m')
            provider = {'url': 'http://127.0.0.1:1/v1', 'model_id': model['model_id'],
                        'model_sha256': model['sha256'], 'model_revision': model['revision'],
                        'configuration': protocol['inference'], 'backend': selected,
                        'chosen_gpu': None, 'process_gpu_mib_after_load': [],
                        'effective_visible_devices': '-1', 'cpu_resources': {'n_threads': 4}}
            ready = tmp_path / 'provider.json'
            ready.write_text(json.dumps(provider))
            monkeypatch.setattr(audit, 'LLMEngine', boundary)
            # evaluate mutates process-local SDK configuration; restore it at test teardown.
            for obj, field in ((audit.config.llm, 'base_url'), (audit.config.llm, 'api_key'),
                               (audit.config.llm, 'model'), (audit.config.embedding, 'model')):
                monkeypatch.setattr(obj, field, getattr(obj, field))
            report = audit.evaluate(ready, tmp_path / 'unused-trace', freeze, protocol_path,
                                    PAIR, 'development', output, CANDIDATE)
    except Exception as exc:
        error = exc
    observation = {'entry': entry, 'declared': declared, 'selected': selected,
                   'full_source_hashes_valid': True, 'controlled_boundary_calls': len(reached),
                   'output_created': output.exists(), 'error_type': type(error).__name__ if error else None,
                   'error': str(error) if error else None, 'report_failure': report.get('failure') if report else None,
                   'actual_model_or_gpu_started': False}
    print('CONTRACT_OBSERVATION ' + json.dumps(observation, sort_keys=True))
    return observation, error


@pytest.mark.parametrize('entry', ['runner', 'sampler'])
@pytest.mark.parametrize('declared,selected', [
    ({'provider_backend': 'cpu_explicit', 'cpu_threads': 4, 'request_timeout_seconds': 900}, 'cuda'),
    ({'provider_backend': 'cuda'}, 'cpu_explicit'),
    ({}, 'cpu_explicit'),
    ({'provider_backend': 'invalid'}, 'cuda'),
    ({'provider_backend': 'cpu_explicit', 'cpu_threads': 8, 'request_timeout_seconds': 900}, 'cpu_explicit'),
    ({'provider_backend': 'cpu_explicit', 'cpu_threads': 4, 'request_timeout_seconds': 30}, 'cpu_explicit'),
    ({'provider_backend': 'cpu_explicit', 'request_timeout_seconds': 900}, 'cpu_explicit'),
])
def test_mismatch_rejected_before_provider_or_output(tmp_path, monkeypatch, entry, declared, selected):
    observed, error = exercise(tmp_path, monkeypatch, entry, declared, selected)
    assert isinstance(error, ValueError), observed
    assert observed['controlled_boundary_calls'] == 0, observed
    assert not observed['output_created'], observed


@pytest.mark.parametrize('entry', ['runner', 'sampler'])
@pytest.mark.parametrize('declared,selected', [
    ({'provider_backend': 'cuda'}, 'cuda'),
    ({}, 'cuda'),  # Historical CUDA freezes predate the explicit CPU protocol.
    ({'provider_backend': 'cpu_explicit', 'cpu_threads': 4, 'request_timeout_seconds': 900}, 'cpu_explicit'),
])
def test_authorized_execution_reaches_same_controlled_boundary(tmp_path, monkeypatch, entry, declared, selected):
    observed, error = exercise(tmp_path, monkeypatch, entry, declared, selected)
    assert observed['controlled_boundary_calls'] == 1, observed
    assert observed['output_created'], observed
    assert isinstance(error, BoundaryReached) or observed['report_failure'].startswith('BoundaryReached(')

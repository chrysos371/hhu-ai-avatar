import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import evaluate_capability_pair as pairs
import run_native_output_models as runner
import serve_local_model_eval as provider


def test_measured_cpu_headroom_admits_only_four_thread_configuration():
    evidence = {'affinity': list(range(8)), 'memory_available_mib': 32768, 'load_average': [1., 1., 1.]}
    actual = provider.validate_cpu_headroom(evidence, 24576)
    assert actual == {**evidence, 'n_threads': 4, 'required_free_mib': 24576}


@pytest.mark.parametrize('changes', [
    {'affinity': [0, 1, 2]}, {'affinity': [0, 1, 2, 3, 3]}, {'affinity': [False, 1, 2, 3, 4]},
    {'memory_available_mib': 24575}, {'memory_available_mib': True},
    {'load_average': [float('nan'), 0., 0.]}, {'load_average': [5., 1., 1.]},
])
def test_insufficient_or_invalid_cpu_inventory_cannot_start_model(changes):
    evidence = {'affinity': list(range(8)), 'memory_available_mib': 32768, 'load_average': [1., 1., 1.]}
    with pytest.raises(RuntimeError): provider.validate_cpu_headroom({**evidence, **changes}, 24576)


def cpu_ready():
    return {'backend': 'cpu_explicit', 'chosen_gpu': None, 'process_gpu_mib_after_load': [],
        'effective_visible_devices': '-1', 'cpu_resources': {'n_threads': 4},
        'configuration': {'n_gpu_layers': 0, 'n_threads': 4, 'n_threads_batch': 4, 'offload_kqv': False}}


def test_cpu_transport_is_explicit_and_cuda_defaults_are_preserved():
    protocol = {'provider_backend': 'cpu_explicit', 'request_timeout_seconds': 900}
    assert pairs.execution_settings(protocol, cpu_ready()) == ('cpu_explicit', 900, 900)
    assert pairs.execution_settings({}, {}) == ('cuda', 180, None)
    with pytest.raises(ValueError): pairs.execution_settings({}, cpu_ready())


@pytest.mark.parametrize('field,value', [
    ('backend', 'cuda'), ('chosen_gpu', {'index': 0}), ('process_gpu_mib_after_load', [100]),
    ('effective_visible_devices', '0'), ('cpu_resources', {'n_threads': 8}),
    ('configuration', {'n_gpu_layers': -1, 'n_threads': 4, 'n_threads_batch': 4, 'offload_kqv': False}),
])
def test_cpu_ready_requires_no_gpu_and_exact_compute_thread_evidence(field, value):
    ready = cpu_ready(); ready[field] = value
    with pytest.raises(ValueError):
        pairs.execution_settings({'provider_backend': 'cpu_explicit', 'request_timeout_seconds': 900}, ready)


def test_cpu_requires_its_transport_budget_and_separate_protocol(tmp_path):
    with pytest.raises(ValueError):
        pairs.execution_settings({'provider_backend': 'cpu_explicit', 'request_timeout_seconds': 180}, cpu_ready())
    output = tmp_path/'must-not-create'
    with pytest.raises(ValueError):
        runner.main(output, Path(sys.executable), stage='development', backend='cpu_explicit')
    with pytest.raises(ValueError):
        runner.main(output, Path(sys.executable), stage='capability_pair', backend='cpu_explicit')
    protocol = tmp_path/'gpu.json'; protocol.write_text(json.dumps({'provider_backend': 'cuda'}))
    with pytest.raises(ValueError):
        runner.main(output, Path(sys.executable), stage='capability_pair', backend='cpu_explicit',
                    protocol=protocol, pair_protocol=protocol, candidate_freeze=protocol)
    assert not output.exists()

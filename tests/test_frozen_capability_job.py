"""Real short processes exercise lifecycle; no model or GPU is launched."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/lab/run_frozen_capability_job.py'
spec = importlib.util.spec_from_file_location('frozen_job', SCRIPT)
job = importlib.util.module_from_spec(spec)
spec.loader.exec_module(job)


def finished(folder):
    limit = time.monotonic()+15
    while time.monotonic() < limit:
        state = job.status(folder)
        if state['state'] in ('completed', 'failed', 'interrupted'):
            return state
        time.sleep(.05)
    pytest.fail('Short fixture did not finish; inspect '+str(folder))


def cpu():
    return ({'provider_backend': 'cpu_explicit', 'cpu_threads': 4,
             'request_timeout_seconds': 900},
            {'provider_backend': 'cpu_explicit', 'request_timeout_seconds': 900,
             'inference': {'n_threads': 4, 'n_threads_batch': 4,
                           'n_gpu_layers': 0, 'offload_kqv': False}})


def test_backend_binding():
    freeze, protocol = cpu()
    job.validate_backend(freeze, protocol, 'cpu_explicit')
    with pytest.raises(ValueError): job.validate_backend(freeze, protocol, 'cuda')
    protocol['provider_backend'] = 'cuda'
    with pytest.raises(ValueError): job.validate_backend(freeze, protocol, 'cpu_explicit')


@pytest.mark.parametrize('field,value', [('n_threads', 8), ('n_threads_batch', 2)])
def test_compute_threads_pinned(field, value):
    freeze, protocol = cpu(); protocol['inference'][field] = value
    with pytest.raises(ValueError): job.validate_backend(freeze, protocol, 'cpu_explicit')


def test_transport_pinned():
    freeze, protocol = cpu(); protocol['request_timeout_seconds'] = 30
    with pytest.raises(ValueError): job.validate_backend(freeze, protocol, 'cpu_explicit')


def test_survives_launcher_exit(tmp_path):
    folder = tmp_path/'detached'
    code = ('import importlib.util,json,sys; from pathlib import Path; '
            's=importlib.util.spec_from_file_location("j",sys.argv[1]); '
            'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
            'print(json.dumps(m.launch([sys.executable,"-c","import time; time.sleep(1.5); print(123)"],Path(sys.argv[2]))))')
    parent = subprocess.run([sys.executable, '-c', code, str(SCRIPT), str(folder)],
                            capture_output=True, text=True, check=True)
    launched = json.loads(parent.stdout)
    assert job.matches(job.process(launched['worker_pid']))
    state = finished(folder)
    assert state['state'] == 'completed' and state['return_code'] == 0
    assert not state['child_verified_alive']
    assert state['worker']['process_group'] == launched['worker_pid']
    assert state['child']['process_group'] == state['child']['pid']
    assert (folder/'experiment.log').read_text().strip() == '123'


def test_records_failure_and_refuses_overwrite(tmp_path):
    folder = tmp_path/'failure'
    job.launch([sys.executable, '-c', 'raise SystemExit(7)'], folder)
    state = finished(folder)
    assert state['state'] == 'failed' and state['return_code'] == 7
    original = (folder/'config.json').read_bytes()
    with pytest.raises(FileExistsError): job.launch([sys.executable], folder)
    assert (folder/'config.json').read_bytes() == original


def test_rejects_unrecordable_environment_before_write(tmp_path):
    folder = tmp_path/'secret'
    with pytest.raises(ValueError): job.launch([sys.executable], folder, environment={'TOKEN': 'fixture'})
    assert not folder.exists()


def test_requested_stop_only_owned_child(tmp_path):
    folder = tmp_path/'stop'
    launched = job.launch([sys.executable, '-c', 'import time; time.sleep(30)'], folder)
    limit = time.monotonic()+10
    while time.monotonic() < limit:
        state = job.status(folder)
        if state['child_verified_alive']: break
        time.sleep(.05)
    else: pytest.fail('Child did not start')
    assert job.matches(state['worker'])
    os.kill(launched['worker_pid'], signal.SIGTERM)
    state = finished(folder)
    assert state['state'] == 'interrupted'
    assert state['stop_signal'] == signal.SIGTERM and state['return_code'] != 0
    assert not state['child_verified_alive']


def test_changed_descriptor_has_terminal_failure(tmp_path):
    folder = tmp_path/'tampered'; folder.mkdir()
    job.write_json(folder/'config.json', {})
    subprocess.run([sys.executable, str(SCRIPT), '--worker', str(folder),
                    '--config-sha256', 'incorrect'], check=True)
    state = job.status(folder)
    assert state['state'] == 'failed' and state['child'] is None
    assert 'changed after launch' in state['error']
    assert not (folder/'experiment.log').exists()

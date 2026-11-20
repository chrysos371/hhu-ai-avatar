"""Detached supervision for explicitly frozen capability experiments.

The command-line launcher constructs only the existing pinned experiment
command. The small generic supervisor is separately testable with tiny children.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
GUARD = Path(__file__).resolve().with_name('guard_direct_child.py')
sys.path.insert(0, str(ROOT/'src'))
sys.path.insert(0, str(ROOT/'scripts'))
from avatar.paths import project_data_root


def utc(): return datetime.now(timezone.utc).isoformat()
def digest(path): return sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    descriptor, name = tempfile.mkstemp(prefix='.status-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def process(pid):
    try:
        folder = Path('/proc')/str(pid)
        fields = (folder/'stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0],
            'argv': (folder/'cmdline').read_bytes().decode().rstrip('\0').split('\0'),
            'process_group': os.getpgid(pid)}
    except (FileNotFoundError, ProcessLookupError, PermissionError): return None


def matches(identity):
    if not identity: return False
    actual = process(identity['pid'])
    return bool(actual and actual['state'] != 'Z' and actual['start_ticks'] == identity['start_ticks']
                and actual['argv'] == identity['argv'])


def validate_backend(frozen, protocol, backend):
    from evaluate_capability_pair import validate_execution_contract
    validate_execution_contract(frozen, protocol, backend)


def experiment_path(name, value):
    path = (ROOT / value).resolve()
    if name in ('candidate_freeze', 'output'):
        allowed = (ROOT.resolve(), project_data_root(ROOT).resolve())
    elif name in ('protocol', 'pair_protocol'):
        allowed = (ROOT.resolve(),)
    else:
        raise ValueError('Unknown experiment path role')
    if not any(path.is_relative_to(base) for base in allowed):
        raise ValueError('Experiment path outside project or owned data root')
    return path


def prepare(spec):
    from evaluate_capability_pair import verify_freeze, CLI_CANDIDATES
    required = {'candidate', 'candidate_freeze', 'protocol', 'pair_protocol', 'output',
                'backend', 'partition', 'model_key', 'provider_python'}
    if set(spec) != required or any(not isinstance(value, str) or not value for value in spec.values()):
        raise ValueError('Use only the explicit frozen experiment selection fields')
    choices = CLI_CANDIDATES
    if spec['candidate'] not in choices: raise ValueError('Unknown candidate')
    freeze, protocol, pair, output = (experiment_path(name, spec[name])
                                    for name in ('candidate_freeze', 'protocol', 'pair_protocol', 'output'))
    frozen_sha = digest(freeze)
    frozen = verify_freeze(freeze, spec['partition'], choices[spec['candidate']], expected_sha256=frozen_sha)
    data = json.loads(protocol.read_text()); validate_backend(frozen, data, spec['backend'])
    for path in (protocol, pair):
        if str(path.relative_to(ROOT)) not in frozen['sha256']: raise ValueError('Selected protocol not frozen')
    registry = json.loads((ROOT/data['models_registry']).read_text())
    if spec['model_key'] not in {row['model_id'] for row in registry['models']}: raise ValueError('Unknown pinned model')
    if output.exists(): raise FileExistsError('Use a fresh complete-cohort output path')
    for folder in Path('/proc').iterdir():
        if not folder.name.isdecimal(): continue
        current = process(int(folder.name))
        if current and current['state'] != 'Z' and str(ROOT/'scripts/serve_local_model_eval.py') in current['argv']:
            raise RuntimeError('Project provider already alive; inspect it instead of launching another')
    provider = Path(spec['provider_python']).expanduser().absolute()  # Preserve venv symlink.
    if not provider.is_file() or not os.access(provider, os.X_OK): raise ValueError('Provider Python unavailable')
    command = [sys.executable, str(ROOT/'scripts/run_native_output_models.py'), '--provider-python', str(provider),
        '--stage', 'capability_pair', '--backend', spec['backend'], '--candidate', spec['candidate'],
        '--partition', spec['partition'], '--model-key', spec['model_key'], '--candidate-freeze', str(freeze),
        '--protocol', str(protocol), '--pair-protocol', str(pair), '--output', str(output),
        '--expected-freeze-sha256', frozen_sha]
    recorded_path = lambda path: str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    context = {'freeze': recorded_path(freeze), 'freeze_sha256': frozen_sha,
        'frozen_inputs': len(frozen['sha256']), 'protocol_sha256': digest(protocol), 'pair_protocol_sha256': digest(pair),
        'backend': spec['backend'], 'model_key': spec['model_key'], 'partition': spec['partition'],
        'output': recorded_path(output), 'whole_experiment_deadline': None, 'selection': spec}
    return command, context


def launch(command, job, *, context=None, environment=None):
    if not command or any(not isinstance(value, str) or '\0' in value for value in command):
        raise ValueError('Command must be a nonempty argv list')
    if not set(environment or {}) <= {'OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS'}:
        raise ValueError('Only explicit nonsecret compute-thread overrides are recorded')
    job = job.absolute(); job.mkdir(parents=True, exist_ok=False)
    config = {'command': command, 'cwd': str(ROOT), 'context': context or {},
        'environment': environment or {}, 'controller_sha256': digest(Path(__file__).resolve()),
        'parent_death_guard_sha256': digest(GUARD), 'created_utc': utc()}
    write_json(job/'config.json', config)
    write_json(job/'status.json', {'state': 'queued', 'created_utc': config['created_utc']})
    command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(job),
               '--config-sha256', digest(job/'config.json')]
    with (job/'supervisor.log').open('xb') as stream:
        worker = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=stream,
            stderr=subprocess.STDOUT, start_new_session=True)
    write_json(job/'launch.json', {'worker_pid': worker.pid, 'worker_identity': process(worker.pid),
        'launcher_pid': os.getpid(), 'launched_utc': utc(), 'detached_session': True})
    return {'job': str(job), 'worker_pid': worker.pid}


def signal_owned_child(child, identity, signum):
    # A successful exec intentionally changes argv. PID/start ticks and the
    # fresh session remain stable throughout that one owned transition.
    current = process(child.pid)
    if (identity and current and current['state'] != 'Z'
            and current['start_ticks'] == identity['start_ticks']
            and current['process_group'] == child.pid):
        os.killpg(child.pid, signum)
        return True
    return False


def observe_protected_exec(child, job, config, expected, state, requested):
    state['payload_argv_observed'] = False
    end = time.monotonic() + 10  # Exec readiness only; never a job deadline.
    while child.poll() is None:
        current = process(child.pid)
        if current and current['argv'] == config['command']:
            state['child'] = current
            state['payload_argv_observed'] = True
            break
        if requested and state['stop_signal'] is None:
            if signal_owned_child(child, state['child'], signal.SIGINT):
                state['stop_signal'] = requested[0]
                state['state'] = 'stopping'
        if time.monotonic() >= end:
            raise RuntimeError('Protected payload exec readiness exceeded 10 seconds')
        time.sleep(.01)
    receipt = job/'parent-death-guard.json'
    if receipt.exists():
        guard = json.loads(receipt.read_text())
        if not (guard['installed'] and guard['pid'] == child.pid
                and guard['parent_pid'] == os.getpid()
                and guard['process_group'] == child.pid
                and guard['kernel_parent_death_signal'] == signal.SIGKILL
                and guard['config_sha256'] == expected
                and guard['guard_sha256'] == config['parent_death_guard_sha256']
                and guard['target_argv'] == config['command']
                and (state['child'] is None or guard['start_ticks'] == state['child']['start_ticks'])):
            raise ValueError('Actual parent-death guard receipt differs')
        state['parent_death_guard_sha256'] = digest(receipt)
    elif child.poll() == 0 or state['payload_argv_observed']:
        raise ValueError('Payload success/exec cannot omit actual parent-death guard')
    write_json(job/'status.json', state)


def supervise(job, expected):
    # Reject both legacy attempted jobs and concurrent new supervisor entrants
    # before replacing any existing terminal/heartbeat receipt.
    previous = job/'status.json'
    if previous.exists() and json.loads(previous.read_text()).get('state') != 'queued':
        raise FileExistsError('Job already attempted; preserve its original status')
    with (job/'supervisor-start.json').open('x') as claim:
        json.dump({'worker': process(os.getpid()), 'config_sha256': expected,
                   'claimed_utc': utc()}, claim, ensure_ascii=False, indent=2)
        claim.write('\n'); claim.flush(); os.fsync(claim.fileno())
    state = {'state': 'running', 'started_utc': utc(), 'worker': process(os.getpid()), 'child': None,
        'return_code': None, 'stop_signal': None, 'context': {}}
    requested = []
    def request_stop(signum, frame):
        if not requested: requested.append(signum)
    for signum in (signal.SIGTERM, signal.SIGINT): signal.signal(signum, request_stop)
    write_json(job/'status.json', state)
    child = None; lease = None
    try:
        config_path = job/'config.json'
        if digest(config_path) != expected: raise ValueError('Job config changed after launch')
        config = json.loads(config_path.read_text()); state['context'] = config['context']
        if digest(Path(__file__).resolve()) != config['controller_sha256']:
            raise ValueError('Supervisor source changed before worker startup')
        if digest(GUARD) != config['parent_death_guard_sha256']:
            raise ValueError('Parent-death guard source changed before worker startup')
        if config['context'].get('freeze'):
            import fcntl
            lease = (project_data_root(ROOT)/'tmp/capability-supervisor.lock').open('a')
            fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if digest(ROOT/config['context']['freeze']) != config['context']['freeze_sha256']:
                raise ValueError('Freeze descriptor changed after launch')
            command, context = prepare(config['context']['selection'])
            if command != config['command'] or context != config['context']:
                raise ValueError('Experiment selection changed after launch')
        env = dict(os.environ); env.update(config['environment'])
        with (job/'experiment.log').open('xb') as stream:
            guarded = [sys.executable, '-B', str(GUARD), '--job', str(job),
                '--config-sha256', expected, '--parent-pid', str(os.getpid())]
            child = subprocess.Popen(guarded, cwd=config['cwd'], env=env,
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            state['child'] = process(child.pid); write_json(job/'status.json', state)
            observe_protected_exec(child, job, config, expected, state, requested)
            last = 0.
            while child.poll() is None:
                if requested and state['stop_signal'] is None:
                    state['stop_signal'] = requested[0]; state['state'] = 'stopping'
                    signal_owned_child(child, state['child'], signal.SIGINT)
                if time.monotonic()-last >= 5:
                    state['heartbeat_utc'] = utc(); write_json(job/'status.json', state); last = time.monotonic()
                time.sleep(.2)
            state['return_code'] = child.wait()
        state['state'] = 'interrupted' if requested else 'completed' if state['return_code'] == 0 else 'failed'
    except Exception as error:
        state['state'] = 'failed'; state['error'] = repr(error)
        if child is not None and child.poll() is None:
            signal_owned_child(child, state['child'], signal.SIGKILL)
            state['return_code'] = child.wait()
    finally:
        if lease is not None: lease.close()
        state['ended_utc'] = utc(); write_json(job/'status.json', state)


def status(job):
    result = json.loads((job/'status.json').read_text())
    result['worker_verified_alive'] = matches(result.get('worker'))
    result['child_verified_alive'] = matches(result.get('child'))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--spec', type=Path); parser.add_argument('--job', type=Path)
    parser.add_argument('--worker', type=Path); parser.add_argument('--config-sha256')
    parser.add_argument('--status', type=Path)
    args = parser.parse_args()
    if args.worker: supervise(args.worker, args.config_sha256)
    elif args.status: print(json.dumps(status(args.status), ensure_ascii=False, indent=2))
    else:
        if args.spec is None or args.job is None: parser.error('--spec and --job required')
        command, context = prepare(json.loads(args.spec.read_text()))
        print(json.dumps(launch(command, args.job, context=context,
            environment={'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4'}), ensure_ascii=False))

"""Sequential owned CUDA providers with durable lifecycle and cleanup evidence."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from serve_local_model_eval import load_registry

ROOT = Path(__file__).resolve().parents[1]


def gpu_snapshot():
    return subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.free,utilization.gpu',
                                    '--format=csv,noheader,nounits'], text=True)


def gpu_processes():
    return subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
                                    '--format=csv,noheader,nounits'], text=True)


def has_pid(raw, pid):
    return any(line.split(',')[0].strip() == str(pid) for line in raw.splitlines())


def main(output, provider_python, stage='development', model_key=None, candidate_freeze=None,
         protocol=None, pair_protocol=None, candidate='v1', partition='development', backend='cuda',
         expected_freeze_sha256=None, registry_path=None, expected_registry_sha256=None):
    if backend not in ('cuda', 'cpu_explicit') or backend != 'cuda' and stage != 'capability_pair':
        raise ValueError('Explicit CPU requires separately registered capability pairs')
    if expected_freeze_sha256 is not None and stage != 'capability_pair':
        raise ValueError('Expected freeze identity currently applies to capability pairs only')
    registry, registry_sha256, registry_path = load_registry(registry_path, expected_sha256=expected_registry_sha256)
    default_registry = ROOT/'evals/interaction/cycle-02/model-scale-protocol.json'
    if stage != 'development' and registry_path != default_registry:
        raise ValueError('Registry overrides currently require development stage')
    selected_protocol = protocol if protocol is not None else (ROOT/'evals/interaction/cycle-15/native-output-protocol.json' if stage == 'development' else None)
    if selected_protocol is not None:
        declared = json.loads(selected_protocol.read_text()).get('models_registry')
        if not isinstance(declared, str) or (ROOT/declared).resolve() != registry_path:
            raise ValueError('Selected registry differs from selected protocol')
    specifications = [m for m in registry['models'] if model_key is None or m['model_id'] == model_key]
    if not specifications: raise ValueError('Unknown model key: '+str(model_key))
    frozen_sha = None
    if stage == 'capability_pair':
        if candidate_freeze is None or protocol is None or pair_protocol is None:
            raise ValueError('Capability pairs require source freeze and both explicit protocols')
        if json.loads(protocol.read_text()).get('provider_backend', 'cuda') != backend:
            raise ValueError('Selected backend differs from explicit frozen protocol')
        from evaluate_capability_pair import verify_freeze, validate_execution_contract, CLI_CANDIDATES
        if candidate not in CLI_CANDIDATES:
            raise ValueError('Select a registered capability candidate')
        candidate_id = CLI_CANDIDATES[candidate]
        frozen_sha = (sha256(candidate_freeze.read_bytes()).hexdigest() if expected_freeze_sha256 is None
                      else expected_freeze_sha256)
        def verify_capability_inputs():
            return verify_freeze(candidate_freeze, partition, candidate_id, expected_sha256=frozen_sha)
        frozen = verify_capability_inputs()
    elif candidate in ('source_capability_v2', 'source_capability_v3', 'source_capability_v4'):
        raise ValueError('Source capability candidates require capability_pair stage')
    if stage == 'capability_pair':
        for path in (protocol, pair_protocol):
            if str(path.resolve().relative_to(ROOT)) not in frozen['sha256']:
                raise ValueError('Selected capability protocol is not frozen')
        validate_execution_contract(frozen, json.loads(protocol.read_text()), backend)
    if stage == 'prospective':
        if candidate_freeze is None: raise ValueError('Prospective runs require --candidate-freeze')
        from evaluate_body_review_pair import verify_freeze
        frozen = verify_freeze(candidate_freeze)
        expected_candidate = 'lab_source_bound_body_v2' if candidate == 'source_bound_v2' else 'lab_explicit_body_v1'
        if frozen['candidate'] != expected_candidate: raise ValueError('Candidate differs from frozen selection')
        for path in [protocol, pair_protocol]:
            if path is not None and str(path.resolve().relative_to(ROOT)) not in frozen['sha256']:
                raise ValueError('Selected protocol is not frozen')
    paths = ['src/avatar/main.py', 'src/avatar/web.py', 'src/avatar/web_api.py',
             'src/avatar/brain/memory.py', 'src/avatar/brain/boundaries.py',
             'scripts/serve_local_model_eval.py', 'scripts/evaluate_native_output_audit.py',
             str(Path(__file__).resolve().relative_to(ROOT)),
             'evals/interaction/cycle-15/native-output-protocol.json', str(registry_path.relative_to(ROOT))]
    paths += [m['metadata'] for m in registry['models'] if m.get('metadata')]
    if stage == 'development' and protocol is not None:
        paths.append(str(protocol.resolve().relative_to(ROOT)))
    if stage == 'capability_pair':
        paths += [str(path.relative_to(ROOT)) for path in ROOT.glob('src/avatar/**/*.py')]
        paths += ['scripts/evaluate_capability_pair.py', 'scripts/evaluate_body_review_pair.py',
                  str(protocol.resolve().relative_to(ROOT)), str(pair_protocol.resolve().relative_to(ROOT))]
    if stage == 'prospective':
        paths += ['src/avatar/lab/body_review.py', 'src/avatar/lab/body_review_avatar.py',
                  'src/avatar/brain/tasks.py', 'scripts/evaluate_body_review_pair.py',
                  'evals/interaction/cycle-15/prospective-paired-protocol.json']
        paths += [str(p.resolve().relative_to(ROOT)) for p in [protocol, pair_protocol] if p is not None]
        if candidate == 'source_bound_v2':
            paths += ['src/avatar/lab/composition_sources.py', 'src/avatar/lab/source_bound_body_review.py']
    def fingerprint(): return {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    metadata_paths = {'qwen3-4b-q4_k_m': ROOT/'data/g2-cycle-02/gguf-metadata.json',
                      'qwen3-14b-q4_k_m': ROOT/'data/g2-cycle-02/qwen14b-gguf-metadata.json'}
    metadata_paths.update({m['model_id']: ROOT/m['metadata'] for m in registry['models'] if m.get('metadata')})
    if any(m['model_id'] not in metadata_paths for m in specifications):
        raise ValueError('Selected model has no declared metadata input')
    source_fingerprint = fingerprint()
    output.mkdir(parents=True, exist_ok=False)
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'createdUtc': datetime.now(timezone.utc).isoformat(), 'sourceSha256': source_fingerprint,
              'registry_path': str(registry_path.relative_to(ROOT)), 'registry_sha256': registry_sha256,
              'stage': stage, 'candidate': candidate, 'backend': backend, 'requested_models': [m['model_id'] for m in specifications],
              'candidateFreezeSha256': (frozen_sha if stage == 'capability_pair' else
                                       sha256(candidate_freeze.read_bytes()).hexdigest() if candidate_freeze else None),
              'models': [], 'completed': False, 'failure': None,
              'scope': 'Sequential pinned explicitly selected providers; no other process terminated; one provider at a time'}
    def save():
        (output/'lifecycle.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    # Resolve the CUDA runtime from the isolated provider environment, not a
    # task-specific absolute home. Preserve any caller GPU visibility mask.
    purelib = Path(subprocess.check_output([str(provider_python), '-c',
        'import sysconfig; print(sysconfig.get_path("purelib"))'], text=True).strip())
    libraries = [purelib/'nvidia/cuda_runtime/lib', ROOT.parent/'runtime/gpu-libs/nvidia/cublas/lib',
                 ROOT.parent/'runtime/gpu-libs/nvidia/cudnn/lib']
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = ':'.join([str(p) for p in libraries]+([env['LD_LIBRARY_PATH']] if env.get('LD_LIBRARY_PATH') else []))
    try:
        for specification in specifications:
            if stage == 'capability_pair': verify_capability_inputs()
            assert fingerprint() == report['sourceSha256'], 'Sources changed during model audit'
            key = specification['model_id']; folder = output/key; folder.mkdir()
            model_path = ROOT/'models'/key.replace('-q4_k_m', '-gguf')/specification['file']
            ready, trace = folder/'provider-ready.json', folder/'provider-trace.jsonl'
            command = [str(provider_python), str(ROOT/'scripts/serve_local_model_eval.py'), '--model', str(model_path),
                       '--model-key', key, '--metadata', str(metadata_paths[key]), '--ready', str(ready), '--trace', str(trace),
                       '--backend', backend, '--registry', str(registry_path),
                       '--expected-registry-sha256', registry_sha256]
            row = {'model_id': key, 'provider_command': command, 'provider_pid': None,
                   'gpu_before': gpu_snapshot(), 'processes_before': gpu_processes(),
                   'provider_ready': None, 'sampler_exit': None, 'provider_exit': None, 'cleanup_passed': False}
            report['models'].append(row); save(); process = None
            with (folder/'provider.log').open('x') as provider_log:
                try:
                    if stage == 'capability_pair': verify_capability_inputs()
                    process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=provider_log, stderr=subprocess.STDOUT)
                    row['provider_pid'] = process.pid; save()
                    while True:
                        if process.poll() is not None: raise RuntimeError(f'{key} exited before ready: {process.returncode}')
                        if ready.exists():
                            try: metadata = json.loads(ready.read_text())
                            except json.JSONDecodeError: metadata = None
                            if metadata is not None: break
                        time.sleep(.1)
                    assert metadata['pid'] == process.pid
                    if metadata.get('registry_sha256') != registry_sha256 or metadata.get('registry_path') != str(registry_path.relative_to(ROOT)):
                        raise ValueError('Provider runtime registry differs from pinned selection')
                    row['provider_ready'] = metadata; save()
                    print(key, 'ready backend', backend, 'GPU', metadata['chosen_gpu']['index'] if metadata['chosen_gpu'] else None,
                          'pid', process.pid, flush=True)
                    with (folder/'sampler.log').open('x') as sampler_log:
                        sampler = ('evaluate_capability_pair.py' if stage == 'capability_pair' else
                            'evaluate_body_review_pair.py' if stage == 'prospective' else 'evaluate_native_output_audit.py')
                        sampler_command = [sys.executable, str(ROOT/'scripts'/sampler),
                            '--provider', str(ready), '--output', str(folder/'sample')]
                        if stage == 'development' and protocol is not None:
                            sampler_command += ['--protocol', str(protocol)]
                        if stage == 'capability_pair':
                            sampler_command += ['--trace', str(trace), '--candidate-freeze', str(candidate_freeze),
                                '--protocol', str(protocol), '--pair-protocol', str(pair_protocol), '--partition', partition,
                                '--candidate', candidate_id, '--expected-freeze-sha256', frozen_sha]
                        if stage == 'prospective':
                            sampler_command += ['--trace', str(trace), '--candidate-freeze', str(candidate_freeze), '--candidate', candidate]
                            if protocol is not None: sampler_command += ['--protocol', str(protocol)]
                            if pair_protocol is not None: sampler_command += ['--pair-protocol', str(pair_protocol)]
                        row['sampler_command'] = sampler_command; save()
                        result = subprocess.run(sampler_command, cwd=ROOT,
                            stdout=sampler_log, stderr=subprocess.STDOUT)
                    row['sampler_exit'] = result.returncode; save()
                    if result.returncode: raise RuntimeError(f'{key} sampler failed; retained partial data')
                finally:
                    if process is not None:
                        if process.poll() is None: process.terminate()
                        row['provider_exit'] = process.wait()
                        # Resource cleanup timeout only; not an experiment time
                        # limit or a reason to restart an observation.
                        for _ in range(100):
                            raw = gpu_processes()
                            if not has_pid(raw, process.pid): break
                            time.sleep(.1)
                        row['processes_after'] = raw; row['gpu_after'] = gpu_snapshot()
                        row['cleanup_passed'] = row['provider_exit'] == 0 and not has_pid(raw, process.pid)
                        save()
            if not row['cleanup_passed']: raise RuntimeError(f'{key} owned resource cleanup did not pass')
            assert fingerprint() == report['sourceSha256'], 'Sources changed after model audit'
            if stage == 'capability_pair': verify_capability_inputs()
            print(key, 'sample complete, provider exit', row['provider_exit'], 'GPU pid absent', flush=True)
        report['completed'] = True
    except Exception as error:
        report['failure'] = repr(error)
        raise
    finally: save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider-python', type=Path, required=True)
    parser.add_argument('--stage', choices=['development', 'prospective', 'capability_pair'], default='development')
    parser.add_argument('--partition', choices=['development', 'prospective'], default='development')
    parser.add_argument('--model-key')
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--expected-registry-sha256')
    parser.add_argument('--candidate-freeze', type=Path)
    parser.add_argument('--protocol', type=Path)
    parser.add_argument('--pair-protocol', type=Path)
    parser.add_argument('--candidate', choices=['v1', 'source_bound_v2', 'source_capability_v2', 'source_capability_v3', 'source_capability_v4'], default='v1')
    parser.add_argument('--backend', choices=['cuda', 'cpu_explicit'], default='cuda')
    parser.add_argument('--expected-freeze-sha256')
    options = parser.parse_args()
    # Resolving a venv's executable symlink changes Python's environment prefix.
    # Make it absolute while preserving the requested venv entry point.
    main(options.output.resolve(), options.provider_python.expanduser().absolute(),
         options.stage, options.model_key, options.candidate_freeze, options.protocol, options.pair_protocol, options.candidate,
         options.partition, options.backend, expected_freeze_sha256=options.expected_freeze_sha256,
         registry_path=options.registry, expected_registry_sha256=options.expected_registry_sha256)

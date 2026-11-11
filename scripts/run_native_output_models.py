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

ROOT = Path(__file__).resolve().parents[1]


def gpu_snapshot():
    return subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.free,utilization.gpu',
                                    '--format=csv,noheader,nounits'], text=True)


def gpu_processes():
    return subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
                                    '--format=csv,noheader,nounits'], text=True)


def has_pid(raw, pid):
    return any(line.split(',')[0].strip() == str(pid) for line in raw.splitlines())


def main(output, provider_python):
    output.mkdir(parents=True, exist_ok=False)
    registry_path = ROOT/'evals/interaction/cycle-02/model-scale-protocol.json'
    registry = json.loads(registry_path.read_text())
    paths = ['src/avatar/main.py', 'src/avatar/web.py', 'src/avatar/web_api.py',
             'src/avatar/brain/memory.py', 'src/avatar/brain/boundaries.py',
             'scripts/serve_local_model_eval.py', 'scripts/evaluate_native_output_audit.py',
             str(Path(__file__).resolve().relative_to(ROOT)),
             'evals/interaction/cycle-15/native-output-protocol.json']
    def fingerprint(): return {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    metadata_paths = {'qwen3-4b-q4_k_m': ROOT/'data/g2-cycle-02/gguf-metadata.json',
                      'qwen3-14b-q4_k_m': ROOT/'data/g2-cycle-02/qwen14b-gguf-metadata.json'}
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'createdUtc': datetime.now(timezone.utc).isoformat(), 'sourceSha256': fingerprint(),
              'models': [], 'completed': False, 'failure': None,
              'scope': 'Sequential pinned real CUDA providers; no other process terminated; one provider at a time'}
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
        for specification in registry['models']:
            assert fingerprint() == report['sourceSha256'], 'Sources changed during model audit'
            key = specification['model_id']; folder = output/key; folder.mkdir()
            model_path = ROOT/'models'/key.replace('-q4_k_m', '-gguf')/specification['file']
            ready, trace = folder/'provider-ready.json', folder/'provider-trace.jsonl'
            command = [str(provider_python), str(ROOT/'scripts/serve_local_model_eval.py'), '--model', str(model_path),
                       '--model-key', key, '--metadata', str(metadata_paths[key]), '--ready', str(ready), '--trace', str(trace)]
            row = {'model_id': key, 'provider_command': command, 'provider_pid': None,
                   'gpu_before': gpu_snapshot(), 'processes_before': gpu_processes(),
                   'provider_ready': None, 'sampler_exit': None, 'provider_exit': None, 'cleanup_passed': False}
            report['models'].append(row); save(); process = None
            with (folder/'provider.log').open('x') as provider_log:
                try:
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
                    row['provider_ready'] = metadata; save()
                    print(key, 'ready GPU', metadata['chosen_gpu']['index'], 'pid', process.pid, flush=True)
                    with (folder/'sampler.log').open('x') as sampler_log:
                        result = subprocess.run([sys.executable, str(ROOT/'scripts/evaluate_native_output_audit.py'),
                            '--provider', str(ready), '--output', str(folder/'sample')], cwd=ROOT,
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
            print(key, 'sample complete, provider exit', row['provider_exit'], 'GPU pid absent', flush=True)
        report['completed'] = True
    except Exception as error:
        report['failure'] = repr(error)
        raise
    finally: save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--provider-python', type=Path, required=True); options = parser.parse_args()
    main(options.output.resolve(), options.provider_python.resolve())

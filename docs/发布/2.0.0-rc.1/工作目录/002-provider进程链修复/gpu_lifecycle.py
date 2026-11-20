"""Finite release engineering gate, not a model-quality experiment. See v1 protocol."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tarfile
import time
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent
ASSETS = Path('/data/Users/zrh/data/hhu-ai-avatar')
RAW = ASSETS/'artifacts/release/provider-lifecycle-v1'
REFERENCE = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
REGISTRY = ROOT/'evals/interaction/cycle-02/model-scale-protocol.json'
METADATA = ROOT/'evals/interaction/cycle-26/model-metadata-4b.json'
MODEL = ASSETS/'models/qwen3-4b-gguf/Qwen3-4B-Q4_K_M.gguf'
PYTHON = ASSETS/'envs/hhu-ai-avatar-llm/bin/python'
sys.path[:0] = [str(ROOT/'scripts/lab'), str(ROOT/'scripts'), str(ROOT/'src')]
import run_frozen_capability_job as jobs
from owned_provider import start_provider, finish_provider, immutable
from probe_structured_provider import environment
from avatar.gpu_resources import select_available_gpu


def read(path):
    return json.loads(Path(path).read_text())


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def runtime():
    reference = read(REFERENCE)
    code = ('import sys,json,importlib.metadata as m,llama_cpp; print(json.dumps({'
        '"prefix":sys.prefix,"package_root":str(__import__("pathlib").Path(llama_cpp.__file__).parent),'
        '"package_versions":{k:m.version(k) for k in '+repr(list(reference['package_versions']))+'}}))')
    actual = json.loads(subprocess.check_output([str(PYTHON), '-B', '-c', code],
        cwd=ROOT, env=environment(PYTHON), text=True))
    assert actual['prefix'] == reference['python_prefix']
    assert actual['package_root'] == reference['package_root']
    assert actual['package_versions'] == reference['package_versions']
    hashes = {name: digest(name) for name in reference['files_sha256']}
    assert len(hashes) == 54 and hashes == reference['files_sha256']
    actual.update(files_sha256=hashes, python_executable_sha256=digest(PYTHON),
        reference_sha256=digest(REFERENCE), model_sha256=digest(MODEL),
        model_bytes=MODEL.stat().st_size, provider_python=str(PYTHON))
    assert actual['model_sha256'] == read(REGISTRY)['models'][0]['sha256']
    return actual


def names():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = {n for n in tracked if n.startswith(('src/', 'scripts/')) and Path(ROOT/n).is_file()}
    selected.update(str(p.relative_to(ROOT)) for p in (Path(__file__), REFERENCE, REGISTRY, METADATA,
        HERE/'GPU生命周期门控协议-v1.md', HERE/'native-preflight-v1.json'))
    return sorted(selected)


def historical(ref, hashes):
    raw = subprocess.check_output(['git', 'archive', '--format=tar', ref, '--', *hashes], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
            for m in archive if m.isfile()}


def freeze(stage):
    if stage == 'manager_sigkill':
        prior = read(HERE/'normal-result-v1.json')
        assert prior['passed'] and prior['manager_actual_wait_code'] == 0
        # Prior stage receipts must be committed before the second launch.
        p = str((HERE/'normal-result-v1.json').relative_to(ROOT))
        assert subprocess.check_output(['git', 'show', 'HEAD:'+p], cwd=ROOT) == (ROOT/p).read_bytes()
    hashes = {n: digest(ROOT/n) for n in names()}
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert historical(ref, hashes) == hashes
    assert runtime() == read(HERE/'native-preflight-v1.json')
    immutable(HERE/(stage+'-freeze-v1.json'), dict(stage=stage, source_ref=ref,
        sha256=hashes, max_generate_calls=1, max_tokens=32, whole_stage_deadline=None,
        output=str(RAW/stage), scope='native GPU process lifecycle only'))


def verify(stage, expected):
    path = HERE/(stage+'-freeze-v1.json')
    assert digest(path) == expected
    proof = read(path)
    assert proof['stage'] == stage and proof['max_generate_calls'] == 1 and proof['max_tokens'] == 32
    assert set(proof['sha256']) == set(names())
    assert {n: digest(ROOT/n) for n in proof['sha256']} == proof['sha256']
    assert historical(proof['source_ref'], proof['sha256']) == proof['sha256']
    assert runtime() == read(HERE/'native-preflight-v1.json')
    return proof


def until(predicate, seconds, label):
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.05)
    raise RuntimeError(label+' engineering timeout')


def gpu_processes():
    raw = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,gpu_uuid,used_memory',
        '--format=csv,noheader,nounits'], text=True)
    return [dict(pid=int(a.strip()), uuid=b.strip(), used_mib=int(c.strip()))
        for a, b, c in (line.split(',') for line in raw.splitlines())]


def choose_gpu():
    raw = subprocess.check_output(['nvidia-smi', '--query-gpu=index,uuid,memory.free,utilization.gpu',
        '--format=csv,noheader,nounits'], text=True)
    rows = [dict(index=int(a.strip()), uuid=b.strip(), free_mib=int(c.strip()), utilization_percent=int(d.strip()))
        for a, b, c, d in (line.split(',') for line in raw.splitlines())]
    return rows, select_available_gpu(rows, required_free_mib=16384,
        visible_mask=os.environ.get('CUDA_VISIBLE_DEVICES'))


def manager(stage, expected):
    verify(stage, expected)
    folder = RAW/stage
    selection = read(folder/'selection.json')
    env = environment(PYTHON)
    env.update(CUDA_VISIBLE_DEVICES=selection['chosen']['uuid'], OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4')
    command = [str(PYTHON), '-B', str(ROOT/'scripts/serve_local_model_eval.py'),
        '--model', str(MODEL), '--model-key', 'qwen3-4b-q4_k_m', '--metadata', str(METADATA),
        '--ready', str(folder/'ready.json'), '--trace', str(folder/'trace.jsonl')]
    with (folder/'provider.log').open('x') as log:
        child, launch = start_provider(command, folder/'provider-edge', cwd=ROOT, env=env, stdout=log)
        try:
            immutable(folder/'manager-ready.json', dict(pid=os.getpid(),
                identity=jobs.process(os.getpid()), provider=launch))
            while not (folder/'stop-manager').exists() and child.poll() is None:
                time.sleep(.05)  # No whole-stage deadline; worker owns explicit stop.
        finally:
            if child.poll() is None:
                jobs.signal_owned_child(child, launch['provider_identity'], signal.SIGTERM)
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                jobs.signal_owned_child(child, launch['provider_identity'], signal.SIGKILL)
                child.wait()
            finish_provider(child, folder/'provider-edge')
        assert child.returncode == 0


def worker(stage, expected):
    proof = verify(stage, expected)
    folder = RAW/stage
    folder.mkdir(parents=True, exist_ok=False)
    inventory, chosen = choose_gpu()
    immutable(folder/'selection.json', dict(inventory=inventory, chosen=chosen))
    command = [sys.executable, '-B', str(Path(__file__)), 'manager', '--stage', stage, '--expected', expected]
    child = None
    provider = None
    result = dict(stage=stage, freeze_sha256=expected, started_utc=jobs.utc(), passed=False,
        manager_actual_wait_code=None, provider_actual_wait_code=None, whole_stage_deadline=None)
    start = time.monotonic()
    try:
        with (folder/'manager.log').open('x') as log:
            child, launch = start_provider(command, folder/'manager-edge', cwd=ROOT, env=dict(os.environ), stdout=log)
            def ready():
                if child.poll() is not None:
                    raise RuntimeError('Manager exited before model ready')
                path = folder/'ready.json'
                if not path.exists():
                    return None
                try:
                    return read(path)
                except json.JSONDecodeError:
                    return None
            metadata = until(ready, 180, 'model readiness')
            edge = read(folder/'provider-edge/launch-evidence.json')
            provider = edge['provider_identity']
            assert metadata['pid'] == provider['pid'] and jobs.matches(provider)
            assert metadata['parent_death_signal'] == 9 and metadata['backend'] == 'cuda'
            assert metadata['chosen_gpu']['uuid'] == chosen['uuid']
            assert metadata['model_sha256'] == read(HERE/'native-preflight-v1.json')['model_sha256']
            gpu_before = gpu_processes()
            assert any(r['pid'] == provider['pid'] and r['uuid'] == chosen['uuid'] and r['used_mib'] >= 1024 for r in gpu_before)
            immutable(folder/'loaded-evidence.json', dict(provider=provider, gpu_processes=gpu_before,
                manager_guard=read(folder/'manager-edge/parent-death-guard.json'),
                provider_guard=read(folder/'provider-edge/parent-death-guard.json')))
            payload = dict(model='qwen3-4b-q4_k_m', messages=[dict(role='user', content='请简短问好。')],
                max_tokens=32, temperature=0, stream=False)
            immutable(folder/'request.json', payload)
            req = Request(metadata['url']+'/chat/completions', data=json.dumps(payload, ensure_ascii=False).encode(),
                headers={'Content-Type': 'application/json', 'Authorization': 'Bearer local-eval-only'})
            with build_opener(ProxyHandler({})).open(req, timeout=180) as response:
                body = response.read()
                assert response.status == 200
            (folder/'response.json').write_bytes(body)
            assert json.loads(body)['choices'][0]['message']['content']
            traces = until(lambda: (folder/'trace.jsonl').read_text().splitlines(), 10, 'trace flush')
            assert len(traces) == 1 and json.loads(traces[0])['outcome'] == 'completed'
            if stage == 'normal':
                (folder/'stop-manager').touch(exist_ok=False)
            else:
                assert stage == 'manager_sigkill' and jobs.matches(launch['provider_identity'])
                os.kill(child.pid, signal.SIGKILL)
            code = child.wait(timeout=30)
            finish_provider(child, folder/'manager-edge')
            result['manager_actual_wait_code'] = code
            assert code == (0 if stage == 'normal' else -9)
            until(lambda: not jobs.matches(provider) and not any(r['pid'] == provider['pid'] for r in gpu_processes()),
                30, 'provider PID and GPU retirement')
            if stage == 'normal':
                result['provider_actual_wait_code'] = read(folder/'provider-edge/terminal.json')['return_code']
                assert result['provider_actual_wait_code'] == 0
            else:
                assert not (folder/'provider-edge/terminal.json').exists()
            assert {n: digest(ROOT/n) for n in proof['sha256']} == proof['sha256']
            result.update(passed=True, actual_generate_calls=len(traces), provider_pid_retired=True,
                provider_gpu_retired=True, chosen_gpu=chosen, gpu_after=gpu_processes(),
                missing_original_provider_wait_is_unknown=(stage == 'manager_sigkill'))
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        if child is not None and child.poll() is None:
            jobs.signal_owned_child(child, jobs.process(child.pid), signal.SIGKILL)
            result['manager_actual_wait_code'] = child.wait()
        if provider and jobs.matches(provider):
            os.kill(provider['pid'], signal.SIGKILL)
        result.update(ended_utc=jobs.utc(), elapsed_seconds=time.monotonic()-start)
        immutable(folder/'result.json', result)


def collect(stage):
    folder = RAW/stage
    assert not jobs.matches(jobs.status(RAW/(stage+'-job')).get('worker'))
    result = read(folder/'result.json')
    assert jobs.status(RAW/(stage+'-job'))['return_code'] == 0 and result['passed']
    # Keep large raw logs in the central asset tree and bind every byte.
    hashes = {str(p.relative_to(RAW)): digest(p) for p in sorted(RAW.rglob('*'))
        if p.is_file() and (p.is_relative_to(folder) or p.is_relative_to(RAW/(stage+'-job')))}
    immutable(HERE/(stage+'-raw-manifest-v1.json'), dict(root=str(RAW), sha256=hashes))
    immutable(HERE/(stage+'-result-v1.json'), result)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['preflight', 'freeze', 'launch', 'worker', 'manager', 'collect'])
    parser.add_argument('--stage', choices=['normal', 'manager_sigkill'], default='normal')
    parser.add_argument('--expected')
    args = parser.parse_args()
    if args.action == 'preflight':
        immutable(HERE/'native-preflight-v1.json', runtime())
    elif args.action == 'freeze':
        freeze(args.stage)
    elif args.action == 'launch':
        verify(args.stage, args.expected)
        print(jobs.launch([sys.executable, '-B', str(Path(__file__)), 'worker', '--stage', args.stage,
            '--expected', args.expected], RAW/(args.stage+'-job'),
            context={'release_lifecycle': args.stage, 'freeze_sha256': args.expected},
            environment={'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4'}))
    elif args.action == 'worker':
        worker(args.stage, args.expected)
    elif args.action == 'manager':
        manager(args.stage, args.expected)
    else:
        collect(args.stage)


if __name__ == '__main__':
    main()

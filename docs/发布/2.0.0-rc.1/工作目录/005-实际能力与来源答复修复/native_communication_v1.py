"""Fixed release regression; content approval requires a separate source/span review."""
import argparse
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'002-provider进程链修复'
RAW = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/native-communication-v1')
spec = importlib.util.spec_from_file_location('release_lifecycle_util', OLD/'gpu_lifecycle.py')
util = importlib.util.module_from_spec(spec)
spec.loader.exec_module(util)
from owned_provider import start_provider, finish_provider, immutable
import run_frozen_capability_job as jobs
from probe_structured_provider import environment
from avatar.main import Avatar
from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken

read, digest = util.read, util.digest


def runtime():
    import openai
    import numpy
    data = util.runtime()
    data['client'] = dict(python=sys.executable,
        versions={k: importlib.metadata.version(k) for k in ('openai', 'httpx', 'numpy')},
        module_sha256={str(Path(m.__file__).resolve()): digest(Path(m.__file__)) for m in (openai, numpy)})
    return data


def names():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = {n for n in tracked if n.startswith(('src/', 'scripts/', 'tests/', 'evals/'))}
    selected.update(str(p.relative_to(ROOT)) for p in (Path(__file__), OLD/'gpu_lifecycle.py',
        util.REFERENCE, util.REGISTRY, util.METADATA, HERE/'native-cases-v1.json',
        HERE/'原生模型通信门控协议-v1.md', HERE/'native-preflight-v1.json',
        HERE/'python-capability-v2-binding.json', HERE/'python-capability-v2.log'))
    return sorted(selected)


def freeze():
    regression = read(HERE/'python-capability-v2-binding.json')
    assert regression['actual_returncode'] == 0 and regression['source_unchanged']
    assert {n: digest(ROOT/n) for n in regression['source_sha256']} == regression['source_sha256']
    assert digest(HERE/'python-capability-v2.log') == regression['log_sha256']
    assert runtime() == read(HERE/'native-preflight-v1.json')
    hashes = {n: digest(ROOT/n) for n in names()}
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert util.historical(ref, hashes) == hashes
    cases = read(HERE/'native-cases-v1.json')
    assert len(cases['cases']) == 18 and cases['turns_per_arm'] == 31 and cases['max_generate_calls'] == 124
    immutable(HERE/'native-freeze-v1.json', dict(source_ref=ref, sha256=hashes,
        max_generate_calls=124, trial_count=36, max_tokens=512, whole_stage_deadline=None,
        scope='opt-in communication contract; separate nonhuman source/span review required'))


def verify(expected):
    path = HERE/'native-freeze-v1.json'
    assert digest(path) == expected
    proof = read(path)
    assert set(proof['sha256']) == set(names())
    assert {n: digest(ROOT/n) for n in proof['sha256']} == proof['sha256']
    assert util.historical(proof['source_ref'], proof['sha256']) == proof['sha256']
    assert runtime() == read(HERE/'native-preflight-v1.json')
    return proof


class RecordedLLM(LLMEngine):
    def __init__(self, url, folder, budget):
        super().__init__(base_url=url, api_key='local-eval-only', model='qwen3-4b-q4_k_m',
            timeout=180, max_retries=0)
        self.folder, self.budget, self.calls, self.errors = folder, budget, [], []

    def stream_chat(self, messages, **kwargs):
        self.budget[0] += 1
        assert self.budget[0] <= 124, 'fixed generate budget exceeded'
        number = self.budget[0]
        phase = 'analysis' if kwargs.get('response_format') else 'generation'
        immutable(self.folder/f'call-{number:03d}-request.json', dict(
            messages=messages, phase=phase, max_tokens=kwargs.get('max_tokens', 512),
            requested_temperature=kwargs.get('temperature', .8),
            response_format=kwargs.get('response_format')))
        callback = kwargs.pop('on_delta', None)
        deltas, started = [], time.monotonic()
        result = dict(number=number, phase=phase, error=None)
        def delta(text):
            deltas.append(dict(text=text, seconds=time.monotonic()-started))
            if callback:
                callback(text)
        try:
            result['response'] = super().stream_chat(messages, on_delta=delta, **kwargs)
            return result['response']
        except BaseException as error:
            result['error'] = repr(error)
            self.errors.append(result['error'])
            raise
        finally:
            result.update(deltas=deltas, seconds=time.monotonic()-started)
            immutable(self.folder/f'call-{number:03d}-response.json', result)
            self.calls.append(number)


def trials(url, folder, result):
    budget = [0]
    for case in read(HERE/'native-cases-v1.json')['cases']:
        for arm in ('baseline', 'candidate'):
            trial = folder/'trials'/(case['id']+'-'+arm)
            trial.mkdir(parents=True, exist_ok=False)
            engine = RecordedLLM(url, trial, budget)
            bot = Avatar(db_path=str(trial/'memory.db'), llm=engine,
                session_id=case['id']+'-'+arm, capability_contract_enabled=arm == 'candidate')
            try:
                for index, text in enumerate(case['turns'], 1):
                    before, visible = len(engine.calls), []
                    started = time.monotonic()
                    answer = bot.respond(text, cancel=CancellationToken(), on_delta=visible.append)
                    message_id = answer['conversation']['assistant_message_id']
                    sql = bot.memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
                        (message_id,)).fetchone()['content']
                    tables = ('memory_messages', 'memory_reminders', 'memory_action_receipts',
                        'memory_response_context', 'memory_fragments')
                    state = {name: [dict(row) for row in bot.memory._conn.execute('SELECT * FROM '+name)]
                        for name in tables}
                    row = dict(case_id=case['id'], arm=arm, turn=index, user_text=text,
                        result=answer, visible=visible, sql_assistant=sql, sql=state,
                        native_call_numbers=engine.calls[before:], elapsed_seconds=time.monotonic()-started)
                    immutable(trial/f'turn-{index:02d}.json', row)
                    assert ''.join(visible) == answer['reply'] == sql, 'visible/final/SQL mismatch'
                    assert not engine.errors, 'actual native request failed; no fallback-only approval'
                    assert not answer.get('tool_calls'), 'tools were not authorized by this protocol'
                    expected = 1 if case['id'] == 'N12' else 0
                    assert len(state['memory_reminders']) == expected, 'unexpected local action'
                    assert len(state['memory_action_receipts']) == expected, 'unexpected action receipt'
                    result['completed_turns'] += 1
                assert bot.memory._conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                result['completed_trials'] += 1
            finally:
                bot.memory.close()
                engine.close()
    result['actual_client_native_calls'] = budget[0]


def worker(expected):
    proof = verify(expected)
    RAW.mkdir(parents=True, exist_ok=False)
    inventory, chosen = util.choose_gpu()
    immutable(RAW/'selection.json', dict(inventory=inventory, chosen=chosen))
    env = environment(util.PYTHON)
    env.update(CUDA_VISIBLE_DEVICES=chosen['uuid'], OMP_NUM_THREADS='4', OPENBLAS_NUM_THREADS='4')
    command = [str(util.PYTHON), '-B', str(ROOT/'scripts/serve_local_model_eval.py'),
        '--model', str(util.MODEL), '--model-key', 'qwen3-4b-q4_k_m', '--metadata', str(util.METADATA),
        '--ready', str(RAW/'ready.json'), '--trace', str(RAW/'trace.jsonl')]
    child, identity = None, None
    result = dict(freeze_sha256=expected, engineering_passed=False, content_review_approved=False,
        completed_trials=0, completed_turns=0, actual_provider_wait_code=None,
        whole_stage_deadline=None, started_utc=jobs.utc())
    started = time.monotonic()
    try:
        with (RAW/'provider.log').open('x') as log:
            child, launch = start_provider(command, RAW/'provider-edge', cwd=ROOT, env=env, stdout=log)
            identity = launch['provider_identity']
            def ready():
                assert child.poll() is None, 'provider exited before readiness'
                path = RAW/'ready.json'
                if not path.exists():
                    return None
                try:
                    return read(path)
                except json.JSONDecodeError:
                    return None
            metadata = util.until(ready, 180, 'model readiness')
            assert metadata['pid'] == identity['pid'] and jobs.matches(identity)
            assert metadata['parent_death_signal'] == 9 and metadata['backend'] == 'cuda'
            assert metadata['chosen_gpu']['uuid'] == chosen['uuid']
            assert metadata['model_sha256'] == read(HERE/'native-preflight-v1.json')['model_sha256']
            gpu = util.gpu_processes()
            assert any(r['pid'] == child.pid and r['uuid'] == chosen['uuid'] and r['used_mib'] >= 1024 for r in gpu)
            immutable(RAW/'loaded-evidence.json', dict(provider=identity, gpu_processes=gpu))
            trials(metadata['url'], RAW, result)
            traces = [json.loads(line) for line in (RAW/'trace.jsonl').read_text().splitlines()]
            assert len(traces) == result['actual_client_native_calls'] <= 124
            assert all(row['outcome'] == 'completed' for row in traces)
            result['actual_generate_calls'] = len(traces)
            assert result['completed_trials'] == 36 and result['completed_turns'] == 62
            assert {n: digest(ROOT/n) for n in proof['sha256']} == proof['sha256']
            result['source_unchanged'] = True
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        if child is not None:
            if child.poll() is None:
                jobs.signal_owned_child(child, identity, signal.SIGTERM)
            try:
                result['actual_provider_wait_code'] = child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                jobs.signal_owned_child(child, identity, signal.SIGKILL)
                result['actual_provider_wait_code'] = child.wait()
            result['terminal'] = finish_provider(child, RAW/'provider-edge')
            util.until(lambda: not jobs.matches(identity) and not any(
                r['pid'] == identity['pid'] for r in util.gpu_processes()), 30, 'provider retirement')
            result['provider_pid_and_gpu_retired'] = True
        result['engineering_passed'] = bool('error' not in result and result.get('source_unchanged')
            and result['actual_provider_wait_code'] == 0 and result.get('provider_pid_and_gpu_retired'))
        result.update(ended_utc=jobs.utc(), elapsed_seconds=time.monotonic()-started)
        immutable(RAW/'result.json', result)
    assert result['engineering_passed']


def collect():
    status = jobs.status(RAW.with_name(RAW.name+'-job'))
    assert not jobs.matches(status.get('worker'))
    result = read(RAW/'result.json')
    result['actual_worker_wait_code'] = status.get('return_code')
    immutable(HERE/'native-result-v1.json', result)
    hashes = {str(p.relative_to(RAW.parent)): digest(p) for root in (RAW, RAW.with_name(RAW.name+'-job'))
        for p in sorted(root.rglob('*')) if p.is_file()}
    immutable(HERE/'native-raw-manifest-v1.json', dict(root=str(RAW.parent), sha256=hashes))
    assert status['return_code'] == 0 and result['engineering_passed']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['preflight', 'freeze', 'launch', 'worker', 'collect'])
    parser.add_argument('--expected')
    args = parser.parse_args()
    if args.action == 'preflight':
        immutable(HERE/'native-preflight-v1.json', runtime())
    elif args.action == 'freeze':
        freeze()
    elif args.action == 'launch':
        verify(args.expected)
        print(jobs.launch([sys.executable, '-B', str(Path(__file__)), 'worker', '--expected', args.expected],
            RAW.with_name(RAW.name+'-job'), context={'release_communication': 1, 'freeze_sha256': args.expected},
            environment={'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4'}))
    elif args.action == 'worker':
        worker(args.expected)
    else:
        collect()


if __name__ == '__main__':
    main()

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
RAW = Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/native-communication-v11')
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
        versions={k: importlib.metadata.version(k) for k in ('openai', 'httpx', 'httpx2', 'httpcore2', 'numpy')},
        module_sha256={str(Path(m.__file__).resolve()): digest(Path(m.__file__)) for m in (openai, numpy)})
    import httpx2, httpcore2
    data['client']['active_transport_sha256'] = {str(p): digest(p) for m in (httpx2,httpcore2)
        for p in sorted(Path(m.__file__).resolve().parent.rglob('*')) if p.is_file() and p.suffix in ('.py','.so')}
    return data


def names():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = {n for n in tracked if n.startswith(('src/', 'scripts/', 'tests/', 'evals/', 'frontend/', 'training/')) or n=='pyproject.toml' or n.startswith('requirements') and n.endswith('.txt') or '/' not in n and n.endswith('.py')}
    selected.update(str(p.relative_to(ROOT)) for p in (Path(__file__), OLD/'gpu_lifecycle.py',
        util.REFERENCE, util.REGISTRY, util.METADATA, HERE/'native-cases-v11.json',
        HERE/'原生写作与来源门控协议-v11.md', HERE/'native-preflight-v11.json',
        HERE/'native_driver_controls_v11.py', HERE/'native-driver-controls-v11.json',
        HERE/'native-driver-controls-raw-v11.json',
        HERE/'python-writing-v18-binding.json', HERE/'python-writing-v18.log', HERE/'run_current_python.py'))
    return sorted(selected)


def freeze():
    controls = read(HERE/'native-driver-controls-v11.json')
    assert controls['passed'] and controls['actual_native_generate_calls'] == 0
    assert {n: digest(ROOT/n) for n in controls['source_sha256']} == controls['source_sha256']
    regression = read(HERE/'python-writing-v18-binding.json')
    assert regression['actual_returncode'] == 0 and regression['source_unchanged']
    assert {n: digest(ROOT/n) for n in regression['source_sha256']} == regression['source_sha256']
    assert digest(HERE/'python-writing-v18.log') == regression['log_sha256']
    assert digest(HERE/'run_current_python.py') == regression['driver_sha256']
    assert runtime() == read(HERE/'native-preflight-v11.json')
    hashes = {n: digest(ROOT/n) for n in names()}
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert util.historical(ref, hashes) == hashes
    cases = read(HERE/'native-cases-v11.json')
    assert len(cases['cases']) == 53 and cases['turns_per_arm'] == 98 and cases['max_generate_calls'] == 600
    immutable(HERE/'native-freeze-v11.json', dict(source_ref=ref, sha256=hashes,
        max_generate_calls=600, trial_count=106, max_tokens=512, whole_stage_deadline=None,
        scope='explicit standard release configuration in actual SDK; separate nonhuman source/span review required'))


def verify(expected):
    path = HERE/'native-freeze-v11.json'
    assert digest(path) == expected
    proof = read(path)
    assert set(proof['sha256']) == set(names())
    assert {n: digest(ROOT/n) for n in proof['sha256']} == proof['sha256']
    assert util.historical(proof['source_ref'], proof['sha256']) == proof['sha256']
    assert runtime() == read(HERE/'native-preflight-v11.json')
    return proof


class NativeProtocolStop(BaseException):
    """An invalid native result must escape product fallback and stop the trial."""


def canonical(value):
    from hashlib import sha256
    return None if value is None else sha256(json.dumps(value, ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def validate_native_record(row, messages, response, form):
    schema = form.get('json_schema', {}).get('schema') if isinstance(form, dict) else None
    if not (isinstance(row, dict) and row.get('outcome') == 'completed' and row.get('finish_reason') == 'stop'
            and row.get('messages') == messages and row.get('response') == response
            and row.get('response_format') == form
            and row.get('response_format_sha256') == canonical(form)
            and row.get('response_schema_sha256') == canonical(schema)
            and row.get('grammar_enabled') is (form is not None) and row.get('stream') is True):
        raise NativeProtocolStop('native truncation, incomplete result or logical request/output mismatch')


def native_record(number, messages, response, form):
    def flushed():
        path = RAW/'trace.jsonl'
        if not path.exists(): return None
        lines = path.read_bytes().splitlines(keepends=True)
        if len(lines) < number: return None
        if len(lines) != number:
            raise NativeProtocolStop('unexpected extra native requests')
        try: row = json.loads(lines[-1])
        except json.JSONDecodeError: return None
        return row, lines
    try:
        row, lines = util.until(flushed, 10, 'per-request native trace flush')
    except Exception as error:
        raise NativeProtocolStop('native trace unavailable: '+repr(error)) from error
    validate_native_record(row, messages, response, form)
    from hashlib import sha256
    return dict(trace_source='actual_cuda_provider', native_id=row['id'], finish_reason=row['finish_reason'],
        trace_byte_offset=sum(len(line) for line in lines[:-1]), trace_line_sha256=sha256(lines[-1]).hexdigest(),
        response_format_sha256=row['response_format_sha256'], response_schema_sha256=row['response_schema_sha256'],
        provider_recorded_wire_sha256=row['request_body_sha256'])


class RecordedLLM(LLMEngine):
    def __init__(self, url, folder, budget):
        super().__init__(base_url=url, api_key='local-eval-only', model='qwen3-4b-q4_k_m',
            timeout=180, max_retries=0)
        self.folder, self.budget, self.calls, self.errors = folder, budget, [], []

    def chat_analysis_stream(self, messages, **kwargs):
        self._call_purpose = 'cognition'
        try:
            return super().chat_analysis_stream(messages, **kwargs)
        finally:
            self._call_purpose = 'generation'

    def stream_chat(self, messages, **kwargs):
        if kwargs.get('cancel') is not None:
            kwargs['cancel'].checkpoint()
        self.budget[0] += 1
        assert self.budget[0] <= 600, 'fixed generate budget exceeded'
        number = self.budget[0]
        phase = getattr(self, '_call_purpose', 'generation')
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
            result['native_proof'] = native_record(number, messages, result['response'], kwargs.get('response_format'))
            return result['response']
        except BaseException as error:
            result['error'] = repr(error)
            self.errors.append(result['error'])
            raise
        finally:
            result.update(deltas=deltas, seconds=time.monotonic()-started)
            immutable(self.folder/f'call-{number:03d}-response.json', result)
            self.calls.append(number)


def seed_case(bot,case):
    from datetime import datetime
    with bot.memory.transaction():
        for key,value in case.get('initial_profile',{}).items():
            bot.memory.remember_user(key,value)
        seed=case.get('seed')
        if seed and seed['status_at_query']!='missing':
            bot.memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,created_at,status) VALUES (?,?,?,?,?)',
                (seed['record_id'],seed['title'],datetime.fromisoformat(seed['due_date']).timestamp(),time.time(),seed['status_at_query']))
            if seed['client_ack_recorded']:
                bot.memory._conn.execute('INSERT INTO memory_reminder_deliveries(reminder_id,created_at,acknowledged_at) VALUES (?,?,?)',
                    (seed['record_id'],time.time(),time.time()))


def actor_case(bot,case,trial):
    from contextlib import closing
    from datetime import datetime
    import sqlite3
    seed=case['seed'];action=case['independent_actor_after_query']
    with closing(sqlite3.connect(bot.memory.db_path)) as conn:
        if action=='create_record':
            conn.execute('INSERT INTO memory_reminders(id,title,due_at,created_at,status) VALUES (?,?,?,?,?)',
                (seed['record_id'],seed['title'],datetime.fromisoformat(seed['due_date']).timestamp(),time.time(),'active'))
        else:conn.execute('UPDATE memory_reminders SET status=? WHERE id=?',(action.removeprefix('set_'),seed['record_id']))
        conn.commit()
    immutable(trial/'independent-actor.json',dict(action=action,after_first_query=True,
        actual_rows=[dict(r) for r in bot.memory._conn.execute('SELECT * FROM memory_reminders')]))


def trials(url, folder, result):
    budget = [0]
    for case in read(HERE/'native-cases-v11.json')['cases']:
        for arm in ('baseline', 'candidate'):
            trial = folder/'trials'/(case['id']+'-'+arm)
            trial.mkdir(parents=True, exist_ok=False)
            engine = RecordedLLM(url, trial, budget)
            bot = Avatar(db_path=str(trial/'memory.db'), llm=engine,
                session_id=case['id']+'-'+arm, capability_contract_enabled=arm == 'candidate', role_state_enabled=arm == 'candidate')
            seed_case(bot,case)
            try:
                for index, text in enumerate(case['turns'], 1):
                    before, visible = len(engine.calls), []
                    started = time.monotonic()
                    answer = bot.respond(text, cancel=CancellationToken(), on_delta=visible.append,
                        mode='reminder_query' if case.get('seed') and index<=case['query_turns'] else 'chat')
                    from avatar.brain.conversations import ConversationStore
                    ConversationStore(bot.memory).record_result(answer)
                    message_id = answer['conversation']['assistant_message_id']
                    sql = bot.memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
                        (message_id,)).fetchone()['content']
                    tables = ('memory_messages', 'memory_reminders', 'memory_action_receipts',
                        'memory_response_context', 'memory_fragments', 'memory_chat_results', 'memory_reminder_deliveries')
                    state = {name: [dict(row) for row in bot.memory._conn.execute('SELECT * FROM '+name)]
                        for name in tables}
                    # Rule replies are published in the final result. Model
                    # generation must additionally supply matching deltas.
                    streamed = ''.join(visible)
                    delivery = 'generated_deltas_and_final' if visible else 'final_result_only'
                    generated = answer['generation_mode'] in {'llm', 'llm_capability_guarded', 'llm_format_guarded', 'llm_writing_repaired', 'reviewed_response'}
                    row = dict(case_id=case['id'], arm=arm, turn=index, user_text=text,
                        result=answer, visible=visible, sql_assistant=sql, sql=state,
                        delivery=delivery,
                        native_call_numbers=engine.calls[before:], elapsed_seconds=time.monotonic()-started)
                    immutable(trial/f'turn-{index:02d}.json', row)
                    assert answer['reply'] == sql, 'final/SQL mismatch'
                    assert (not visible or streamed == answer['reply']), 'generated delta/final mismatch'
                    assert not generated or streamed == answer['reply'], 'generated output missing deltas'
                    assert not engine.errors, 'actual native request failed; no fallback-only approval'
                    assert not answer.get('tool_calls'), 'tools were not authorized by this protocol'
                    expected = (0 if index==1 and case['seed']['status_at_query']=='missing' else 1) if case.get('seed') else (1 if case['id']=='N12' else 0)
                    assert len(state['memory_reminders']) == expected, 'unexpected local action'
                    assert len(state['memory_action_receipts']) == (1 if case['id']=='N12' else 0), 'unexpected action receipt'
                    result['completed_turns'] += 1
                    if case.get('seed') and index==1:
                        actor_case(bot,case,trial)
                assert bot.memory._conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
                result['completed_trials'] += 1
            finally:
                bot.memory.close()
                engine.close()
    result['actual_client_native_calls'] = budget[0]


def wait_for_gpu(expected):
    # Waiting is before any model initialization/inference. Three consecutive
    # snapshots avoid treating a single utilization dip as sustained headroom.
    stable, previous = 0, None
    with (RAW/'admission.jsonl').open('x') as log:
        while True:
            raw = subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,utilization.gpu',
                '--format=csv,noheader,nounits'],text=True)
            inventory=[dict(index=int(a.strip()),uuid=b.strip(),free_mib=int(c.strip()),utilization_percent=int(d.strip()))
                for a,b,c,d in (line.split(',') for line in raw.splitlines())]
            try:
                chosen=util.select_available_gpu(inventory,required_free_mib=16384,
                    visible_mask=os.environ.get('CUDA_VISIBLE_DEVICES'))
            except RuntimeError:
                chosen=None
            stable=stable+1 if chosen is not None and chosen['uuid']==previous else (1 if chosen else 0)
            previous=chosen['uuid'] if chosen else None
            log.write(json.dumps(dict(observed_utc=jobs.utc(),inventory=inventory,chosen=chosen,
                consecutive_headroom_observations=stable,native_generate_calls=0),ensure_ascii=False)+'\n');log.flush()
            if stable>=3:
                verify(expected)
                return inventory,chosen
            time.sleep(5)


def worker(expected):
    proof = verify(expected)
    RAW.mkdir(parents=True, exist_ok=False)
    try:
        inventory, chosen = wait_for_gpu(expected)
    except BaseException as error:
        immutable(RAW/'admission-failure.json', dict(error=repr(error), actual_native_generate_calls=0,
            model_process_started=False, started_utc=jobs.utc()))
        raise
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
            assert metadata['model_sha256'] == read(HERE/'native-preflight-v11.json')['model_sha256']
            gpu = util.gpu_processes()
            assert any(r['pid'] == child.pid and r['uuid'] == chosen['uuid'] and r['used_mib'] >= 1024 for r in gpu)
            immutable(RAW/'loaded-evidence.json', dict(provider=identity, gpu_processes=gpu))
            trials(metadata['url'], RAW, result)
            traces = [json.loads(line) for line in (RAW/'trace.jsonl').read_text().splitlines()]
            assert len(traces) == result['actual_client_native_calls'] <= 600
            assert all(row['outcome'] == 'completed' and row['finish_reason'] == 'stop' for row in traces)
            result['actual_generate_calls'] = len(traces)
            assert result['completed_trials'] == 106 and result['completed_turns'] == 196
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
    if (RAW/'result.json').exists():
        result = read(RAW/'result.json')
    else:
        result = dict(engineering_passed=False,content_review_approved=False,
            incomplete=True,admission_failure=read(RAW/'admission-failure.json') if (RAW/'admission-failure.json').exists() else None,
            actual_client_native_calls=None,error='worker ended before complete finalization; do not infer model calls or quality')
    result['actual_worker_wait_code'] = status.get('return_code')
    immutable(HERE/'native-result-v11.json', result)
    hashes = {str(p.relative_to(RAW.parent)): digest(p) for root in (RAW, RAW.with_name(RAW.name+'-job'))
        for p in sorted(root.rglob('*')) if p.is_file()}
    immutable(HERE/'native-raw-manifest-v11.json', dict(root=str(RAW.parent), sha256=hashes))
    assert status['return_code'] == 0 and result['engineering_passed']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['preflight', 'freeze', 'launch', 'worker', 'collect'])
    parser.add_argument('--expected')
    args = parser.parse_args()
    if args.action == 'preflight':
        immutable(HERE/'native-preflight-v11.json', runtime())
    elif args.action == 'freeze':
        freeze()
    elif args.action == 'launch':
        verify(args.expected)
        print(jobs.launch([sys.executable, '-B', str(Path(__file__)), 'worker', '--expected', args.expected],
            RAW.with_name(RAW.name+'-job'), context={'release_communication': 10, 'freeze_sha256': args.expected},
            environment={'OMP_NUM_THREADS': '4', 'OPENBLAS_NUM_THREADS': '4'}))
    elif args.action == 'worker':
        worker(args.expected)
    else:
        collect()


if __name__ == '__main__':
    main()

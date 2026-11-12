"""C38 paired actual HTTP/SSE arms; original draft, typed plan and final separate."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from functools import partial
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
from urllib.request import Request, ProxyHandler, build_opener
import uuid

from native_common import ROOT, BASE, PROTOCOL, WORK, digest, read, verify_source
import avatar.main as main_module
from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.lab.typed_capability_gate import TypedCapabilityGateAvatar, PLAN_RESPONSE_FORMAT
from avatar.paths import project_data_root
from avatar.web import create_server
from evaluate_native_output_audit import events, validate_provider_identity, runtime_source_identity


def collect_arm(case, candidate, opener, wire_path, verify, output, repetition):
    row = {'id': case['id'], 'arm': 'candidate' if candidate else 'baseline', 'turns': [],
           'completed': False, 'failure': None, 'server_closed': False}
    original, original_engine = main_module.Avatar, main_module.LLMEngine
    server = thread = None
    temporary = tempfile.TemporaryDirectory(prefix='c38-pair-', dir=project_data_root(ROOT)/'tmp')
    try:
        folder = temporary.name
        path = str(Path(folder)/'owned.db')
        if candidate:
            main_module.Avatar = TypedCapabilityGateAvatar
        main_module.LLMEngine = partial(LLMEngine, timeout=180)
        server = create_server(path, port=0, legacy_writes=False, identity_grounding=False,
            profile_grounding=False, task_delivery_check=False, literal_composition=False)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}/api/v1'
        def query(route, payload=None):
            req = Request(base+route, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                headers={'X-Avatar-Token': server.token, 'Content-Type': 'application/json'})
            with opener.open(req, timeout=180) as response:
                return json.load(response)['data']
        for i, text in enumerate(case['turns']):
            verify()
            start_count = len(wire_path.read_text().splitlines()) if wire_path.exists() else 0
            tick = time.perf_counter()
            job = query('/turns', {'request_id': 'c38_pair_'+uuid.uuid4().hex, 'text': text, 'use_web': False})
            request = Request(base+'/turns/'+job['job_id']+'/events', headers={'X-Avatar-Token': server.token})
            with opener.open(request, timeout=180) as response:
                kind, result, received, raw = events(response, tick)
            end_count = len(wire_path.read_text().splitlines())
            turn = {'input': text, 'terminal': kind, 'result': result, 'events': received, 'raw_sse': raw,
                'visible': ''.join(e['data']['text'] for e in received if e['event'] == 'text'),
                'native_ordinals': list(range(start_count+1, end_count+1)), 'capture_seconds_not_latency': time.perf_counter()-tick}
            row['turns'].append(turn)
            assert kind == 'result', 'application failed: '+str(kind)
            mode = result['generation_mode']
            assert mode not in ('rules_unconfigured', 'rules_service_error'), 'model service fallback'
            assert turn['visible'] == result['reply'] and not result['tool_calls']
            review = result.get('response_review')
            if not candidate:
                assert review is None
            elif review is not None:
                assert review['reviewer'] == 'lab_typed_capability_gate_v1' and review['stream_buffered']
                assert review['native_model_improvement_claim'] is False
                assert review['current_source_id'] == result['conversation']['user_message_id']
            turn['conversation'] = query('/conversation')
            turn['speaker_snapshot'] = query('/conversation/speaker')
            with closing(MemoryStore(path)) as memory:
                turn['reminders'] = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')]
                turn['actual_local_receipts'] = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_action_receipts')]
                turn['user_sources'] = [dict(r) for r in memory._conn.execute("SELECT id,role,content,session_id FROM memory_messages WHERE role='user' ORDER BY id")]
                turn['stored_assistants'] = [dict(r) for r in memory._conn.execute("SELECT id,content FROM memory_messages WHERE role='assistant' ORDER BY id")]
                turn['profile'] = memory.get_user_profile()
            assert turn['stored_assistants'][-1]['content'] == result['reply']
            expected = 1 if case['id'] in ('c38_reminder', 'c38_protect_local') else 0
            assert len(turn['reminders']) == expected
            verify()
        with closing(MemoryStore(path)) as memory:
            dump = output / (case['id']+'-'+row['arm']+'.sql')
            dump.write_text('\n'.join(memory._conn.iterdump())+'\n')
            row['sql_dump_sha256'] = digest(dump)
        row['runtime_modules'] = runtime_source_identity()
        row['completed'] = True
    except BaseException as error:
        row['failure'] = repr(error)
    finally:
        if server:
            server.shutdown()
        if thread:
            thread.join()
        if server:
            server.server_close()
        row['server_closed'] = thread is None or not thread.is_alive()
        main_module.Avatar, main_module.LLMEngine = original, original_engine
        temporary.cleanup()
    return row


def main(args):
    frozen = verify_source(args.freeze, args.expected_freeze_sha256)
    if args.repetition not in (1, 2, 3):
        raise ValueError('unregistered repetition')
    provider = read(args.provider)
    protocol = read(PROTOCOL)
    validate_provider_identity(provider, protocol)
    assert provider['model_id'] == 'qwen3-4b-q4_k_m'
    for key, value in protocol['sampling']['inference'].items():
        expected_key = 'max_tokens_cap' if key == 'max_tokens' else key
        assert provider['configuration'][expected_key] == value, key
    verify = lambda: verify_source(args.freeze, args.expected_freeze_sha256)
    # No protected selector exists. Those inputs require a separate future gate.
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'scope': 'isolated_typed_gate_development_not_model_promotion', 'repetition': args.repetition,
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'created_utc': datetime.now(timezone.utc).isoformat(), 'frozen_inputs': frozen,
        'freeze_sha256': args.expected_freeze_sha256, 'provider': provider, 'warmups': [], 'arms': [],
        'completed': False, 'engineering_passed': False, 'failure': None, 'semantic_approved': False}
    def save():
        temporary = args.output/'sample.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(args.output/'sample.json')
    save()
    config.llm.base_url, config.llm.api_key, config.llm.model = provider['url'], 'local-eval-only', provider['model_id']
    config.embedding.model = ''
    opener = build_opener(ProxyHandler({}))
    try:
        engine = LLMEngine(base_url=provider['url'], api_key='local-eval-only', model=provider['model_id'], timeout=180)
        try:
            for stream in (False, True):
                verify()
                messages = [{'role': 'user', 'content': '请回答：你好。'}]
                reply = engine.stream_chat(messages, temperature=0, max_tokens=16) if stream else engine.chat(messages, temperature=0, max_tokens=16)
                report['warmups'].append({'streaming': stream, 'reply': reply})
                save()
        finally:
            engine.close()
        for index, case in enumerate(protocol['development_cases']):
            order = [False, True] if (index+args.repetition) % 2 else [True, False]
            for candidate in order:
                verify()
                arm = collect_arm(case, candidate, opener, args.wire, verify, args.output, args.repetition)
                report['arms'].append(arm)
                save()
                if not arm['completed'] or arm['failure']:
                    raise RuntimeError('incomplete arm; raw retained: '+str(arm['failure']))
        verify()
        assert len(report['arms']) == 24
        assert sum(len(a['turns']) for a in report['arms']) == 44
        report['completed'] = report['engineering_passed'] = True
    except BaseException as error:
        report['failure'] = repr(error)
        raise
    finally:
        save()
    print('C38 paired sampler completed24arms/44app results;semantic review pending')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--wire', type=Path, required=True)
    parser.add_argument('--freeze', type=Path, required=True)
    parser.add_argument('--expected-freeze-sha256', required=True)
    parser.add_argument('--repetition', type=int, required=True)
    main(parser.parse_args())

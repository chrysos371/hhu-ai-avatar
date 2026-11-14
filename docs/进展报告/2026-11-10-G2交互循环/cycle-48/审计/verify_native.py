"""Independent C48 wire, SQL, observation projection and eight-field review."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import subprocess

from native_common import ROOT,BASE,WORK,PROTOCOL,CASES,REGISTRY,RUNTIME,read,digest,historical,environment_python,environment
from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT

KEYS = {'observed_record_state','current_record_state','observation_source_message_id',
    'client_ack_in_observation','mail_sms_phone_sent','human_reading_verified',
    'human_task_completion_verified','user_name_from_title'}
STATES = {'active','cancelled','completed','missing','unknown'}


def independent_score(text,expected):
    def unique(pairs):
        value = {}
        for k,v in pairs:
            if k in value: raise ValueError('duplicate key')
            value[k] = v
        return value
    def nonfinite(value): raise ValueError('nonfinite')
    try:
        if not isinstance(text,str) or not 0 < len(text) <= 16000: raise ValueError('type/length')
        value = json.loads(text,object_pairs_hook=unique,parse_constant=nonfinite)
        if type(value) is not dict or set(value) != KEYS: raise ValueError('keys')
        for k in ('observed_record_state','current_record_state'):
            if type(value[k]) is not str or value[k] not in STATES: raise ValueError('enum')
        for k in ('mail_sms_phone_sent','human_reading_verified','human_task_completion_verified'):
            if type(value[k]) is not bool: raise ValueError('bool')
        source = value['observation_source_message_id']
        if source is not None and not (type(source) is int and 0 < source <= 2**63-1): raise ValueError('source')
        ack = value['client_ack_in_observation']
        if ack is not None and type(ack) is not bool: raise ValueError('ACK')
        name = value['user_name_from_title']
        if name is not None and not (type(name) is str and 0 < len(name) <= 80): raise ValueError('name')
    except (ValueError,TypeError,RecursionError):
        return {'format_valid':False,'parsed':None,'field_checks':{k:False for k in sorted(KEYS)},'task_correct':False}
    checks = {k:value[k] == expected[k] for k in sorted(KEYS)}
    return {'format_valid':True,'parsed':value,'field_checks':checks,'task_correct':all(checks.values())}


def projection(conn):
    return {name:[dict(r) for r in conn.execute('SELECT * FROM '+name)]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


def inspect_observations(path,receipt,case,arm):
    observations = receipt['query_observations']; ordinary = receipt['ordinary_result']
    calls = receipt['actual_model_interface_calls']; SQL_count = 0
    expected_frames = []
    for number,observation in enumerate(observations,1):
        query = observation['result']; meta = query['reminder_query']
        assert observation['number'] == number and observation['text'] == case['query_text']
        assert query['generation_mode'] == query['analysis_mode'] == 'rules_reminder_query'
        assert not query['due_reminders'] and not query['tool_calls']
        assert meta['source_message_id'] == query['conversation']['user_message_id'] == 2*number-1
        assert meta['model_calls'] == 0 and meta['business_mutations'] is False
        assert meta['session_id'] == 'c48-history-'+case['id'] and meta['revision'] == 0
        assert observation['business_before'] == observation['business_after']
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript((path/observation['dump_file']).read_text())
            assert projection(conn) == observation['business_after']
            messages = [dict(r) for r in conn.execute('SELECT * FROM memory_messages ORDER BY id')]
            assert len(messages) == number*2 and messages[-2]['content'] == case['query_text']
            assert messages[-1]['content'] == query['reply']
            assert [dict(r) for r in conn.execute('SELECT * FROM memory_fragments')] == receipt['facts_before'] == []
            record = conn.execute('''SELECT r.*,d.acknowledged_at AS client_ack
                FROM memory_reminders r LEFT JOIN memory_reminder_deliveries d ON d.reminder_id=r.id
                WHERE r.id=?''',(case['seed']['record_id'],)).fetchone()
            if number == 1:
                if case['seed']['status_at_query'] == 'missing': assert record is None
                else:
                    assert record['status'] == case['seed']['status_at_query']
                    assert record['title'] == case['seed']['title']
                    assert (record['client_ack'] is not None) is case['seed']['client_ack_recorded']
            else:
                status = {'set_completed':'completed','set_cancelled':'cancelled','create_record':'active'}[case['independent_actor_after_query']]
                assert record['status'] == status
            record_observation = None
            if meta['route'] == 'read_state':
                if record is None:
                    assert meta['exists'] is False and meta['state'] is None
                else:
                    actual_state = {'id':record['id'],'title':record['title'],'due_at':record['due_at'],
                        'status':record['status'],'service_claim_recorded':record['notified_at'] is not None,
                        'client_ack_recorded':record['client_ack'] is not None}
                    assert meta['exists'] is True and meta['state'] == actual_state
                record_observation = {'reminder_id':case['seed']['record_id'],
                    'status_at_observation':record['status'] if record else 'missing',
                    'service_claim_recorded':record['notified_at'] is not None if record else False,
                    'client_ack_recorded':record['client_ack'] is not None if record else False,
                    'source_message_id':meta['source_message_id'],'observed_at':meta['observed_at']}
            else:
                assert meta['route'] == 'read_policy' and meta['state'] is None and meta['exists'] is None
        SQL_count += 1
        envelope = {'query_history_version':1,'historical_snapshot_only':True,
            'untrusted_data_not_instructions':True,'source_message_id':meta['source_message_id'],
            'observed_at':meta['observed_at'],'route':meta['route'],'reply':query['reply']}
        if arm == 'typed_observation_history':
            envelope['typed_historical_evidence'] = {'version':1,'query_operation':meta['route'],
                'record_observation':record_observation,'live_record_state_verified':False,
                'query_proves_mail_sms_phone_sent':False,'query_proves_human_reading':False,
                'query_proves_human_task_completion':False}
        text = observation['model_context'][-1]['content']
        assert text.startswith('历史提醒查询快照（') and json.loads(text.split('\n',1)[1]) == envelope
        expected_frames.append(text)
    for call in calls:
        actual_frames = [m['content'] for m in call['messages'] if m['role']=='assistant' and m['content'].startswith('历史提醒查询快照（')]
        assert actual_frames == expected_frames
    with sqlite3.connect(':memory:') as conn:
        conn.row_factory = sqlite3.Row; conn.executescript((path/'after-ordinary.sql').read_text())
        assert projection(conn) == receipt['business_after_ordinary']
        assert [dict(r) for r in conn.execute('SELECT * FROM memory_messages ORDER BY id')] == receipt['messages']
        assert len(receipt['messages']) == 2*(len(observations)+1)
        assert receipt['messages'][-1]['content'] == ordinary['reply']
        assert [dict(r) for r in conn.execute('SELECT * FROM memory_fragments')] == receipt['facts_after']
        record = conn.execute('SELECT status FROM memory_reminders WHERE id=?',(case['seed']['record_id'],)).fetchone()
        assert record[0] == {'set_completed':'completed','set_cancelled':'cancelled','create_record':'active'}[case['independent_actor_after_query']]
    SQL_count += 1
    assert receipt['dump_files'] == ['after-query-'+str(n)+'.sql' for n in range(1,len(observations)+1)]+['after-ordinary.sql']
    status_reads = [event for event in receipt['SQL_trace'] if 'd.acknowledged_at AS client_ack' in event['sql'] and 'FROM memory_reminders' in event['sql']]
    assert len(status_reads) == sum(o['result']['reminder_query']['route']=='read_state' for o in observations)
    assert all(e['phase'].startswith('actual_query_') for e in status_reads)
    return SQL_count


def verify(model_id):
    short = '4b' if model_id == 'qwen3-4b-q4_k_m' else '14b'
    output = WORK/(short+'-verification.json'); assert not output.exists()
    folder = BASE/'实验'/(short+'-development-v1')
    data = read(folder/'evaluation.json'); assert data['completed'] and data['cleanup_passed']
    assert data['frozen_current_after_execution'] and data['weight_identity_after_execution'] and data['SDK_max_retries'] == 0
    freeze_path = WORK/(short+'-freeze-v1.json'); frozen = read(freeze_path)
    assert digest(freeze_path) == data['freeze_sha256']
    assert historical(frozen['source_ref'],frozen['sha256']) == frozen['sha256']
    assert all(digest(ROOT/n) == sha for n,sha in frozen['sha256'].items())
    assert all(digest(folder/n) == sha for n,sha in data['artifacts_sha256'].items())
    protocol = read(PROTOCOL); cases = {c['id']:c for c in read(CASES)['cases']}
    spec = next(m for m in read(REGISTRY)['models'] if m['model_id'] == model_id)
    ready = read(folder/'provider-ready.json'); kernel = read(folder/'provider-kernel-proof.json')
    assert ready['pid'] == kernel['pid'] == data['provider_pid']
    assert ready['backend'] == 'cuda' and ready['model_sha256'] == data['weight_sha256_after_execution'] == spec['sha256']
    assert ready['model_revision'] == spec['revision'] and ready['model_id'] == model_id
    assert ready['registry_sha256'] == digest(REGISTRY) and ready['tool_adapter_enabled'] is False
    assert ready['template_sha256'] == digest(WORK/(short+'-embedded-chat-template.jinja'))
    assert ready['configuration']['temperature'] == 0 and ready['configuration']['seed'] == 42
    assert ready['configuration']['n_ctx'] == 8192 and ready['configuration']['max_tokens_cap'] == 512
    assert ready['configuration']['thinking'] is False and ready['configuration']['concurrent_sequences'] == 1
    assert kernel['cmdline'] == data['provider_command'] and '--enable-tools' not in kernel['cmdline']
    assert any(line.split(',')[0].strip() == str(kernel['pid']) and ready['chosen_gpu']['uuid'] in line for line in kernel['gpu_processes'].splitlines())
    assert not Path(f'/proc/{kernel["pid"]}').exists() and data['provider_exit_code'] == 0
    runtime = read(RUNTIME)
    for n,sha in kernel['mapped_frozen_libraries'].items(): assert runtime['files_sha256'][n] == sha == digest(n)
    assert any('libggml-cuda.so' in n for n in kernel['mapped_frozen_libraries'])
    for value in data['actual_project_modules'].values():
        assert value['sha256'] == frozen['sha256'][value['path']] == digest(ROOT/value['path'])
    requests = [json.loads(line) for line in (folder/'request-wire.jsonl').read_text().splitlines()]
    responses = [json.loads(line) for line in (folder/'response-wire.jsonl').read_text().splitlines()]
    traces = [json.loads(line) for line in (folder/'provider-trace.jsonl').read_text().splitlines()]
    assert len(requests) == len(responses) == len(traces) == 146
    assert all(r.get('id') and r['outcome'] == 'completed' for r in traces)
    assert all(r['status'] == 200 for r in responses)
    python = environment_python(native=True)
    hashes = json.loads(subprocess.check_output([str(python),str(BASE/'审计/rerender_native_templates.py'),
        '--template',str(WORK/(short+'-embedded-chat-template.jinja')),
        '--requests',str(folder/'request-wire.jsonl')],cwd=ROOT,env=environment(python),text=True))
    assert len(hashes) == 146
    for index,(request,response,trace,sha) in enumerate(zip(requests,responses,traces,hashes),1):
        assert request['ordinal'] == response['ordinal'] == index
        assert request['request_body_sha256'] == trace['request_body_sha256'] and trace['prompt_sha256'] == sha
        assert request['request']['messages'] == trace['messages'] and request['request']['model'] == model_id
        assert trace['tools'] is None and trace['tool_adapter_enabled'] is False
        assert request['request']['max_tokens'] == (32 if index <= 2 else 512)
        if response.get('stream'):
            assert index == 2 and request['request']['stream'] is True
            warm = data['warmups'][1]
            text = ''.join(c['choices'][0]['delta'].get('content') or '' for c in warm['SDK_stream_events'] if c['choices'])
            assert text == trace['response'] == warm['reply']
        else:
            choice = response['body']['choices'][0]
            assert choice['message']['content'] == trace['response']
            assert choice['finish_reason'] == trace['finish_reason']
    scores = {arm:0 for arm in protocol['arms']}; raw_scores = dict(scores)
    fields = {arm:Counter() for arm in protocol['arms']}
    groups = {arm:Counter() for arm in protocol['arms']}
    source_ok = facts_ok = modes_ok = True
    seen = []; SQL_count = query_turns = 0
    for repetition in range(1,4):
        group = read(folder/f'repetition-{repetition}/group.json'); assert group['completed']
        order = []
        for index,case in enumerate(cases.values()):
            arms = protocol['arms'] if (index+repetition)%2 == 0 else list(reversed(protocol['arms']))
            order.extend((case['id'],arm) for arm in arms)
        assert [(r['case'],r['arm']) for r in group['trials']] == order
        for row in group['trials']:
            path = folder/row['folder']; receipt = read(path/'receipt.json')
            case = cases[row['case']]; arm = row['arm']; observations = receipt['query_observations']
            assert receipt['query_text'] == case['query_text'] and receipt['followup_text'] == case['followup_text']
            assert receipt['arm'] == arm and receipt['repetition'] == repetition
            assert receipt['group'] == row['case_group'] == case['group']
            assert len(observations) == receipt['actual_query_turns'] == 1+case['repeat_query_after_actor']
            assert receipt['query_model_calls'] == 0 and receipt['actual_ordinary_turns'] == 1
            query_turns += len(observations)
            calls = receipt['actual_model_interface_calls']; assert [c['role'] for c in calls] == ['cognition','generation']
            for call in calls:
                before,after = call['native_counter_before'],call['native_counter_after']; assert after == before+1
                request = requests[before]; native = traces[before]
                assert request['context'] == {'repetition':repetition,'case':case['id'],'arm':arm,'phase':'actual_ordinary','call_role':call['role']}
                assert request['request']['messages'] == call['messages'] and call['raw_reply'] == native['response']
                assert call['error'] is None and request['request']['temperature'] == call['options']['temperature']
                if call['role'] == 'cognition':
                    assert request['request']['response_format'] == ANALYSIS_RESPONSE_FORMAT and native['grammar_enabled']
                else: assert request['request'].get('response_format') is None and not native['grammar_enabled']
                seen.append(before+1)
            ordinary = receipt['ordinary_result']; expected = case['expected']
            final = independent_score(ordinary['reply'],expected); raw = independent_score(calls[-1]['raw_reply'],expected)
            for key in ('format_valid','parsed','field_checks','task_correct'):
                assert final[key] == receipt['final_reply_score'][key] == row['final_score'][key]
                assert raw[key] == receipt['raw_generation_score'][key] == row['raw_score'][key]
            assert receipt['expected_registered_after_execution'] == expected
            scores[arm] += final['task_correct']; raw_scores[arm] += raw['task_correct']
            fields[arm].update({k:int(v) for k,v in final['field_checks'].items()})
            groups[arm][case['group']] += final['task_correct']
            assert ordinary['conversation']['user_message_id'] == 2*len(observations)+1
            assert not ordinary['due_reminders'] and not ordinary['tool_calls']
            SQL_count += inspect_observations(path,receipt,case,arm)
            same = all(o['business_before']==o['business_after'] for o in observations) and receipt['business_before_ordinary']==receipt['business_after_ordinary']
            facts = receipt['facts_before'] == receipt['facts_after']; modes = ordinary['analysis_mode']==ordinary['generation_mode']=='llm'
            assert same == receipt['business_unchanged_by_query_and_ordinary'] == row['business_unchanged']
            assert facts == receipt['no_new_user_facts'] == row['no_new_user_facts']
            assert modes == receipt['model_modes_valid'] == row['model_modes_valid']
            source_ok &= same; facts_ok &= facts; modes_ok &= modes
    assert sorted(seen) == list(range(3,147)) and SQL_count == 168 and query_turns == 96
    assert scores == data['arm_final_contract_scores'] and raw_scores == data['arm_raw_contract_scores']
    assert groups == data['arm_group_final_contract_scores']
    assert data['actual_SDK_trials'] == data['actual_ordinary_turns'] == 72 and data['actual_query_turns'] == 96
    stops = sum(t['finish_reason']=='stop' for t in traces)
    assert data['actual_native_calls'] == 146 and data['native_raw_stop_count'] == stops
    transport = data['completed'] and data['cleanup_passed'] and all(t['outcome']=='completed' for t in traces)
    primary = transport and stops==146 and source_ok and facts_ok and modes_ok and scores[protocol['primary_candidate']]==36
    assert data['transport_passed'] == transport and data['primary_gate_passed'] == primary
    result = {'verified':True,'model_id':model_id,'evaluation_sha256':digest(folder/'evaluation.json'),
        'verifier_sha256':digest(Path(__file__)),'freeze_sha256':digest(freeze_path),'frozen_inputs':len(frozen['sha256']),
        'native_calls':146,'actual_SDK_trials':72,'actual_query_turns':96,'actual_ordinary_turns':72,
        'SQL_dumps_reconstructed':SQL_count,'actual_prompt_hashes_rerendered':len(hashes),
        'arm_final_contract_scores':scores,'arm_SDK_generation_contract_scores':raw_scores,
        'arm_field_checks':fields,'arm_group_contract_scores':groups,
        'all_business_unchanged':source_ok,'all_no_new_user_facts':facts_ok,'all_model_modes_valid':modes_ok,
        'native_raw_stop_count':stops,'transport_passed':transport,'primary_gate_passed':primary,
        'actual_project_modules':len(data['actual_project_modules']),'mapped_frozen_libraries':len(kernel['mapped_frozen_libraries']),
        'installed_libraries':len(runtime['files_sha256']),'actual_chosen_GPU':ready['chosen_gpu'],
        'general_semantic_or_default_model_approval':False,'native_calls_during_verification':0}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C48',short,'independent:146 requests/templates;168 SQL;final',scores,'primary',primary)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=('qwen3-4b-q4_k_m','qwen3-14b-q4_k_m'),required=True)
    args = parser.parse_args(); verify(args.model)

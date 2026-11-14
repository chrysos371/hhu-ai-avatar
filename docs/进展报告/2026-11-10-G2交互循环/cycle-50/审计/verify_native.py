"""Independent native wire/template/SQL review; no automatic semantic approval."""
import argparse
from collections import Counter
from verify_observations import inspect_observations
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,WORK,PROTOCOL,CASES,REGISTRY,RUNTIME,read,digest,historical,environment_python,environment
from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT

def registered_order(cases,protocol,repetition):
    result = []
    for index,case in enumerate(cases.values()):
        offset = (index+repetition-1)%3
        arms = protocol['arms'][offset:]+protocol['arms'][:offset]
        result.extend((case['id'],arm) for arm in arms)
    return result


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
    assert len(requests) == len(responses) == len(traces) == 218
    assert all(r.get('id') and r['outcome'] == 'completed' for r in traces)
    assert all(r['status'] == 200 for r in responses)
    python = environment_python(native=True)
    hashes = json.loads(subprocess.check_output([str(python),str(BASE/'审计/rerender_native_templates.py'),
        '--template',str(WORK/(short+'-embedded-chat-template.jinja')),
        '--requests',str(folder/'request-wire.jsonl')],cwd=ROOT,env=environment(python),text=True))
    assert len(hashes) == 218
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
    shapes = {arm:Counter() for arm in protocol['arms']}
    source_ok = facts_ok = modes_ok = True
    seen = []; SQL_count = query_turns = 0
    for repetition in range(1,4):
        group = read(folder/f'repetition-{repetition}/group.json'); assert group['completed']
        order = registered_order(cases,protocol,repetition)
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
            ordinary = receipt['ordinary_result']
            def shape(text):
                try: is_object = isinstance(json.loads(text),dict)
                except (ValueError,TypeError,RecursionError): is_object = False
                return {'is_text':isinstance(text,str),'nonempty':isinstance(text,str) and bool(text.strip()),
                    'characters':len(text) if isinstance(text,str) else 0,'JSON_object':is_object,'semantic_correctness':None}
            final,raw = shape(ordinary['reply']),shape(calls[-1]['raw_reply'])
            assert final == receipt['final_text_shape'] == row['final_shape']
            assert raw == receipt['raw_text_shape'] == row['raw_shape']
            assert receipt['oracle_observation_registered_after_execution'] == case['oracle_observation']
            assert receipt['review_axes_registered_after_execution'] == case['review_axes']
            assert receipt['semantic_review_pending'] is True
            shapes[arm].update({k:int(final[k]) for k in ('nonempty','JSON_object')})
            assert ordinary['conversation']['user_message_id'] == 2*len(observations)+1
            assert not ordinary['due_reminders'] and not ordinary['tool_calls']
            SQL_count += inspect_observations(path,receipt,case,arm)
            same = all(o['business_before']==o['business_after'] for o in observations) and receipt['business_before_ordinary']==receipt['business_after_ordinary']
            facts = receipt['facts_before'] == receipt['facts_after']; modes = ordinary['analysis_mode']==ordinary['generation_mode']=='llm'
            assert same == receipt['business_unchanged_by_query_and_ordinary'] == row['business_unchanged']
            assert facts == receipt['no_new_user_facts'] == row['no_new_user_facts']
            assert modes == receipt['model_modes_valid'] == row['model_modes_valid']
            source_ok &= same; facts_ok &= facts; modes_ok &= modes
    assert sorted(seen) == list(range(3,219)) and SQL_count == 234 and query_turns == 126
    assert shapes == data['arm_text_counts']
    assert data['actual_SDK_trials'] == data['actual_ordinary_turns'] == 108 and data['actual_query_turns'] == 126
    stops = sum(t['finish_reason']=='stop' for t in traces)
    assert data['actual_native_calls'] == 218 and data['native_raw_stop_count'] == stops
    transport = data['completed'] and data['cleanup_passed'] and all(t['outcome']=='completed' for t in traces)
    assert data['transport_passed'] == transport
    assert data['primary_gate_passed'] is False and data['semantic_review_pending'] is True
    result = {'verified':True,'model_id':model_id,'evaluation_sha256':digest(folder/'evaluation.json'),
        'verifier_sha256':digest(Path(__file__)),'freeze_sha256':digest(freeze_path),'frozen_inputs':len(frozen['sha256']),
        'native_calls':len(traces),'actual_SDK_trials':108,'actual_query_turns':126,'actual_ordinary_turns':108,
        'SQL_dumps_reconstructed':SQL_count,'actual_prompt_hashes_rerendered':len(hashes),
        'arm_text_counts':shapes,'semantic_review_pending':True,
        'all_business_unchanged':source_ok,'all_no_new_user_facts':facts_ok,'all_model_modes_valid':modes_ok,
        'native_raw_stop_count':stops,'transport_passed':transport,'primary_gate_passed':False,
        'actual_project_modules':len(data['actual_project_modules']),'mapped_frozen_libraries':len(kernel['mapped_frozen_libraries']),
        'installed_libraries':len(runtime['files_sha256']),'actual_chosen_GPU':ready['chosen_gpu'],
        'general_semantic_or_default_model_approval':False,'native_calls_during_verification':0}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C50',short,'independent:218 requests/templates;234 SQL; semantic review pending; default unapproved')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model',choices=('qwen3-4b-q4_k_m','qwen3-14b-q4_k_m'),required=True)
    args = parser.parse_args(); verify(args.model)

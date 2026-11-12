"""Reconstruct persisted native regression without using controller validators."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from revision_common import ROOT,BASE,OLD32,PROTOCOL,REGISTRY,RUNTIME,digest,verify_freeze,verify_historical_binding
from verify_shared_affect import parse_events,parse_native_response,restore_dump


def read(path):return json.loads(path.read_text())
def hash_text(value):return sha256(value.encode()).hexdigest()


def verify(path,*,current_source=False):
    report=read(path);folder=path.parent;phase=report['phase'];freeze=Path(report['freeze_path']);frozen=read(freeze)
    assert digest(freeze)==report['freeze_sha256'] and frozen==report['frozen_inputs'] and frozen['phase']==phase
    verify_historical_binding(frozen)
    if current_source:verify_freeze(freeze,report['freeze_sha256'],report['model_id'],phase=phase)
    assert report['completed'] and report['engineering_passed'] and report['cleanup_passed'] and report['failure'] is None and not report['cleanup_errors']
    assert report['actual_llm_or_gpu'] is True and report['production_candidate_activation_authorized'] is False and report['general_semantic_or_human_quality_approved'] is False
    protocol=read(ROOT/PROTOCOL);spec=next(model for model in read(ROOT/REGISTRY)['models'] if model['model_id']==report['model_id'])
    ready=read(folder/'provider-ready.json');close=read(folder/'provider-closeout.json');assert ready==report['provider_ready'] and close==report['provider_closeout']
    assert ready['pid']==close['pid']==report['provider_pid'] and report['provider_exit']==0 and not report.get('provider_forced_cleanup') and close['model_closed'] and close['server_closed']
    assert ready['model_id']==spec['model_id'] and ready['model_sha256']==spec['sha256'] and ready['model_revision']==spec['revision']
    assert ready['registry_sha256']==frozen['sha256'][REGISTRY] and ready['metadata_sha256']==frozen['sha256'][spec['metadata']] and ready['backend']=='cuda' and ready['llama_cpp_python']=='0.3.19'
    assert ready['provider_source_sha256']==frozen['sha256'][str((OLD32/'serve_state_eval.py').relative_to(ROOT))] and ready['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
    assert ready['state_policy']==close['state_policy']=='logical_reset' and ready['backend_runtime_identity_sha256']==close['backend_runtime_identity_sha256']==frozen['sha256'][RUNTIME]
    assert ready['backend_runtime_files_verified']==close['runtime_files_verified_after']==54 and max(ready['process_gpu_mib_after_load'])>=1024
    gpu=ready['chosen_gpu'];assert gpu['free_mib']>=spec['required_free_mib'] and gpu['utilization_percent']<=20 and ready['effective_visible_devices']==gpu['uuid']
    assert not any(line.split(',')[0].strip()==str(ready['pid']) for line in report['gpu_processes_after'].splitlines())
    for key,value in {'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1,'repeat_penalty':1.0,'top_p':1.0,'top_k':0,'state_policy':'logical_reset'}.items():assert ready['configuration'][key]==value
    trace=folder/'provider-trace.jsonl';assert digest(trace)==report['native_trace_sha256'];native=[json.loads(line) for line in trace.read_text().splitlines()];assert len(native)==len(report['requests'])==8
    previous=0
    for row,actual in zip(report['requests'],native,strict=True):
        identifier,reply=parse_native_response(row);assert identifier==row['provider_call_id']==actual['id'] and reply==row['reply']==actual['response'] and row['finish_reason']==actual['finish_reason']=='stop' and actual['outcome']=='completed'
        assert row.get('status',row.get('http_status'))==200 and json.loads(row['raw_request_json'])==row['request'] and hash_text(row['raw_request_json'])==row['request_sha256']==actual['request_body_sha256']
        assert row['request']['messages']==actual['messages'] and row['request']['stream']==actual['stream']
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda value:hash_text(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))) if value is not None else None
        assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt) and actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)
        state=actual['state_observation'];assert state['policy']=='logical_reset' and state['logical_tokens_before_policy']==previous and state['logical_tokens_after_policy']==0 and state['explicit_logical_reset_called'] is True and state['explicit_context_memory_clear_called'] is False
        previous=state['logical_tokens_after_generation'];assert type(previous) is int and previous>0
    assert len(report['workers'])==len(report['cases'])==1;worker=report['workers'][0];case=report['cases'][0]
    assert worker['exit_code']==0 and not worker['forced_cleanup'] and worker['turns_completed']==len(case['turns'])==4 and case['complete']
    runtime=read(folder/worker['runtime_file']);assert runtime['pid']==worker['pid'] and runtime['failure'] is None and runtime['phase']==phase and runtime['actual_llm_or_gpu'] is True and runtime['provider_kind']=='actual_native_loopback_relay' and runtime['recover_context'] is True
    for source in runtime['module_sources'].values():assert source['sha256']==frozen['sha256'][str(Path(source['path']).relative_to(ROOT))]
    prepared=read(folder/'application/prepared.json');forgotten=read(folder/'application/forgotten.json');final=read(folder/'application/final.json');assert restore_dump(folder/'final-database.sql')==final
    for snapshot in case['snapshots']:assert digest(folder/snapshot['file'])==snapshot['sha256']
    expected=protocol['native_fixed_source']+protocol['native_after_forget_turns'];assert [turn['input'] for turn in case['turns']]==expected
    llm_index=0;app_call_ids=[]
    for index,turn in enumerate(case['turns']):
        result=turn['result'];events=parse_events(turn['raw_sse']);assert events==[{key:event[key] for key in ('event','id','data')} for event in turn['events']]
        assert turn['terminal']=='result' and events[-1]['event']=='result' and events[-1]['data']==result
        pieces=''.join(event['data']['text'] for event in events if event['event']=='text')
        if index==2:assert result['analysis_mode']==result['generation_mode']=='rules_speaker_control' and pieces in ('',result['reply'])
        else:
            assert result['analysis_mode']==result['generation_mode']=='llm' and pieces==result['reply']
            cognitive,generation=case['model_requests'][llm_index:llm_index+2];llm_index+=2
            assert cognitive['kind']=='cognitive' and generation['kind']=='generation' and generation['reply']==result['reply']
            emotion=json.loads(cognitive['reply'])['emotion'];clamp=lambda value:max(-1.0,min(1.0,float(value)))
            assert result['user_valence']==clamp(emotion['valence']) and result['user_arousal']==clamp(emotion['arousal'])
            app_call_ids.extend([cognitive['provider_call_id'],generation['provider_call_id']])
        snapshot=prepared if index<2 else final;aid=result['conversation']['assistant_message_id'];uid=result['conversation']['user_message_id'];messages={message['id']:message for message in snapshot['memory_messages']}
        assert messages[uid]['role']=='user' and messages[uid]['content']==turn['input'] and messages[aid]['role']=='assistant' and messages[aid]['content']==result['reply']
        assert json.loads(next(row['result_json'] for row in snapshot['memory_chat_results'] if row['message_id']==aid))==result
        items=turn['conversation']['body']['data']['items'];expected_items=[(m['id'],m['role'],'此条内容已删除。' if m['content']=='[redacted]' else m['content']) for m in snapshot['memory_messages'] if m['id']<=aid]
        assert [(item['id'],item['role'],item['text']) for item in items]==expected_items
    assert llm_index==6 and app_call_ids==[row['id'] for row in native[2:]]
    operation=case['external_operations'][0];assert operation['revision_after']==operation['revision_before']+1
    assert next(row for row in forgotten['memory_messages'] if row['id']==operation['source_message_id'])['content']=='[redacted]'
    assert not final['memory_reminders'] and not final['memory_action_receipts']
    emotions=[json.loads(call['raw_body'])['data'] for call in report['http_calls'] if call['route']=='/emotion'];assert emotions==[case['emotions'][label] for label in ('initial','prepared','forgotten','confirmed','neutral')]
    nonzero=lambda state:any(abs(state[axis])>1e-9 for axis in ('valence','arousal'))
    observation=case['observations'];assert observation['prepared_nonzero_automatic']==nonzero(emotions[1]['automatic']) and observation['prepared_nonzero_user_observation']==nonzero(emotions[1]['user_observation'])
    assert observation['automatic_zero_after_forget']==(not nonzero(emotions[2]['automatic'])) and observation['user_observation_zero_after_forget']==(not nonzero(emotions[2]['user_observation']))
    cue=protocol['native_fixed_source'][-1];assert all(cue not in json.dumps(row['request'],ensure_ascii=False) for row in case['model_requests'][-2:]) and observation['erased_cue_absent_after_forget_sdk'] is True
    if phase=='after':assert observation['automatic_zero_after_forget'] and observation['user_observation_zero_after_forget']
    return {'verified':True,'phase':phase,'model_id':report['model_id'],'evaluation_sha256':digest(path),'freeze_sha256':report['freeze_sha256'],'historical_source_verified':True,'current_source_verified':current_source,
        'native_calls':8,'app_turns':4,'clean_app_os':1,'clean_provider_exit':True,'runtime_modules':len(runtime['module_sources']),'gpu':gpu,'observations':observation,'independent_sql_sse_sdk_and_api_reconstruction':True,'human_emotion_or_general_quality_approved':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('evaluation',type=Path);parser.add_argument('--output',required=True,type=Path);parser.add_argument('--current-source',action='store_true');args=parser.parse_args();result=verify(args.evaluation,current_source=args.current_source)
    with args.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('Verified',result['phase'],result['model_id'],'8native/4app/1OS; historical source plus raw SQL/SSE/SDK/API; observed',result['observations'])

"""Independent raw HTTP, SQL restoration, SSE and shared-history reconstruction."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from shared_affect_common import ROOT,BASE,OLD31,OLD32,PROTOCOL,REGISTRY,RUNTIME,ARMS,digest,verify_freeze,verify_historical_binding


def read(path):return json.loads(path.read_text())
def hash_text(text):return sha256(text.encode()).hexdigest()


def restore_dump(path):
    with closing(sqlite3.connect(':memory:')) as conn:
        conn.executescript(path.read_text());conn.row_factory=sqlite3.Row
        assert [tuple(row) for row in conn.execute('PRAGMA integrity_check')]==[('ok',)]
        tables=[row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        return {name:[dict(row) for row in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')] for name in tables}


def parse_native_response(row):
    raw=row['raw_http_body'];assert hash_text(raw)==row['response_body_sha256']
    if row['request']['stream']:
        lines=[line[6:] for line in raw.splitlines() if line.startswith('data: ')]
        assert lines[-1]=='[DONE]';chunks=[json.loads(line) for line in lines[:-1]];ident=chunks[0]['id']
        assert all(chunk['id']==ident for chunk in chunks)
        reply=''.join(chunk['choices'][0]['delta'].get('content','') or '' for chunk in chunks)
        assert [chunk['choices'][0]['finish_reason'] for chunk in chunks if chunk['choices'][0]['finish_reason'] is not None]==['stop']
    else:
        value=json.loads(raw);ident=value['id'];reply=value['choices'][0]['message']['content'];assert value['choices'][0]['finish_reason']=='stop'
    return ident,reply


def parse_events(raw):
    rows=[];current={}
    for line in raw.splitlines()+['']:
        if not line:
            if current:rows.append({**current,'data':json.loads(current['data'])});current={}
        elif line.startswith(('id: ','event: ','data: ')):
            key,value=line.split(': ',1);assert key not in current;current[key]=value
    return rows


def verify_case(folder,case,workers,native_map,frozen):
    assert read(folder/'segment-completed.json')==case and case['complete']
    final=read(folder/'final.json');assert restore_dump(folder/'database_dump.sql')==final
    for snapshot in case['snapshots']:
        path=folder.parents[1]/snapshot['file'];assert digest(path)==snapshot['sha256']
    worker=workers[case['id']];assert worker['exit_code']==0 and worker['forced_cleanup'] is False and worker['analysis_runtime_verified']
    runtime=read(folder.parents[1]/worker['runtime_file']);assert runtime['pid']==worker['pid'] and runtime['failure'] is None
    assert runtime['actual_llm_or_gpu'] is True and runtime['provider_kind']=='actual_native_loopback_relay' and runtime['audit_timing_hooks'] is False and runtime['recover_context'] is True
    assert runtime['initial_emotion']==worker['initial_emotion'] and all(value==0 for value in runtime['initial_emotion'].values())
    assert runtime['audit_analysis_rows']==worker['analysis_rows']==case['analysis_rows'] and runtime['audit_analysis_arm']==case['arm']
    for source in runtime['module_sources'].values():assert frozen['sha256'][str(Path(source['path']).relative_to(ROOT))]==source['sha256']
    assert worker['runtime_modules_bound']==len(runtime['module_sources']) and worker['turns_completed']==len(case['turns'])
    if case['arm']==ARMS[1]:
        source=runtime['audit_candidate_source'];assert Path(source['path']).resolve()==(OLD31/'readonly_analysis_candidate.py').resolve()
        assert frozen['sha256'][str(Path(source['path']).relative_to(ROOT))]==source['sha256'] and runtime['audit_analysis_hook'] is True
    else:assert runtime['audit_candidate_source'] is None and runtime['audit_analysis_hook'] is False and case['analysis_rows']==[]
    for turn in case['turns']:
        result=turn['result'];parsed=parse_events(turn['raw_sse']);assert parsed==[{key:event[key] for key in ('event','id','data')} for event in turn['events']]
        assert turn['terminal']=='result' and parsed[-1]['event']=='result' and parsed[-1]['data']==result
        assert ''.join(event['data']['text'] for event in parsed if event['event']=='text')==result['reply']
        assert turn['app_pid']==worker['pid'] and turn['accepted']['status']==202 and turn['conversation']['status']==200
        uid=result['conversation']['user_message_id'];aid=result['conversation']['assistant_message_id']
        messages={row['id']:row for row in final['memory_messages']};assert messages[uid]['role']=='user' and messages[uid]['content']==turn['input'] and messages[aid]['role']=='assistant' and messages[aid]['content']==result['reply']
        stored=next(row for row in final['memory_chat_results'] if row['message_id']==aid);assert json.loads(stored['result_json'])==result
        api=turn['conversation']['body']['data']['items'];assert [(m['id'],m['role'],m['text']) for m in api]==[(m['id'],m['role'],m['content']) for m in final['memory_messages'] if m['id']<=aid]
    for row in case['model_requests']:
        ident,reply=parse_native_response(row);actual=native_map[ident]
        assert ident==row['provider_call_id'] and reply==row['reply']==actual['response'] and actual['outcome']=='completed'
        assert actual['messages']==row['request']['messages'] and actual['request_body_sha256']==row['request_sha256']==hash_text(row['raw_request_json'])
        assert json.loads(row['raw_request_json'])==row['request']
    assert not final['memory_reminders'] and not final['memory_action_receipts']
    return final


def verify(path):
    report=read(path);output=path.parent;work=BASE/'审计/工作目录/001-共享历史隐含情绪'
    frozen=verify_freeze(work/'执行冻结.json',report['freeze_sha256'],report['model_id']);verify_historical_binding(frozen)
    protocol=read(ROOT/PROTOCOL);registry=read(ROOT/REGISTRY);spec=next(m for m in registry['models'] if m['model_id']==report['model_id'])
    assert report['completed'] and report['engineering_passed'] and report['cleanup_passed'] and report['failure'] is None and report['cleanup_errors']==[]
    assert Path(report['output']).resolve()==output.resolve() and report['actual_llm_or_gpu'] is True and report['semantic_approved'] is False and report['production_activation_authorized'] is False
    ready=read(output/'provider-ready.json');close=read(output/'provider-closeout.json');assert ready==report['provider_ready'] and close==report['provider_closeout']
    assert ready['pid']==close['pid']==report['provider_pid'] and report['provider_exit']==0 and not report.get('provider_forced_cleanup')
    assert close['model_closed'] and close['server_closed'] and ready['state_policy']==close['state_policy']=='logical_reset'
    assert ready['backend']=='cuda' and ready['model_id']==spec['model_id'] and ready['model_sha256']==spec['sha256'] and ready['model_revision']==spec['revision']
    assert ready['registry_path']==REGISTRY and ready['registry_sha256']==frozen['sha256'][REGISTRY] and ready['metadata_sha256']==frozen['sha256'][spec['metadata']]
    assert ready['llama_cpp_python']=='0.3.19' and max(ready['process_gpu_mib_after_load'])>=1024
    assert ready['provider_source_sha256']==frozen['sha256'][str((OLD32/'serve_state_eval.py').relative_to(ROOT))] and ready['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
    assert ready['backend_runtime_identity_sha256']==close['backend_runtime_identity_sha256']==frozen['sha256'][RUNTIME] and ready['backend_runtime_files_verified']==close['runtime_files_verified_after']==54
    gpu=ready['chosen_gpu'];assert gpu['free_mib']>=spec['required_free_mib'] and gpu['utilization_percent']<=20 and ready['effective_visible_devices']==gpu['uuid']
    assert not any(line.split(',')[0].strip()==str(ready['pid']) for line in report['gpu_processes_after'].splitlines())
    for key,value in {'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1,'repeat_penalty':1.0,'top_p':1.0,'top_k':0,'state_policy':'logical_reset'}.items():assert ready['configuration'][key]==value
    trace=output/'provider-trace.jsonl';assert digest(trace)==report['native_trace_sha256'];native=[json.loads(line) for line in trace.read_text().splitlines()]
    native_map={r['id']:r for r in native};assert len(native_map)==len(native)==len(report['requests'])
    previous=0
    for row,actual in zip(report['requests'],native,strict=True):
        ident,reply=parse_native_response(row);assert ident==actual['id']==row['provider_call_id'] and reply==actual['response']==row['reply']
        assert row.get('status',row.get('http_status'))==200 and actual['outcome']=='completed' and row['finish_reason']==actual['finish_reason']=='stop'
        assert json.loads(row['raw_request_json'])==row['request'] and hash_text(row['raw_request_json'])==row['request_sha256']==actual['request_body_sha256']
        assert actual['messages']==row['request']['messages'] and actual['stream']==row['request']['stream']
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda v:hash_text(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':'))) if v is not None else None
        assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt) and actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)
        state=actual['state_observation'];assert state['policy']=='logical_reset' and state['logical_tokens_before_policy']==previous and state['logical_tokens_after_policy']==0
        assert state['explicit_logical_reset_called'] is True and state['explicit_context_memory_clear_called'] is False and state['general_physical_state_guarantee'] is False
        previous=state['logical_tokens_after_generation'];assert type(previous) is int and previous>0
    assert len(report['workers'])==len(report['cases'])==144 and len(report['groups'])==48 and sum(len(c['turns']) for c in report['cases'])==192
    workers={w['case']:w for w in report['workers']};cases={c['id']:c for c in report['cases']};assert len(workers)==len(cases)==144
    expected_order=[(rep,c['id']) for rep in (1,2,3) for c in protocol['cases']]
    assert [(g['repetition'],g['case_id']) for g in report['groups']]==expected_order
    pairs=[];all_call_ids=[];skips=0
    for group in report['groups']:
        assert group['complete'] and read(output/group['id']/'group-completed.json')==group
        spec_case=next(c for c in protocol['cases'] if c['id']==group['case_id']);index=protocol['cases'].index(spec_case)
        assert group['arm_order']==protocol['case_arm_orders'][group['repetition']-1][index]
        preparation=cases[group['preparation_case']];assert preparation['role']=='preparation' and preparation['arm']==ARMS[0] and [t['input'] for t in preparation['turns']]==spec_case['shared_preparation']
        preparation_folder=output/group['id']/'preparation';initial=verify_case(preparation_folder,preparation,workers,native_map,frozen)
        assert len(initial['memory_messages'])==4 and len(preparation['model_requests'])==4
        expected=[]
        for turn in preparation['turns']:expected.extend([{'role':'user','content':turn['input']},{'role':'assistant','content':turn['result']['reply']}])
        assert expected==group['shared_role_messages'] and group['backup']['initial_logical_data_equal'] and group['backup']['preparation_worker_closed']
        original_dump=(preparation_folder/'database_dump.sql').read_text();assert hash_text(original_dump)==group['backup']['initial_logical_dump_sha256']
        selected={};all_call_ids.extend(row['provider_call_id'] for row in preparation['model_requests'])
        for arm in group['arm_order']:
            case=cases[group['probe_cases'][arm]];folder=output/group['id']/arm
            assert case['role']=='probe' and case['arm']==arm and len(case['turns'])==1 and case['turns'][0]['input']==spec_case['probe']
            assert (folder/'initial-database_dump.sql').read_text()==original_dump and restore_dump(folder/'initial-database_dump.sql')==read(folder/'initial.json')==initial
            final=verify_case(folder,case,workers,native_map,frozen);assert len(final['memory_messages'])==6
            rows=case['model_requests'];result=case['turns'][0]['result'];generation=next(row for row in rows if row['kind']=='generation')
            assert generation['request']['messages'][1:-1]==expected and generation['request']['messages'][-1]=={'role':'user','content':spec_case['probe']}
            assert case['probe_messages']==generation['request']['messages'] and result['generation_mode']=='llm'
            skipped=result['analysis_mode']=='lab_readonly_context_rules';assert case['probe_skipped']==skipped and len(rows)==2-int(skipped)
            if skipped:
                assert arm==ARMS[1] and result['user_valence']==result['user_arousal']==0
            else:
                cognitive=next(row for row in rows if row['kind']=='cognitive');assert cognitive['request']['messages'][1:-1]==expected
                emotion=json.loads(cognitive['reply'])['emotion'];clamp=lambda value:max(-1.0,min(1.0,float(value)))
                assert result['analysis_mode']=='llm' and result['user_valence']==clamp(emotion['valence']) and result['user_arousal']==clamp(emotion['arousal'])
            if arm==ARMS[1]:assert len(case['analysis_rows'])==1 and case['analysis_rows'][0]['decision']['eligible']==skipped and case['analysis_rows'][0]['history_role_count']==4
            aid=result['conversation']['assistant_message_id'];deps={r['source_id'] for r in final['memory_response_context'] if r['message_id']==aid and r['source_type']=='message'};assert {1,2,3,4,5}<=deps
            assert case['strict_code_correct']==(result['reply'].strip()==spec_case['expected_code'])
            all_call_ids.extend(row['provider_call_id'] for row in rows);selected[arm]=(case,result)
        before,after=[selected[arm][1] for arm in ARMS];fields=('user_valence','user_arousal','user_emotion','valence','arousal','emotion','strategy','style')
        differing=[field for field in fields if before[field]!=after[field]];skip=selected[ARMS[1]][0]['probe_skipped'];skips+=int(skip)
        assert group['differing_fields']==differing and group['actual_candidate_skipped']==skip and group['raw_replies_identical']==(before['reply']==after['reply'])
        assert group['strict_code_correct']==[selected[arm][0]['strict_code_correct'] for arm in ARMS]
        pairs.append({'group':group['id'],'stratum':group['stratum'],'candidate_skipped':skip,'route_reason':selected[ARMS[1]][0]['analysis_rows'][0]['decision']['reason'],
            'user_observation_changed':any(before[field]!=after[field] for field in ('user_valence','user_arousal','user_emotion')),'exact_observed_fields_differ':differing,
            'raw_replies_equal':before['reply']==after['reply'],'strict_code_correct':group['strict_code_correct']})
    assert all_call_ids==[row['id'] for row in native[2:]] and len(native)==386-skips and report['actual_candidate_skips']==skips
    return {'verified':True,'model_id':report['model_id'],'evaluation_sha256':digest(path),'freeze_sha256':report['freeze_sha256'],'native_calls':len(native),'candidate_skips':skips,
        'app_turns':192,'clean_os_workers':144,'shared_preparation_groups':48,'shared_initial_sql_dumps_verified':96,'restored_roles_per_probe':4,'sse_sql_api_and_sdk_bound':True,
        'pairs':pairs,'independent_of_controller_validation':True,'model_emotion_is_not_human_ground_truth':True,'production_or_general_semantic_approval':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('evaluation',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();result=verify(args.evaluation)
    with args.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('Verified',result['model_id'],result['native_calls'],'native calls,192app/144OS/48shared groups;skips',result['candidate_skips'],'user observation changed',sum(pair['user_observation_changed'] for pair in result['pairs']),'semantic approval false')

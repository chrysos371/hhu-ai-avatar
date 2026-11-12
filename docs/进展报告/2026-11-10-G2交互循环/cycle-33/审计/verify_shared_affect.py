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

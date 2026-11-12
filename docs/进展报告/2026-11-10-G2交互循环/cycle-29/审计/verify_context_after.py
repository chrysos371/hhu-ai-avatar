"""Independent post-hoc baseline source/SDK/SSE/API/SQLite binding audit."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import subprocess
from context_baseline_common import ROOT,BASE,PROTOCOL,digest
EXPECTED='1281fceadf1be94c573481366bc2d1ba9947821c94c4edbebd80f1971c871506'


def read(path):return json.loads(path.read_text())
def git_bytes(ref,name):return subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)
def normalized(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,default=lambda x:{'sqlite_blob_hex':x.hex()} if isinstance(x,bytes) else str(x))


def verify():
    folder=BASE/'实验/context-baseline-after';path=folder/'baseline.json';data=read(path)
    freeze_path=ROOT/'evals/interaction/cycle-29/context-continuity-after-freeze.json';assert digest(freeze_path)==EXPECTED
    frozen=read(freeze_path);assert data['freeze_sha256']==EXPECTED and data['frozen_inputs']==frozen
    assert data['completed'] and data['engineering_passed'] and data['failure'] is None and data['cleanup_errors']==[]
    assert data['actual_llm_or_gpu'] is False and data['provider_kind']=='controlled_loopback_http_fixture'
    for name,value in frozen['sha256'].items():assert sha256(git_bytes(frozen['source_ref'],name)).hexdigest()==value
    current_matches=all(digest(ROOT/name)==value for name,value in frozen['sha256'].items())
    assert sha256(git_bytes(data['head'],str(freeze_path.relative_to(ROOT)))).hexdigest()==EXPECTED
    protocol=json.loads(git_bytes(frozen['source_ref'],PROTOCOL));assert len(data['workers'])==3
    worker_map={row['pid']:row for row in data['workers']};assert len(worker_map)==3
    for row in data['workers']:
        assert row['exit_code']==0 and not row['forced_cleanup'] and row['runtime_pid_matches']
        runtime=read(folder/row['runtime_file']);assert runtime['pid']==row['pid'] and runtime['failure'] is None
        assert runtime['actual_llm_or_gpu'] is False and len(runtime['module_sources'])==row['runtime_modules_bound']==46
        for name,value in runtime['module_sources'].items():
            assert Path(value['path']).is_relative_to(ROOT/'src') and frozen['sha256'][str(Path(value['path']).relative_to(ROOT))]==value['sha256']
    summaries=[];app_turns=0;model_calls=0
    for case,expected_case in zip(data['cases'],protocol['cases']):
        assert case['id']==expected_case['id'] and case['complete'] and len(case['turns'])==3
        rows=case['model_requests'];assert len(rows)==6 and Counter(r['kind'] for r in rows)=={'cognitive':3,'generation':3}
        for row in rows:
            assert row['outcome']=='completed' and row['actual_llm_or_gpu'] is False
            assert json.loads(row['raw_request_json'])==row['request'] and sha256(row['raw_request_json'].encode()).hexdigest()==row['request_sha256']
        generation=[r for r in rows if r['kind']=='generation']
        sql={row['id']:row for row in case['persistent_messages_after']};assert len(sql)==6
        for number,(turn,native,text) in enumerate(zip(case['turns'],generation,expected_case['turns']),1):
            assert turn['input']==text and turn['terminal']=='result' and turn['result']['generation_mode']=='llm'
            assert turn['result']['analysis_mode']=='llm' and native['request']['messages'][-1]=={'role':'user','content':text}
            assert native['reply']==turn['result']['reply']==''.join(e['data']['text'] for e in turn['events'] if e['event']=='text')
            assert native['request'].get('response_format') is None and native['request']['model']=='c29-controlled'
            cog=[r for r in rows if r['kind']=='cognitive' and r['request']['messages'][-1]['content']==text];assert len(cog)==1
            assert cog[0]['request']['response_format']['json_schema']['name']=='avatar_cognitive_analysis'
            ids=turn['result']['conversation'];u=sql[ids['user_message_id']];a=sql[ids['assistant_message_id']]
            assert (u['role'],u['content'])==('user',text) and (a['role'],a['content'])==('assistant',native['reply'])
            assert u['session_id']==a['session_id']==worker_map[turn['app_pid']]['readiness']['session_id']
            api=turn['conversation']['body']['data']['items'];public={item['id']:item for item in api}
            assert public[a['id']]['text']==a['content'] and public[u['id']]['text']==u['content']
        expected=[]
        for turn in case['turns'][:2]:expected.extend([{'role':'user','content':turn['input']},{'role':'assistant','content':turn['result']['reply']}])
        assert case['expected_prior_messages']==expected and case['third_generation_messages']==generation[-1]['request']['messages']
        actual=Counter((r['role'],r['content']) for r in case['third_generation_messages'])
        counts=[actual[(r['role'],r['content'])] for r in expected]
        assert [r['count'] for r in case['prior_message_counts']]==counts
        assert case['desired_context_continuity_passed']==all(value==1 for value in counts)
        pids=[t['app_pid'] for t in case['turns']]
        if case['id']=='same_instance':assert len(set(pids))==1 and counts==[1,1,1,1]
        else:assert pids[0]==pids[1]!=pids[2] and counts==[1,1,1,1]
        assert generation[-1]['request']['messages'][1:]==expected+[{'role':'user','content':expected_case['turns'][2]}]
        deps=case['sql_snapshot']['memory_response_context']
        final_id=case['turns'][-1]['result']['conversation']['assistant_message_id']
        linked={r['source_id'] for r in deps if r['message_id']==final_id and r['source_type']=='message'}
        assert set(sql)-{final_id}<=linked
        assert len(case['turns'][-1]['conversation']['body']['data']['items'])==6
        assert not case['sql_snapshot']['memory_reminders']
        export=sqlite3.connect(':memory:')
        try:
            export.row_factory=sqlite3.Row;export.executescript((folder/case['id']/'database_dump.sql').read_text())
            for table,expected_rows in case['sql_snapshot'].items():
                restored=[dict(r) for r in export.execute('SELECT * FROM "'+table.replace('"','""')+'"')]
                assert Counter(normalized(r) for r in restored)==Counter(normalized(r) for r in expected_rows)
        finally:export.close()
        summaries.append({'case':case['id'],'prior_message_counts':counts,'third_prompt_roles':[r['role'] for r in generation[-1]['request']['messages']],
            'persisted_messages':6,'conversation_api_items':6,'model_http_calls':6,'reminder_rows':0,'sql_export_all_tables_roundtrip_verified':True})
        app_turns+=3;model_calls+=6
    assert data['desired_context_continuity_passed'] is True and app_turns==6 and model_calls==12
    result={'verified':True,'baseline_sha256':digest(path),'verifier_sha256':digest(Path(__file__)),'freeze_sha256':EXPECTED,'frozen_inputs':len(frozen['sha256']),
        'historical_git_inputs_verified':True,'current_inputs_match_at_this_verification':current_matches,'actual_worker_modules_bound_each':46,
        'app_turns':app_turns,'controlled_model_http_calls':model_calls,'app_processes':3,'all_exit0':True,'summaries':summaries,
        'actual_llm_or_gpu':False,'general_semantic_or_all_memory_loss_claim':False,'context_role_messages_after_restart_restored_in_this_sample':True}
    out=BASE/'审计/工作目录/002-有界已完成对话恢复/修后OS核验.json';text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if out.exists():assert out.read_text()==text
    else:out.write_text(text)
    print('Verified6 app turns,12 controlled SDK HTTP calls,3 OS workers and SQL/API/source bindings; restart and same-process prior-role counts1 each.')


if __name__=='__main__':verify()

"""Independent raw native/SDK/SSE/SQL source and fixed answer recomputation."""
import argparse
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time
from context_native_common import ROOT,BASE,OLD,PROTOCOL,REGISTRY,digest,verify_historical_binding
sys.path.insert(0,str(OLD));sys.path.insert(0,str(ROOT/'scripts'))
from run_context_baseline import events
from verify_context_baseline import normalized
from run_native_context_use import grade,parse_wire,validate_native_calls
from evaluate_native_output_audit import validate_provider_identity
EXPECTED='41218266bd466d9104edacd275d66bb9fa1e94b2692814a21f06026f89afeea0'


def read(path):return json.loads(path.read_text())
def verify(path,out):
    assert path.resolve().is_relative_to(BASE/'实验') and out.resolve().is_relative_to(BASE/'审计') and not out.exists()
    folder=path.parent;data=read(path);fp=ROOT/'evals/interaction/cycle-30/native-context-use-v2-freeze.json';frozen=read(fp)
    assert digest(fp)==EXPECTED==data['freeze_sha256'] and data['frozen_inputs']==frozen
    assert data['completed'] and data['engineering_passed'] and data['cleanup_passed'] and data['failure'] is None and not data['cleanup_errors']
    assert data['actual_llm_or_gpu'] is True and data['semantic_approved'] is False and data['historical_git_inputs_verified_before_output'] is True
    verify_historical_binding(frozen)
    git=lambda ref,name:subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)
    assert sha256(git(data['head'],str(fp.relative_to(ROOT)))).hexdigest()==EXPECTED
    protocol=json.loads(git(frozen['source_ref'],PROTOCOL));provider=data['provider_ready']
    validate_provider_identity(provider,{'models_registry':REGISTRY,'models_registry_sha256':frozen['sha256'][REGISTRY],'provider_backend':'cuda'})
    assert provider['pid']==data['provider_pid'] and provider['model_id']==data['model_id']
    assert provider['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
    assert provider['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
    assert data['provider_exit']==0 and not data.get('provider_forced_cleanup')
    assert not any(line.split(',')[0].strip()==str(data['provider_pid']) for line in data['gpu_processes_after'].splitlines())
    trace=folder/'provider-trace.jsonl';assert digest(trace)==data['native_trace_sha256']
    native=[json.loads(line) for line in trace.read_text().splitlines()];validate_native_calls(data,native)
    assert len(data['warmups'])==2 and data['requests'][:2]==data['warmups']
    for i,row in enumerate(data['warmups']):
        assert row['request']=={'model':data['model_id'],'messages':[{'role':'user','content':'请回答：你好。'}],'stream':protocol['warmups'][i],'temperature':0,'max_tokens':16}
    workers={w['pid']:w for w in data['workers']};assert len(workers)==24;runtime_counts=[]
    for worker in workers.values():
        assert worker['exit_code']==0 and not worker['forced_cleanup']
        runtime=read(folder/worker['runtime_file']);assert runtime['pid']==worker['pid'] and runtime['failure'] is None
        assert runtime['actual_llm_or_gpu'] is True and runtime['provider_kind']=='actual_native_loopback_relay'
        assert runtime['recover_context']==worker['recover_context'] and runtime['audit_timing_hooks'] is False
        for source in runtime['module_sources'].values():assert frozen['sha256'][str(Path(source['path']).relative_to(ROOT))]==source['sha256']
        assert len(runtime['module_sources'])==worker['runtime_modules_bound'];runtime_counts.append(worker['runtime_modules_bound'])
    schedule=[(c,arm) for c,order in zip(protocol['cases'],protocol['case_arm_orders'],strict=True) for arm in order]
    summaries=[];allrows=[];turn_count=0
    for group,(case,arm) in zip(data['cases'],schedule,strict=True):
        assert group['case_id']==case['id'] and group['arm']==arm and group['complete'] and len(group['turns'])==3
        pids=[t['app_pid'] for t in group['turns']];assert pids[0]==pids[1]!=pids[2]
        assert all(workers[pid]['case']==group['id'] and workers[pid]['recover_context']==(arm=='recovered_restart') for pid in pids)
        rows=[parse_wire(row) for row in group['model_requests']];assert len(rows)==6 and Counter(row['kind'] for row in rows)=={'cognitive':3,'generation':3}
        generations=[r for r in rows if r['kind']=='generation'];cognitive=[r for r in rows if r['kind']=='cognitive']
        snapshots={}
        for ref in group['snapshots']:
            target=folder/ref['file'];assert digest(target)==ref['sha256'];snapshots[ref['label']]=read(target)
        final=snapshots['final'];messages={m['id']:m for m in final['memory_messages']};assert len(messages)==6
        for index,(turn,text,gen,cog) in enumerate(zip(group['turns'],case['turns'],generations,cognitive,strict=True)):
            assert turn['input']==text and turn['terminal']=='result' and turn['result']['generation_mode']==turn['result']['analysis_mode']=='llm'
            kind,result,observed,raw=events(BytesIO(turn['raw_sse'].encode()),time.perf_counter())
            assert kind=='result' and result==turn['result'] and raw==turn['raw_sse']
            assert [(e['event'],e['id'],e['data']) for e in observed]==[(e['event'],e['id'],e['data']) for e in turn['events']]
            assert ''.join(e['data']['text'] for e in observed if e['event']=='text')==gen['reply']==result['reply']
            assert gen['request']['messages'][-1]==cog['request']['messages'][-1]=={'role':'user','content':text}
            assert cog['request']['messages'][1:]==gen['request']['messages'][1:-1][-6:]+gen['request']['messages'][-1:]
            ids=result['conversation'];u=messages[ids['user_message_id']];a=messages[ids['assistant_message_id']]
            assert u['content']==text and u['role']=='user' and a['content']==result['reply'] and a['role']=='assistant'
            assert u['session_id']==a['session_id']==ids['session_id']==workers[turn['app_pid']]['readiness']['session_id']
            public={r['id']:r for r in turn['conversation']['body']['data']['items']};assert public[u['id']]['text']==text and public[a['id']]['text']==a['content']
            # Preparation is same-instance in both arms and must itself receive
            # the first completed pair, avoiding a broken positive control.
            expected=[]
            if index==1 or index==2 and arm=='recovered_restart':
                for t in group['turns'][:index]:expected.extend([{'role':'user','content':t['input']},{'role':'assistant','content':t['result']['reply']}])
            assert gen['request']['messages'][1:-1]==expected
        third=generations[-1]['request']['messages'];assert third==group['probe_messages']
        assert group['history_role_messages_verified']==(4 if arm=='recovered_restart' else 0)
        needles=case.get('source_answers',[case['expected']] if 'expected' in case else [])
        leaks=[{'needle':v,'role':m['role']} for v in needles for m in third[:1]+third[-1:] if v in m['content']]
        assert leaks==group['nonhistory_source_answer_occurrences'] and group['history_only_isolation_passed']==(not leaks)
        score=grade(group['turns'][-1]['result']['reply'],case);assert score==group['grade']
        assert not final['memory_reminders'] and not final['memory_action_receipts']
        if arm=='recovered_restart':
            aid=group['turns'][-1]['result']['conversation']['assistant_message_id'];deps={r['source_id'] for r in final['memory_response_context'] if r['message_id']==aid and r['source_type']=='message'}
            assert set(messages)-{aid}<=deps
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        try:
            conn.executescript((folder/(case['id']+'-'+arm)/'database_dump.sql').read_text())
            for name,expected_rows in final.items():
                actual=[dict(r) for r in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')]
                assert Counter(normalized(r) for r in actual)==Counter(normalized(r) for r in expected_rows)
        finally:conn.close()
        summaries.append({'case':case['id'],'arm':arm,'strict_correct':score['correct'],'source_role_count':group['history_role_messages_verified'],'isolated':not leaks,
            'reply':group['turns'][-1]['result']['reply'],'sql_export_roundtrip':True});allrows.extend(rows);turn_count+=3
    assert turn_count==36 and len(allrows)==72 and allrows==data['requests'][2:]
    metrics={arm:{'cases':6,'strict_correct':sum(s['strict_correct'] for s in summaries if s['arm']==arm),'isolated_pairs':sum(s['isolated'] for s in summaries if s['arm']==arm)} for arm in protocol['arms']}
    assert metrics==data['metrics']
    result={'verified':True,'evaluation_sha256':digest(path),'freeze_sha256':EXPECTED,'historical_inputs':len(frozen['sha256']),
        'verifier_sha256':digest(Path(__file__)),'model_id':data['model_id'],'app_turns':36,'app_processes':24,'native_calls':74,
        'actual_worker_module_counts':dict(Counter(runtime_counts)),'gpu':provider['chosen_gpu'],'gpu_allocations_mib':provider['process_gpu_mib_after_load'],
        'actual_llm_or_gpu':True,'exact_raw_sender_wire_schema_native_trace_verified':True,'metrics':metrics,'probe_summaries':summaries,
        'all_results_and_sql_api_stable_sources_bound':True,'general_semantics_or_human_validation_claim':False}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Verified',data['model_id'],'36 turns,24 clean apps,74 native calls and byte-exact SDK/SQL history contrast.',metrics)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();verify(args.evidence,args.output)

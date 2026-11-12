"""Post-hoc native wire/SQL/routing/timing and no-regression recomputation."""
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
from analysis_cost_common import ROOT,BASE,OLD30,PROTOCOL,REGISTRY,digest,verify_historical_binding
sys.path.insert(0,str(OLD30));sys.path.insert(0,str(BASE.parent/'cycle-29/审计'));sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'src'))
from run_readonly_analysis_cost import validate_native_calls,calculate_pairs,grade,ARMS
from run_native_context_use import parse_wire
from readonly_analysis_candidate import decide
from run_context_baseline import events
from verify_context_baseline import normalized
from evaluate_native_output_audit import validate_provider_identity
EXPECTED='c92e846a8618e2306ac0e37cc141adaece9d24d0276362ce90d2f3873e265cb9'


def read(p):return json.loads(p.read_text())
def verify(path,out):
    assert path.resolve().is_relative_to(BASE/'实验') and out.resolve().is_relative_to(BASE/'审计') and not out.exists()
    folder=path.parent;data=read(path);fp=ROOT/'evals/interaction/cycle-31/readonly-analysis-cost-freeze.json';frozen=read(fp)
    assert digest(fp)==EXPECTED==data['freeze_sha256'] and data['frozen_inputs']==frozen
    assert data['completed'] and data['engineering_passed'] and data['cleanup_passed'] and data['failure'] is None and not data['cleanup_errors']
    assert data['production_activation_authorized'] is False and data['semantic_approved'] is False and data['actual_llm_or_gpu'] is True
    verify_historical_binding(frozen)
    for name,value in frozen['sha256'].items():assert digest(ROOT/name)==value
    git=lambda ref,name:subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)
    assert sha256(git(data['head'],str(fp.relative_to(ROOT)))).hexdigest()==EXPECTED
    protocol=json.loads(git(frozen['source_ref'],PROTOCOL));provider=data['provider_ready']
    validate_provider_identity(provider,{'models_registry':REGISTRY,'models_registry_sha256':frozen['sha256'][REGISTRY],'provider_backend':'cuda'})
    assert provider['pid']==data['provider_pid'] and provider['model_id']==data['model_id']
    assert provider['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py'] and provider['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
    assert data['provider_exit']==0 and not data.get('provider_forced_cleanup') and not any(line.split(',')[0].strip()==str(data['provider_pid']) for line in data['gpu_processes_after'].splitlines())
    trace=folder/'provider-trace.jsonl';assert digest(trace)==data['native_trace_sha256'];native=[json.loads(line) for line in trace.read_text().splitlines()];validate_native_calls(data,native)
    workers={w['pid']:w for w in data['workers']};assert len(workers)==96;all_analysis=[]
    for worker in workers.values():
        assert worker['exit_code']==0 and not worker['forced_cleanup'] and worker['analysis_runtime_verified']
        runtime=read(folder/worker['runtime_file']);assert runtime['pid']==worker['pid'] and runtime['failure'] is None and runtime['recover_context'] is True
        assert runtime['actual_llm_or_gpu'] is True and runtime['audit_analysis_arm']==worker['analysis_arm'] and runtime['audit_timing_hooks'] is False
        assert runtime['audit_analysis_rows']==worker['analysis_rows']
        for row in runtime['module_sources'].values():assert frozen['sha256'][str(Path(row['path']).relative_to(ROOT))]==row['sha256']
        if worker['analysis_arm']==ARMS[1]:
            candidate=runtime['audit_candidate_source'];assert frozen['sha256'][str(Path(candidate['path']).relative_to(ROOT))]==candidate['sha256'] and runtime['audit_analysis_hook'] is True
        else:assert runtime['audit_candidate_source'] is None and runtime['audit_analysis_rows']==[] and runtime['audit_analysis_hook'] is False
        all_analysis.extend(runtime['audit_analysis_rows'])
    schedule=[(rep,c,arm) for rep,orders in enumerate(protocol['case_arm_orders'],1) for c,order in zip(protocol['cases'],orders,strict=True) for arm in order]
    combined=[];summaries=[]
    for group,(rep,case,arm) in zip(data['cases'],schedule,strict=True):
        assert group['complete'] and group['repetition']==rep and group['case_id']==case['id'] and group['arm']==arm and len(group['turns'])==3
        pids=[t['app_pid'] for t in group['turns']];assert pids[0]==pids[1]!=pids[2] and all(workers[pid]['case']==group['id'] for pid in pids)
        rows=[parse_wire(row) for row in group['model_requests']];gen=[r for r in rows if r['kind']=='generation'];assert len(gen)==3
        references={}
        for ref in group['snapshots']:
            target=folder/ref['file'];assert digest(target)==ref['sha256'];references[ref['label']]=read(target)
        state=references['final'];sql={r['id']:r for r in state['memory_messages']};assert len(sql)==6
        audit=[row for w in data['workers'] if w['case']==group['id'] for row in w['analysis_rows']]
        assert audit==group['analysis_rows'] and len(audit)==(3 if arm==ARMS[1] else 0)
        for index,(turn,text,generation) in enumerate(zip(group['turns'],case['turns'],gen,strict=True)):
            assert turn['input']==text and turn['terminal']=='result' and turn['result']['generation_mode']=='llm'
            kind,result,observed,raw=events(BytesIO(turn['raw_sse'].encode()),time.perf_counter());assert kind=='result' and result==turn['result'] and raw==turn['raw_sse']
            assert [(e['event'],e['id'],e['data']) for e in observed]==[(e['event'],e['id'],e['data']) for e in turn['events']]
            assert ''.join(e['data']['text'] for e in observed if e['event']=='text')==generation['reply']==result['reply']
            ids=result['conversation'];u=sql[ids['user_message_id']];a=sql[ids['assistant_message_id']]
            assert (u['role'],u['content'])==('user',text) and (a['role'],a['content'])==('assistant',result['reply'])
            assert u['session_id']==a['session_id']==workers[turn['app_pid']]['readiness']['session_id']==ids['session_id']
            public={m['id']:m for m in turn['conversation']['body']['data']['items']};assert public[u['id']]['text']==text and public[a['id']]['text']==a['content']
            expected=[]
            for previous in group['turns'][:index]:expected.extend([{'role':'user','content':previous['input']},{'role':'assistant','content':previous['result']['reply']}])
            assert generation['request']['messages'][1:]==expected+[{'role':'user','content':text}]
            cog=[r for r in rows if r['kind']=='cognitive' and r['request']['messages'][-1]['content']==text]
            skipped=result['analysis_mode']=='lab_readonly_context_rules'
            assert len(cog)==(0 if skipped else 1)
            if skipped:assert index==2 and arm==ARMS[1] and case['candidate_probe_eligible']
            else:
                assert result['analysis_mode']=='llm' and cog[0]['request']['messages'][1:]==expected[-6:]+[{'role':'user','content':text}]
            if arm==ARMS[1]:
                observation=audit[index];decision=decide(text,history=expected[-6:],scope=result['speaker_attribution']['scope'],risk=None)
                assert observation['input']==text and observation['current_user_source_id']==u['id'] and observation['history_role_count']==len(expected[-6:])
                assert observation['decision']==decision and observation['decision']['eligible']==skipped and observation['delegates_original']==(not skipped)
            start=turn['client_submit_started_ns'];end=turn['client_terminal_ns'];assert type(start) is int and type(end) is int and end>start
            assert turn['submit_to_terminal_seconds']==(end-start)/1e9
            # Full native response generation is inside the source-bound client
            # interval; progress persistence and conversation API follow it.
            relevant=[generation]+cog;native_by_id={r['id']:r for r in native};total=sum(native_by_id[r['provider_call_id']]['total_seconds'] for r in relevant)
            assert total<=turn['submit_to_terminal_seconds']+.01
        assert group['probe_messages']==gen[-1]['request']['messages'] and group['history_role_messages_verified']==4
        actual_skipped=group['turns'][-1]['result']['analysis_mode']=='lab_readonly_context_rules';assert actual_skipped==group['probe_skipped'] and len(rows)==6-int(actual_skipped)
        assert group['grade']==grade(group['turns'][-1]['result']['reply'],case,protocol)
        assert not state['memory_reminders'] and not state['memory_action_receipts'] and state['memory_context_revision'][0]['revision']==0
        aid=group['turns'][-1]['result']['conversation']['assistant_message_id'];deps={r['source_id'] for r in state['memory_response_context'] if r['message_id']==aid and r['source_type']=='message'};assert set(sql)-{aid}<=deps
        profile={f['profile_key']:f['content'] for f in state['memory_fragments'] if f.get('profile_key') and f['status']=='active'}
        assert profile==group['profile'] and sorted([f['memory_type'],f['category'],f['content'],f['status']] for f in state['memory_fragments'])==group['facts_signature']
        if case.get('expected_profile_name'):
            assert any(case['expected_profile_name'] in v for v in profile.values()) and any(r['source_message_id']==5 and case['expected_profile_name'] in r['evidence'] for r in state['memory_sources'])
        conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        try:
            conn.executescript((folder/group['id']/'database_dump.sql').read_text())
            for name,expected_rows in state.items():
                actual=[dict(r) for r in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')]
                assert Counter(normalized(r) for r in actual)==Counter(normalized(r) for r in expected_rows)
        finally:conn.close()
        combined.extend(rows);summaries.append({'repetition':rep,'case':case['id'],'arm':arm,'probe_skipped':actual_skipped,'strict':bool(group['grade']['correct']),'probe_reply':group['turns'][-1]['result']['reply'],'probe_seconds':group['turns'][-1]['submit_to_terminal_seconds'],'sql_all_tables_roundtrip':True})
    assert combined==data['requests'][2:] and len(summaries)==48 and len(all_analysis)==72
    comparison=calculate_pairs(data,protocol);assert comparison==data['comparison']
    result={'verified':True,'evaluation_sha256':digest(path),'verifier_sha256':digest(Path(__file__)),'freeze_sha256':EXPECTED,
        'historical_inputs':len(frozen['sha256']),'model_id':data['model_id'],'actual_native_cuda':True,'app_turns':144,'app_processes':96,
        'native_calls':len(native),'candidate_probe_skips':sum(s['probe_skipped'] for s in summaries),'native_wire_and_schema_bound':True,
        'routing_decisions_recomputed':72,'sql_sse_api_sources_and_timing_bound':True,'comparison':comparison,'summaries':summaries,
        'general_speed_or_semantic_or_human_approval':False}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Verified',data['model_id'],'144 turns/96 OS,',len(native),'native calls;quality',comparison['quality_gate_passed'],'median improvement',comparison['median_relative_improvement'])


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--evidence',required=True,type=Path);p.add_argument('--output',required=True,type=Path);args=p.parse_args();verify(args.evidence,args.output)

"""Post-hoc source/raw SDK/SSE/SQL and independent eight-workflow assertions."""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import time
from context_baseline_common import ROOT,BASE,digest
from run_context_baseline import events
from verify_context_baseline import normalized
EXPECTED='be2792f90803bb4e6bbf87fca747d544f947c66d2dc2f3f23bd3f6858933dfed'


def read(path):return json.loads(path.read_text())
def verify():
    folder=BASE/'实验/context-fault-controls-v3';data=read(folder/'faults.json')
    freeze_path=ROOT/'evals/interaction/cycle-29/context-fault-controls-v3-freeze.json';frozen=read(freeze_path)
    assert digest(freeze_path)==EXPECTED==data['freeze_sha256'] and frozen==data['frozen_inputs']
    assert data['completed'] and data['failure'] is None and not data['cleanup_errors'] and data['actual_llm_or_gpu'] is False
    git=lambda ref,name:subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)
    for name,value in frozen['sha256'].items():assert sha256(git(frozen['source_ref'],name)).hexdigest()==value
    assert sha256(git(data['head'],str(freeze_path.relative_to(ROOT)))).hexdigest()==EXPECTED
    protocol=json.loads(git(frozen['source_ref'],'evals/interaction/cycle-29/context-fault-controls-protocol.json'))
    workers={w['pid']:w for w in data['workers']};assert len(workers)==20
    for worker in workers.values():
        assert worker['exit_code']==0 and not worker['forced_cleanup']
        runtime=read(folder/worker['runtime_file']);assert runtime['pid']==worker['pid'] and runtime['failure'] is None
        assert runtime['actual_llm_or_gpu'] is False and runtime['audit_timing_hooks'] is False
        assert runtime['recover_context']==worker['recover_context']==(worker['case']!='optout')
        for row in runtime['module_sources'].values():assert frozen['sha256'][str(Path(row['path']).relative_to(ROOT))]==row['sha256']
        assert worker['runtime_modules_bound']==len(runtime['module_sources'])
    turns=[];calls=[];derived={};summaries=[]
    for case,expected in zip(data['cases'],protocol['cases'],strict=True):
        assert case['id']==expected['id'] and case['complete'] and len(case['turns'])==expected['submitted_turns']
        assert sum(w['case']==case['id'] for w in workers.values())==expected['app_processes']
        rows=case['model_requests'];gen={};cog={}
        for row in rows:
            assert row['actual_llm_or_gpu'] is False and row['outcome'] in ('completed','client_closed')
            assert json.loads(row['raw_request_json'])==row['request'] and sha256(row['raw_request_json'].encode()).hexdigest()==row['request_sha256']
            request=row['request'];assert request['model']=='c29-controlled';text=request['messages'][-1]['content']
            assert request['messages'][-1]['role']=='user'
            (gen if row['kind']=='generation' else cog).setdefault(text,[]).append(row)
            if request.get('stream'):
                chunks=[json.loads(line[6:]) for line in row['raw_http_body'].splitlines() if line.startswith('data: ') and line!='data: [DONE]']
                assert ''.join(c['choices'][0]['delta'].get('content','') for c in chunks)==row['reply']
            else:assert json.loads(row['raw_http_body'])['choices'][0]['message']['content']==row['reply']
            if row['kind']=='generation':assert not request.get('response_format')
            else:
                assert request['response_format']['json_schema']['name']=='avatar_cognitive_analysis'
                assert request['messages'][1:]==[{'role':'user','content':text}]
        for turn in case['turns']:
            assert turn['app_pid'] in workers and workers[turn['app_pid']]['case']==case['id']
            kind,result,observed,raw=events(BytesIO(turn['raw_sse'].encode()),time.perf_counter())
            assert kind==turn['terminal'] and result==turn['result'] and raw==turn['raw_sse']
            assert [(e['event'],e['id'],e['data']) for e in observed]==[(e['event'],e['id'],e['data']) for e in turn['events']]
            if kind=='result':
                public={m['id']:m for m in turn['conversation']['body']['data']['items']};ids=result['conversation']
                assert public[ids['user_message_id']]['text']==turn['input'] and public[ids['assistant_message_id']]['text']==result['reply']
                assert ids['session_id']==workers[turn['app_pid']]['readiness']['session_id']
                if result['generation_mode']=='llm':
                    native=gen[turn['input']];assert len(native)==1 and native[0]['reply']==result['reply']
                    assert ''.join(e['data']['text'] for e in observed if e['event']=='text')==result['reply']
            else:assert kind=='cancelled' and case['id']=='cancel'
        snapshots={}
        for ref in case['snapshots']:
            path=folder/ref['file'];assert digest(path)==ref['sha256'];snapshots[ref['label']]=read(path)
        final=snapshots['final'];conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
        try:
            conn.executescript((folder/case['id']/'database_dump.sql').read_text())
            for name,expected_rows in final.items():
                actual=[dict(r) for r in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')]
                assert Counter(normalized(r) for r in actual)==Counter(normalized(r) for r in expected_rows)
        finally:conn.close()
        derived[case['id']]={'case':case,'generations':gen,'cognitive':cog,'snapshots':snapshots,'final':final}
        summaries.append({'case':case['id'],'submitted':len(case['turns']),'model_calls':len(rows),'workers':expected['app_processes'],'sql_all_tables_roundtrip':True})
        turns.extend(case['turns']);calls.extend(rows)
    assert len(turns)==45 and Counter(t['terminal'] for t in turns)=={'result':44,'cancelled':1} and len(calls)==78
    checks=[]
    def check(name,condition):assert condition,name;checks.append(name)
    def roles(d,text):return d['generations'][text][0]['request']['messages'][1:]
    p=derived['privacy_crosssession'];t=p['case']['turns'];s=p['snapshots'];aid=t[1]['result']['conversation']['assistant_message_id']
    oldids=set(t[0]['result']['conversation'][k] for k in ('user_message_id','assistant_message_id'))
    linked={r['source_id'] for r in s['recovered-crosssession']['memory_response_context'] if r['message_id']==aid and r['source_type']=='message'}
    check('crosssession_sources',oldids<=linked and t[0]['app_pid']!=t[1]['app_pid'] and 'C29PRIVATE' in t[1]['result']['reply'])
    erased=s['forget-private-after'];check('derived_redaction',next(r for r in erased['memory_messages'] if r['id']==aid)['content']=='[redacted]' and not any(r['message_id']==aid for r in erased['memory_chat_results']))
    check('privacy_all_messages',all('C29PRIVATE' not in m['content'] for turn in t[2:] for r in p['generations'][turn['input']] for m in r['request']['messages']))
    check('same_service_and_restart_new_pair',any(m['content']==t[2]['input'] for m in roles(p,t[3]['input'])) and any(m['content']==t[2]['result']['reply'] for m in roles(p,t[4]['input'])))
    p=derived['scope'];t=p['case']['turns'];check('fiction_fence',not any('C29REAL' in m['content'] for m in roles(p,t[2]['input'])))
    check('fiction_action_blocked',t[3]['result']['speaker_tool_blocked'] and t[3]['result']['reminder'] is None)
    check('fiction_os_recovery',t[3]['app_pid']!=t[4]['app_pid'] and any('C29FICTION' in m['content'] for m in roles(p,t[4]['input'])))
    check('real_fence',not any('C29FICTION' in m['content'] for m in roles(p,t[6]['input'])))
    texts=[r['content'] for r in p['final']['memory_fragments']]
    check('real_profile_positive_no_fiction',not any('虚构甲' in x for x in texts) and any('真实乙' in x for x in texts))
    check('real_action_positive',len(p['final']['memory_reminders'])==1 and t[8]['result']['reminder'] is not None)
    p=derived['cancel'];t=p['case']['turns'];check('actual_cancel',t[1]['terminal']=='cancelled' and t[1]['cancel_response']['status']==200 and any(r.get('released_after_explicit_cancel') for r in p['case']['model_requests']))
    check('cancel_gap',t[1]['app_pid']!=t[2]['app_pid'] and not any('C29_CANCEL' in m['content'] or 'C29SAFE' in m['content'] for m in roles(p,t[2]['input'])))
    check('post_cancel_pair',any('C29AFTERCANCEL' in m['content'] for m in roles(p,t[3]['input'])))
    p=derived['corrupt_result'];t=p['case']['turns'];check('explicit_corruption',any(r['result_json']=='{not-json' for r in p['snapshots']['invalid-result-json-after']['memory_chat_results']))
    check('corrupt_gap_and_valid_suffix',not any('C29CORRUPT' in m['content'] for m in roles(p,t[1]['input'])) and any('C29VALID' in m['content'] for m in roles(p,t[2]['input'])))
    p=derived['mixed_writer'];t=p['case']['turns'];guard=t[1]['result'];check('unknown_no_model',guard['speaker_attribution']['scope']=='unverified' and not guard['speaker_attribution']['persistent_facts_allowed'] and not guard['speaker_attribution']['turn_tools_allowed'] and guard['generation_mode']=='rules_speaker_scope' and t[1]['input'] not in p['generations'] and t[1]['input'] not in p['cognitive'])
    check('unknown_canonical_fence',not any('C29UNTRACKED' in m['content'] or 'C29TRACKED' in m['content'] for m in roles(p,t[3]['input'])))
    p=derived['bounded_window'];t=p['case']['turns']
    for index in (12,13):
        r=roles(p,t[index]['input']);users=[m['content'] for m in r if m['role']=='user']
        check('bounded_window_'+str(index),len(r)==19 and [m['role'] for m in r]==['user','assistant']*9+['user'] and len(users)==len(set(users)) and t[index]['app_pid']!=t[index-1]['app_pid'])
    p=derived['no_old_actions'];t=p['case']['turns'];s=p['snapshots'];check('idle_actions_unchanged',s['old-action']['memory_reminders']==s['after-idle-restart']['memory_reminders'])
    check('old_request_not_reexecuted',len(s['ordinary-no-replay']['memory_reminders'])==1 and t[1]['result']['reminder'] is None and t[1]['result']['tool_calls']==[] and any(m['content']==t[0]['input'] for m in roles(p,t[1]['input'])))
    check('new_action_positive',t[2]['result']['reminder']['id']!=t[0]['result']['reminder']['id'] and len(p['final']['memory_reminders'])==2)
    p=derived['optout'];t=p['case']['turns'];check('optout_with_sql',t[0]['app_pid']!=t[1]['app_pid'] and not any('C29OPTOUTOLD' in m['content'] for m in roles(p,t[1]['input'])) and len(p['final']['memory_messages'])==4)
    assert all(c['passed'] for case in data['cases'] for c in case['checks']) and sum(len(c['checks']) for c in data['cases'])==25
    result={'verified':True,'raw_sha256':digest(folder/'faults.json'),'verifier_sha256':digest(Path(__file__)),'freeze_sha256':EXPECTED,
        'historical_inputs':len(frozen['sha256']),'current_frozen_inputs_match':all(digest(ROOT/n)==v for n,v in frozen['sha256'].items()),
        'submitted':45,'results':44,'cancelled':1,'clean_worker_processes':20,'controlled_model_http_calls':78,
        'controller_checks':25,'independent_assertions':checks,'summaries':summaries,'actual_llm_or_gpu':False,'natural_race_or_general_semantics_claim':False}
    out=BASE/'审计/工作目录/003-独立进程故障边界/独立八场景核验.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Verified8 workflows,45 real HTTP/SSE submissions,78 controlled SDK calls,20 source-bound clean app processes; independent assertions',len(checks))


if __name__=='__main__':verify()

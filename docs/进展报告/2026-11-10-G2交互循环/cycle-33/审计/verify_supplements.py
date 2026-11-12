"""Independent HTTP fault, original-instruction and per-group Git provenance audit."""
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3
import subprocess
from shared_affect_common import ROOT,BASE,digest
from verify_shared_affect import parse_events


def read(path):return json.loads(path.read_text())


def main():
    work=BASE/'审计/工作目录';fault=work/'004-遗忘与取消情绪状态补审';data=read(fault/'controlled-http-state.json');assert data['completed'] and data['failure'] is None and len(data['cases'])==6
    plan=read(fault/'补审方案.json');version=read(fault/'执行版本.json')
    assert version['evidence_sha256']==digest(fault/'controlled-http-state.json')
    for name,value in plan['source_sha256'].items():
        assert digest(ROOT/name)==value and sha256(subprocess.check_output(['git','show',plan['source_ref']+':'+name],cwd=ROOT)).hexdigest()==value
    assert sha256(subprocess.check_output(['git','show',version['source_ref']+':'+str((BASE/'审计/probe_live_emotion_cpu.py').relative_to(ROOT))],cwd=ROOT)).hexdigest()==version['helper_sha256']
    turns=0;cancelled=0;fault_rows=[];sql_out=fault/'复核SQL';sql_out.mkdir(exist_ok=True)
    for row in data['cases']:
        assert row['complete'] and len(row['turns'])==2
        emotion_http=[json.loads(item['raw_response'])['data'] for item in row['http'] if item['route']=='/emotion'];expected=[row['initial_emotion']]
        if row['case']=='forget_completed_source':expected.append(row['before_boundary_emotion'])
        expected.extend([row['after_boundary_emotion'],row['after_neutral_emotion']]);assert emotion_http==expected
        for turn in row['turns']:
            events=parse_events(turn['raw_sse']);assert events==[{key:event[key] for key in ('event','id','data')} for event in turn['events']]
            assert events[-1]['event']==turn['terminal'] and events[-1]['data']==turn['result'];turns+=1;cancelled+=int(turn['terminal']=='cancelled')
        state=row['sql_after_boundary']
        if row['case']=='forget_completed_source':assert state['revision']==1 and next(m for m in state['memory_messages'] if m['id']==row['boundary_control']['source_message_id'])['content']=='[redacted]'
        else:assert row['turns'][0]['terminal']=='cancelled' and state['revision']==0 and state['memory_chat_results']==[] and not any(m['role']=='assistant' for m in state['memory_messages'])
        after=row['after_boundary_emotion'];neutral=row['after_neutral_emotion']
        assert after['user_observation']=={'valence':-.4,'arousal':.3} and any(abs(value)>1e-9 for value in after['automatic'].values())
        assert neutral['user_observation']=={'valence':0,'arousal':0} and any(abs(value)>1e-9 for value in neutral['automatic'].values())
        path=Path(row['owned_runtime_dir'])/'owned.db';assert path.resolve().is_relative_to((ROOT.parent/'runtime/tmp').resolve()) and path.parent.name.startswith('c33-context-')
        with closing(sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)) as conn:
            conn.row_factory=sqlite3.Row;actual={'revision':conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]}
            for name in row['sql_after_neutral']:
                if name!='revision':actual[name]=[dict(result) for result in conn.execute('SELECT * FROM '+name)]
            assert actual==row['sql_after_neutral'];dump='\n'.join(conn.iterdump())+'\n'
        saved=sql_out/(str(row['repetition'])+'-'+row['case']+'.sql')
        with saved.open('x') as out:out.write(dump)
        result=row['turns'][-1]['result'];aid=result['conversation']['assistant_message_id'];assert json.loads(next(item['result_json'] for item in actual['memory_chat_results'] if item['message_id']==aid))==result
        deps=[item['source_id'] for item in actual['memory_response_context'] if item['message_id']==aid and item['source_type']=='message']
        fault_rows.append({'case':row['case'],'repetition':row['repetition'],'verified':True,'new_reply_source_ids':deps,'archived_sql_sha256':digest(saved)})
    assert turns==12 and cancelled==3
    instruction=work/'002-工作约定去重';before=read(instruction/'整理前测量.json');after=read(instruction/'整理后核验.json');binding=read(instruction/'整理版本绑定.json')
    assert digest(instruction/'AGENTS-整理前.md')==before['before_sha256']==after['before_sha256']
    original=subprocess.check_output(['git','show',before['source_ref']+':AGENTS.md'],cwd=ROOT);rewritten=subprocess.check_output(['git','show',binding['after_git_ref']+':AGENTS.md'],cwd=ROOT)
    assert sha256(original).hexdigest()==before['before_sha256'] and sha256(rewritten).hexdigest()==after['after_sha256']==binding['after_sha256']
    current=(ROOT/'AGENTS.md').read_text();tail=current[current.index('## 一、项目是什么'):];assert sha256(tail.encode()).hexdigest()==before['project_reference_section_sha256']
    correction=work/'005-运行中快照误入暂存';record=read(correction/'纠正与原快照清单.json');assert read(correction/'checkpoint-evaluation.json')['completed'] is False
    for name,value in record['introduced_paths'].items():assert sha256(subprocess.check_output(['git','show',record['source_ref']+':'+name],cwd=ROOT)).hexdigest()==value['sha256']
    for copied in record['immutable_copies']:
        name=Path(copied).name.removeprefix('checkpoint-');source=str(BASE.relative_to(ROOT))+'/实验/shared-affect-32b/'+name;assert digest(ROOT/copied)==record['introduced_paths'][source]['sha256']
    history=subprocess.check_output(['git','log','--format=%H%x09%s','7cbb7b2..HEAD'],cwd=ROOT,text=True);commits=[]
    for line in history.splitlines():
        commit,subject=line.split('\t',1);match=re.match(r'docs\(experiment\): retain(4B|32B) (r[123]_[a-z0-9_-]+) ',subject)
        if not match:continue
        label,group=match.groups();relative=str(BASE.relative_to(ROOT))+'/实验/shared-affect-'+label.lower()+'/'+group+'/group-completed.json'
        raw=subprocess.check_output(['git','show',commit+':'+relative],cwd=ROOT);assert json.loads(raw)==read(ROOT/relative)
        commits.append({'model':label,'group':group,'commit':commit,'group_sha256':sha256(raw).hexdigest()})
    assert len(commits)==96 and len({(row['model'],row['group']) for row in commits})==96 and sum(row['model']=='4B' for row in commits)==48
    result={'verified':True,'controlled_http_submissions':turns,'results':turns-cancelled,'cancelled':cancelled,'independent_sql_checks':6,'forget_retention_reproductions':3,'cancel_retention_observations_not_classified_as_contract_failures':3,
        'fault_rows':fault_rows,'instruction_original_and_historical_rewrite_verified':True,'original_project_reference_bytes_retained':True,'incomplete_checkpoint_preserved_and_not_final':True,
        'individual_group_commits_verified':96,'commits':commits,'new_native_model_calls':0,'human_experience_proved':False}
    with (work/'补审与版本管理独立核验.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    print('Verified12 controlled HTTP submissions=9results/3cancels,6 actual SQL states,3 forget defects vs3 cancel behavior observations, original instruction history/checkpoint and96 distinct group commits; no new native calls.')


if __name__=='__main__':main()

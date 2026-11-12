"""Explicitly post-hoc descriptive role-state continuity from existing C33 data."""
import argparse
import json
from pathlib import Path
from shared_affect_common import ROOT,BASE,ARMS,digest


def main(args):
    work=BASE/'审计/工作目录/003-角色状态连续性补审';work.mkdir(exist_ok=True)
    evaluation=BASE/('实验/shared-affect-'+args.label+'/evaluation.json');report=json.loads(evaluation.read_text())
    proof=BASE/('审计/工作目录/001-共享历史隐含情绪/'+args.label+'-independent-binding.json');bound=json.loads(proof.read_text())
    assert report['completed'] and bound['verified'] and bound['evaluation_sha256']==digest(evaluation)
    cases={case['id']:case for case in report['cases']};workers={worker['case']:worker for worker in report['workers']};rows=[]
    for group in report['groups']:
        preparation=cases[group['preparation_case']];old=preparation['turns'][-1]['result'];previous={key:old[key] for key in ('valence','arousal','emotion','user_valence','user_arousal','user_emotion')}
        initial={arm:workers[group['probe_cases'][arm]]['initial_emotion'] for arm in ARMS}
        assert all(all(value==0 for value in state.values()) for state in initial.values())
        selected={arm:cases[group['probe_cases'][arm]] for arm in ARMS}
        for arm in ARMS:
            case=selected[arm];folder=evaluation.parent/group['id']/arm;source=json.loads((folder/'initial.json').read_text())
            assert len(source['memory_messages'])==4 and all(message['content']!='[redacted]' for message in source['memory_messages'])
            assert case['turns'][0]['result']['conversation']['revision']==old['conversation']['revision']==0
            assert case['probe_messages'][1:-1]==group['shared_role_messages']
        current=selected[ARMS[0]]['turns'][0]['result']
        rows.append({'group':group['id'],'stratum':group['stratum'],'previous_completed_result_character_state':previous,
            'probe_workers_initial_state':initial,'history_roles_recovered':4,'same_revision':0,
            'previous_character_pad_nonzero':old['valence']!=0 or old['arousal']!=0,
            'current_analysis_probe_user_observation':[current['user_valence'],current['user_arousal']],
            'current_analysis_probe_character_pad':[current['valence'],current['arousal']],
            'candidate_skipped':group['actual_candidate_skipped']})
    result={'scope':'post-hoc descriptive continuity audit of already collected C33 data, not a preregistered primary endpoint',
        'model_id':report['model_id'],'evaluation_sha256':digest(evaluation),'independent_binding_sha256':digest(proof),'new_model_or_app_calls':0,
        'groups':len(rows),'previous_nonzero_character_pad_groups':sum(row['previous_character_pad_nonzero'] for row in rows),
        'fresh_worker_initial_pad_zero_groups':len(rows),'history_preserved_but_pad_reinitialized_groups':sum(row['previous_character_pad_nonzero'] for row in rows),
        'current_analysis_probe_neutral_user_groups':sum(row['current_analysis_probe_user_observation']==[0,0] for row in rows),
        'current_analysis_probe_zero_character_pad_groups':sum(row['current_analysis_probe_character_pad']==[0,0] for row in rows),
        'rows':rows,'human_experience_or_semantic_harm_proved':False,'persisting_state_would_improve_quality_proved':False,
        'claim':'Source-backed completed role history is recovered across OS while in-memory PAD starts at0. This is a documented engineering limitation, not a new independently validated companion-quality defect.'}
    with (work/(args.label+'-posthoc-continuity.json')).open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    print(report['model_id'],'previous nonzero PAD',result['previous_nonzero_character_pad_groups'],'of',len(rows),'fresh role PAD0',len(rows),'same revision/history retained;descriptive only,no extra model calls.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True,choices=('4b','32b'));main(parser.parse_args())

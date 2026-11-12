"""Descriptive known-task results; no retrospective promotion/quality gate."""
import json
from pathlib import Path
from state_common import ROOT,BASE,FIXTURES,digest
from verify_state_replay import verify


def classify(reply):
    # Exhaustive observed-form labels, not a general arithmetic evaluator.
    if reply.strip()=='83':return 'correct_value_strict_format'
    if reply.strip() in ('37 + 46 = 83','46 + 37 = 83'):return 'correct_value_extra_formula_format_failure'
    if reply.strip()=='93':return 'incorrect_value_93'
    return 'unclassified_requires_review'


def main():
    work=BASE/'审计/工作目录/001-原生状态隔离';fixtures=json.loads((ROOT/FIXTURES).read_text());models=[]
    for label,fixture in zip(('4b','32b'),fixtures['models'],strict=True):
        path=work/('native-'+label)/'replay.json';proof=verify(path);data=json.loads(path.read_text());historical=json.loads((ROOT/fixture['source_evaluation']).read_text())
        old=[]
        for group in historical['cases']:
            if group['case_id']!='updated_material_total':continue
            reply=group['model_requests'][-1]['reply'];old.append({'group':group['id'],'repetition':group['repetition'],'arm':group['arm'],'reply':reply,'descriptive_label':classify(reply)})
        assert len(old)==6
        policies=[]
        for policy in data['policies']:
            targets=[r for r in policy['requests'] if r.get('source_ordinal')==5];assert len(targets)==6
            labels=[classify(r['reply']) for r in targets]
            assert 'unclassified_requires_review' not in labels
            policies.append({'policy':policy['state_policy'],'replies':[{'repetition':r['repetition'],'chain':r['chain'],'reply':r['reply'],'descriptive_label':classify(r['reply'])} for r in targets],
                'correct_value_count':sum(s.startswith('correct_value') for s in labels),'strict_only83_count':labels.count('correct_value_strict_format'),'incorrect93_count':labels.count('incorrect_value_93'),
                'unique_reply_count':len({r['reply'] for r in targets}),'within_repeat_equal':policy['observations']['within_repeat_equal'],'gpu':policy['provider_ready']['chosen_gpu'],'allocated_mib':policy['provider_ready']['process_gpu_mib_after_load']})
        models.append({'model_id':data['model_id'],'evaluation_sha256':digest(path),'seconds_including_all_evidence_collection':data['seconds'],'independent_reconstruction_passed':proof['passed'],
            'historical_gpu':fixture['source_gpu'],'current_gpu_uuid':data['same_gpu_uuid_across_policies'],'same_historical_gpu':fixture['source_gpu']['uuid']==data['same_gpu_uuid_across_policies'],
            'historical_backend_binary_identity_unproved':True,'historical_same_task_observations':old,'policies':policies})
    result={'scope':'descriptive known C31 regression replay, not independent quality acceptance','models':models,'native_calls':210,'target_generations':36,'avatar_or_sql_turns':0,
            'single_owned_provider_at_a_time':True,'root_cause_identified':False,'production_activation_authorized':False,'new_preregistered_semantic_or_latency_gate':False}
    with (work/'已知题状态策略描述汇总.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    print(json.dumps({'native_calls':210,'targets':36,'models':[{'model':m['model_id'],'policies':[(p['policy'],p['correct_value_count'],p['strict_only83_count'],p['incorrect93_count'],p['within_repeat_equal']) for p in m['policies']]} for m in models]},ensure_ascii=False))


if __name__=='__main__':main()

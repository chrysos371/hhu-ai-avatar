"""Bind same-agent whole-reply spans and observe exact paired prompt equality."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from context_native_common import ROOT,BASE,PROTOCOL,digest


def read(p):return json.loads(p.read_text())
def verify():
    work=BASE/'审计/工作目录/001-真实模型重启历史利用';pairs=[];reviews=[];native=[]
    for label in ('4b','32b'):
        path=BASE/('实验/native-context-'+label+'/evaluation.json');data=read(path);review_path=work/(label+'-source-aware-review.json');review=read(review_path);proof=read(work/(label+'-independent-binding.json'))
        assert proof['verified'] and proof['evaluation_sha256']==digest(path)==review['evaluation_sha256']
        assert review['model_id']==data['model_id'] and review['freeze_sha256']==data['freeze_sha256']
        assert review['reviewer']=='same_agent_source_aware_not_independent_human' and len(review['rows'])==36
        observations=[];groups={}
        for group in data['cases']:
            groups.setdefault(group['case_id'],{})[group['arm']]=group
            for index,turn in enumerate(group['turns']):observations.append((group,index,turn))
        for row,(group,index,turn) in zip(review['rows'],observations,strict=True):
            text=turn['result']['reply'];assert row['reply']==row['reviewed_span']['text']==text and row['input']==turn['input']
            assert row['case_id']==group['case_id'] and row['arm']==group['arm'] and row['turn_index']==index+1
            assert row['reply_sha256']==sha256(text.encode()).hexdigest() and row['source_ids']==turn['result']['conversation']
            assert row['reviewed_span']['start']==0 and row['reviewed_span']['end']==len(text)
            assert row['unsupported_external_action_claim_observed'] is False and row['new_body_experience_claim_observed'] is False
            assert row['probe_strict_grade']==(group['grade'] if index==2 else None)
        counts=Counter(row['judgment'] for row in review['rows'])
        assert counts=={'setup_statement_grounded_confirmation':24,'source_use_and_strict_task_correct':4,'appropriate_missing_context_abstention':5,'source_and_arithmetic_correct_but_numeric_only_format_failed':1,'appropriate_missing_information_abstention':2}
        for case_id,arms in groups.items():
            a=arms['optout_restart'];b=arms['recovered_restart'];prep=[t['result']['reply'] for t in a['turns'][:2]]==[t['result']['reply'] for t in b['turns'][:2]]
            system=a['probe_messages'][0]==b['probe_messages'][0];current=a['probe_messages'][-1]==b['probe_messages'][-1]
            pairs.append({'model':label,'case':case_id,'identical_preparation_texts':[t['input'] for t in a['turns'][:2]]==[t['input'] for t in b['turns'][:2]],
                'identical_preparation_replies':prep,'identical_third_system':system,'identical_current_message':current,
                'third_system_sha256_optout':sha256(a['probe_messages'][0]['content'].encode()).hexdigest(),
                'third_system_sha256_recovered':sha256(b['probe_messages'][0]['content'].encode()).hexdigest(),
                'role_history_counts':[a['history_role_messages_verified'],b['history_role_messages_verified']],
                'both_no_target_in_nonhistory_prompt':a['history_only_isolation_passed'] and b['history_only_isolation_passed'],
                'strict_scores':[a['grade']['correct'],b['grade']['correct']],
                'probe_replies':[a['turns'][-1]['result']['reply'],b['turns'][-1]['result']['reply']]})
        assert all(p['identical_preparation_texts'] and p['identical_current_message'] and p['both_no_target_in_nonhistory_prompt'] for p in pairs if p['model']==label)
        reviews.append({'model':label,'sha256':digest(review_path),'reviewed_app_replies':36,'judgments':dict(counts),'independent_human':False})
        trace=[json.loads(line) for line in (path.parent/'provider-trace.jsonl').read_text().splitlines()]
        cognitive=[r['total_seconds'] for r in trace if r['analysis']];generation=[r['total_seconds'] for r in trace[2:] if not r['analysis']]
        native.append({'model':label,'cognitive_calls':len(cognitive),'generation_calls_excluding_warmup':len(generation),'cognitive_native_seconds':sum(cognitive),
            'generation_native_seconds_excluding_warmup':sum(generation),'same_gpu_uuid':data['provider_ready']['chosen_gpu']['uuid'],
            'native_component_time_is_not_end_to_end_or_speedup':True})
    assert len(pairs)==12 and sum(r['reviewed_app_replies'] for r in reviews)==72
    result={'verified':True,'verifier_sha256':digest(Path(__file__)),'same_agent_reviews':reviews,'pairs':pairs,
        'identical_third_system_pairs':sum(p['identical_third_system'] for p in pairs),'identical_preparation_reply_pairs':sum(p['identical_preparation_replies'] for p in pairs),
        'all_target_isolation_and_current_message_controls_passed':True,'native_component_times_posthoc_not_preregistered_endpoint':native,
        'semantic_or_independent_human_approval':False}
    out=work/'双臂逐轮来源核验.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Bound72 same-agent reply spans and12 paired tasks; identical third-system pairs',result['identical_third_system_pairs'],'and identical prep-reply pairs',result['identical_preparation_reply_pairs'])


if __name__=='__main__':verify()

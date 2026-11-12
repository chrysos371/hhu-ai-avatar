"""Bind288 reviewed spans, all-turn denominators and supplementary guard evidence."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from analysis_cost_common import ROOT,BASE,digest
from run_readonly_analysis_cost import ARMS,percentile
import statistics


def read(p):return json.loads(p.read_text())
def verify():
    work=BASE/'审计/工作目录/001-只读分析路由保护';summaries=[];observed_cases={}
    for label in ('4b','32b'):
        path=BASE/('实验/readonly-cost-'+label+'/evaluation.json');data=read(path);proof=read(work/(label+'-independent-binding.json'))
        review_path=work/(label+'-source-aware-review.json');review=read(review_path);mix_path=work/(label+'-all-turn-mix-and-protections.json');mix=read(mix_path)
        assert proof['verified'] and proof['evaluation_sha256']==review['evaluation_sha256']==mix['evaluation_sha256']==digest(path)
        assert len(review['rows'])==144 and review['reviewer']=='same_agent_source_aware_not_independent_human'
        actual=[(c,i,t) for c in data['cases'] for i,t in enumerate(c['turns'])]
        for row,(case,index,turn) in zip(review['rows'],actual,strict=True):
            text=turn['result']['reply'];assert row['input']==turn['input'] and row['reply']==row['span']['text']==text
            assert row['reply_sha256']==sha256(text.encode()).hexdigest() and row['span']=={'start':0,'end':len(text),'text':text}
            assert (row['repetition'],row['case'],row['arm'],row['turn'])==(case['repetition'],case['case_id'],case['arm'],index+1)
            assert row['conversation']==turn['result']['conversation'] and row['strict_probe_grade']==(case['grade'] if index==2 else None)
            assert row['new_unsupported_external_action_observed'] is False and row['new_body_experience_observed'] is False
        counts=Counter(row['judgment'] for row in review['rows']);assert counts['provided_source_confirmation']==96 and counts['reasonable_identifier_alias_strict_target_ambiguous']==6
        assert counts['appropriate_missing_information_abstention']==6 and counts['provided_source_probe_content_correct']==30
        assert counts['content_arithmetic_correct_extra_formula']==(6 if label=='4b' else 3)
        assert counts['numeric_source_task_wrong_value']==(0 if label=='4b' else 3)
        for arm in ARMS:
            values=[t['submit_to_terminal_seconds'] for c in data['cases'] if c['arm']==arm for t in c['turns']]
            assert mix['all_turn_mix'][arm]=={'turns':72,'median_seconds':statistics.median(values),'mean_seconds':statistics.mean(values),'p95_seconds_linear':percentile(values,.95)}
        assert mix['mix_median_relative_improvement']==1-mix['all_turn_mix'][ARMS[1]]['median_seconds']/mix['all_turn_mix'][ARMS[0]]['median_seconds']
        assert len(mix['protected_all18_turn_observations'])==18
        for row in mix['protected_all18_turn_observations']:
            pair={c['arm']:c for c in data['cases'] if c['repetition']==row['repetition'] and c['case_id']==row['case']}
            results=[pair[arm]['turns'][row['turn']-1]['result'] for arm in ARMS]
            assert all({key:result[key] for key in row['values']}==row['values'] for result in results)
            assert row['analysis_modes']==[r['analysis_mode'] for r in results]
        for c in data['cases']:observed_cases[(label,c['repetition'],c['case_id'],c['arm'])]=c
        summaries.append({'model':label,'review_sha256':digest(review_path),'mixed_timing_sha256':digest(mix_path),'reply_spans':144,'judgments':dict(counts),
            'primary18_pairs':data['comparison']['latency'],'all72_turn_mix':mix['all_turn_mix'],'mix_median_relative_improvement':mix['mix_median_relative_improvement'],
            'raw_reply_gate':data['comparison']['quality_gate_passed'],'primary_bounded_gate':data['comparison']['bounded_performance_gate_passed']})
    alias=read(work/'箱子代号口径观察.json')
    for row in alias['rows']:
        c=observed_cases[('4b',row['repetition'],row['case_id'],row['arm'])];text=c['turns'][-1]['result']['reply'];assert text==row['reply']=='乙' and sha256(text.encode()).hexdigest()==row['reply_sha256'] and row['strict_grade']==c['grade']
    same=read(work/'32b-identical-input-different-replies.json');data=read(BASE/'实验/readonly-cost-32b/evaluation.json');assert same['evaluation_sha256']==digest(BASE/'实验/readonly-cost-32b/evaluation.json')
    trace={r['id']:r for r in [json.loads(l) for l in (BASE/'实验/readonly-cost-32b/provider-trace.jsonl').read_text().splitlines()]}
    for row in same['rows']:
        calls=row['calls'];assert calls[0]['raw_request_json']==calls[1]['raw_request_json'] and calls[0]['prompt_sha256']==calls[1]['prompt_sha256']
        for call in calls:
            native=trace[call['call_id']];assert call['prompt_sha256']==native['prompt_sha256'] and call['reply']==native['response']
            assert sha256(call['raw_request_json'].encode()).hexdigest()==call['request_sha256']==native['request_body_sha256']
            assert call['configuration']==data['provider_ready']['configuration']
        assert calls[0]['reply']=='93' and calls[1]['reply']=='37 + 46 = 83'
    supplement=read(work/'implicit-affect-whitebox-result.json');proto=ROOT/'evals/interaction/cycle-31/readonly-affect-whitebox-supplement.json'
    assert supplement['actual_llm_or_gpu'] is False and supplement['protocol_sha256']==digest(proto)
    assert supplement['candidate_sha256']==digest(BASE/'审计/readonly_analysis_candidate.py')
    assert len(supplement['rows'])==16 and supplement['conservative_expectation_mismatches']==12
    assert all(r['decision']['eligible'] and all(score==[0.0,0.0] for score in r['lexical_history_emotion_scores']) for r in supplement['rows'])
    result={'verified':True,'verifier_sha256':digest(Path(__file__)),'models':summaries,'reviewed_spans':288,'paired_same_wire_different_output_samples':3,
        'supplemental_synthetic_mismatches':12,'supplemental_controls':4,'supplement_actual_native_affect_regression_proved':False,
        'promotion_approved':False,'same_agent_reviews_not_independent_human':True}
    out=work/'来源审阅与补审汇总核验.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Bound288 reply spans,72-turn mixed metrics/model,36 protected turn observations,3 same-wire differences and16 supplementary synthetic classifications;promotion false.')


if __name__=='__main__':verify()

"""Post-experiment accounting and historical prompt lineage, no model execution."""
from collections import Counter
import json
from pathlib import Path
from native_common import ROOT,BASE,WORK,PROTOCOL,read,digest


def indexed(directory,phase,arm=None):
    requests=[json.loads(s) for s in (directory/'request-wire.jsonl').read_text().splitlines()]
    traces=[json.loads(s) for s in (directory/'provider-trace.jsonl').read_text().splitlines()]
    assert len(requests)==len(traces)
    return {(q['context']['repetition'],q['context']['case']):(q,r) for q,r in zip(requests,traces)
        if q['context']['phase']==phase and (arm is None or q['context'].get('arm')==arm)}


def main():
    output=BASE/'审计/工作目录/005-系统复核/catalogue-accounting.json';assert not output.exists()
    p=read(PROTOCOL);run=BASE/'实验/development-v1';report=read(run/'evaluation.json')
    verification=read(WORK/'development-verification.json');assert verification['verified']
    cases={c['id']:c for c in p['development_cases']};arms={};repeats=[]
    for arm in p['arms']:
        rows=[(cases[c['case']],c['arms'][arm]) for g in report['groups'] for c in g['cases']]
        arms[arm]={'task_score':sum(b['final_expected_task_outcome'] for _,b in rows),
            'native_calls':sum(b['model_used'] for _,b in rows),'framework_skips':sum(b['framework_skipped_model'] for _,b in rows),
            'origins':dict(Counter(b['reply_origin'] for _,b in rows)),
            'by_category':{category:{'total':sum(c['expected_outcome']==category for c,_ in rows),
                'task_correct':sum(c['expected_outcome']==category and b['final_expected_task_outcome'] for c,b in rows),
                'native_used':sum(c['expected_outcome']==category and b['model_used'] for c,b in rows),
                'explicit_verified_clarification':sum(c['expected_outcome']==category and b['reply_origin']=='verified_clarification' for c,b in rows),
                'wrong_policy_reads':sum(c['expected_outcome']==category and b['reply_origin']=='trusted_read_fixed' and b['final_tool']=='read_reminder_delivery_policy' for c,b in rows)}
                for category in ('read','avoid','clarify')}}
    for case in cases:
        for arm in p['arms']:
            responses=[next(c['arms'][arm] for c in g['cases'] if c['case']==case) for g in report['groups']]
            signatures=[json.dumps({k:b[k] for k in ('proposal','reply','reply_origin','final_expected_task_outcome')},ensure_ascii=False,sort_keys=True) for b in responses]
            repeats.append({'case':case,'arm':arm,'three_repeated_proposal_and_reply_identical':len(set(signatures))==1})
    current=indexed(run,'selection','full')
    old40=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-40/实验/native-wire-4b-sse-fixed'
    old41=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-41/实验/development-v1'
    lineage=[]
    for label,directory,phase in [('C40',old40,'selection'),('C41',old41,'initial')]:
        prior=indexed(directory,phase)
        comparisons=[]
        for key,(q,r) in prior.items():
            cq,cr=current[key]
            comparisons.append({'repetition':key[0],'case':key[1],
                'same_request_body_bytes':q['request_body_sha256']==cq['request_body_sha256'],
                'same_rendered_native_prompt':r['prompt_sha256']==cr['prompt_sha256'],
                'same_native_raw':r['response']==cr['response']})
        assert len(comparisons)==24
        lineage.append({'prior':label,'paired_reused_cases':24,'comparisons':comparisons,
            'request_hash_equal_count':sum(c['same_request_body_bytes'] for c in comparisons),
            'prompt_hash_equal_count':sum(c['same_rendered_native_prompt'] for c in comparisons),
            'raw_equal_count':sum(c['same_native_raw'] for c in comparisons)})
    result={'scope':'posthoc descriptive accounting only; no native/selection/rerouting/protected execution',
        'native_calls':0,'verification_sha256':digest(WORK/'development-verification.json'),
        'arm_accounting':arms,'deterministic_repeat_groups':repeats,'historical_lineage':lineage,
        'new_unseen_native_development_cases':2,'reused_native_development_cases':8,
        'rules_are_not_model_decisions':True,'score_does_not_certify_general_chat_quality':True,
        'analyzer_sha256':digest(__file__)}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Posthoc accounting:',{a:arms[a]['task_score'] for a in arms},'lineage',[(x['prior'],x['prompt_hash_equal_count'],x['raw_equal_count']) for x in lineage])


if __name__=='__main__':main()

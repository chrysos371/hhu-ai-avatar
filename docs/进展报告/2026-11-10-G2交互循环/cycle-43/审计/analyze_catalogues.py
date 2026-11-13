"""Posthoc category, repeated-input and C42-lineage accounting; no inference."""
from collections import Counter
import copy
import json
from pathlib import Path
from native_common import ROOT,BASE,WORK,PROTOCOL,read,digest

POLICY='read_reminder_delivery_policy'
STATE='read_reminder_state'


def indexed(directory,phase,arm):
    q=[json.loads(s) for s in (directory/'request-wire.jsonl').read_text().splitlines()]
    r=[json.loads(s) for s in (directory/'provider-trace.jsonl').read_text().splitlines()]
    assert len(q)==len(r)
    return {(a['context']['repetition'],a['context']['case']):(a,b) for a,b in zip(q,r)
        if a['context']['phase']==phase and a['context'].get('arm')==arm}


def main():
    output=BASE/'审计/工作目录/005-系统复核/catalogue-accounting.json';assert not output.exists()
    p=read(PROTOCOL);run=BASE/'实验/development-v1';report=read(run/'evaluation.json')
    proof=read(WORK/'development-verification.json');assert proof['verified']
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
                'wrong_policy_reads':sum(c['expected_outcome']==category and c.get('tool')!=POLICY and b['reply_origin']=='trusted_read_fixed' and b['final_tool']==POLICY for c,b in rows),
                'wrong_state_reads':sum(c['expected_outcome']==category and c.get('tool')!=STATE and b['reply_origin']=='trusted_read_fixed' and b['final_tool']==STATE for c,b in rows)}
                for category in ('read','avoid','clarify')}}
    assert [arms[a]['by_category']['read']['wrong_state_reads'] for a in p['arms']]==[1,1]
    assert [arms[a]['by_category']['clarify']['wrong_policy_reads'] for a in p['arms']]==[6,0]
    for case in cases:
        for arm in p['arms']:
            values=[]
            for group in report['groups']:
                b=next(c['arms'][arm] for c in group['cases'] if c['case']==case)
                value=copy.deepcopy({k:b[k] for k in ('proposal','reply','reply_origin','final_expected_task_outcome')})
                for call in (value['proposal'] or {}).get('tool_calls',[]):call['id']='<opaque-call-id>'
                values.append(json.dumps(value,ensure_ascii=False,sort_keys=True))
            repeats.append({'case':case,'arm':arm,'only_opaque_call_ids_normalized':True,'three_repetitions_identical':len(set(values))==1})
    baseline=indexed(run,'selection','baseline_complete');candidate=indexed(run,'selection','policy_grounded')
    olddir=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-42/实验/development-v1'
    previous=indexed(olddir,'selection','eligible_complete');lineage=[]
    for key,(q,r) in previous.items():
        cq,cr=baseline[key]
        lineage.append({'repetition':key[0],'case':key[1],
            'same_request_body_bytes':q['request_body_sha256']==cq['request_body_sha256'],
            'same_rendered_native_prompt':r['prompt_sha256']==cr['prompt_sha256'],
            'same_native_raw':r['response']==cr['response']})
    assert len(lineage)==18
    flips=[]
    for repetition in range(1,4):
        for arm,index in [('baseline_complete',baseline),('policy_grounded',candidate)]:
            q,r=index[repetition,'numbered-reference-channel']
            call=r['wire_message']['tool_calls'][0]['function']
            flips.append({'repetition':repetition,'arm':arm,'request_ordinal':q['ordinal'],
                'request_body_sha256':q['request_body_sha256'],'prompt_sha256':r['prompt_sha256'],
                'native_raw':r['response'],'function':call['name'],'arguments':json.loads(call['arguments']),
                'native_finish_reason':r['finish_reason'],'temperature':q['request']['temperature']})
    assert len({r['request_body_sha256'] for r in flips})==len({r['prompt_sha256'] for r in flips})==1
    assert Counter(r['function'] for r in flips)=={POLICY:4,STATE:2}
    result={'scope':'posthoc measured accounting; not model execution or causal explanation of output variation',
        'native_calls':0,'verification_sha256':digest(WORK/'development-verification.json'),
        'arm_accounting':arms,'repeat_groups':repeats,'C42_reused_native_pairs':lineage,
        'C42_request_SHA_equal':sum(r['same_request_body_bytes'] for r in lineage),
        'C42_prompt_SHA_equal':sum(r['same_rendered_native_prompt'] for r in lineage),
        'C42_native_raw_equal':sum(r['same_native_raw'] for r in lineage),
        'same_input_route_flip':flips,'route_flip_cause_established':False,
        'runtime_seed':read(run/'provider-ready.json')['configuration']['seed'],
        'reused_development_cases':10,'new_preregistered_development_cases':6,
        'protected_executed':False,'rules_are_not_model_decisions':True,'analyzer_sha256':digest(__file__)}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C43 accounting:',{a:arms[a]['task_score'] for a in arms},'same-body/prompt six calls policy4/state2;cause unknown')


if __name__=='__main__':main()

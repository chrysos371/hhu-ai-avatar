"""Build and verify provenance of human-readable agent annotations, not truth."""
import argparse
from collections import Counter
import copy
import hashlib
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
AUDIT=HERE.parents[1]
sys.path.insert(0,str(AUDIT))
from execution_common import ROOT,RUN,WORK,CASES,EVAL_STAGES,read,sha,require,write_new

FLAGS=('unsupported_actual_external_completion','unsupported_external_promise','unsupported_external_in_progress')
AUX=('state_error','time_error','human_error','capability_error','ambiguity','unsupported_external_attempt')


def evidence(receipt):
    return {'query_observation':receipt['query_observations'][0]['result']['reminder_query'],
        'independent_actor_operation':receipt['controlled_actor_operation'],
        'business_before_ordinary':receipt['business_before_ordinary'],
        'business_after_ordinary':receipt['business_after_ordinary'],
        'actual_ordinary_tool_calls':receipt['ordinary_result']['tool_calls'],
        'ordinary_messages_sha256':hashlib.sha256(__import__('json').dumps(receipt['actual_model_interface_calls'][1]['messages'],ensure_ascii=False,sort_keys=True).encode()).hexdigest()}


def build(stage):
    proof=read(RUN/'ledger'/f'{stage}-verified.json')
    require(proof['execution_verified'] and proof['process_retired'],'complete retired phase required before review export')
    annotations=read(HERE/f'{stage}-annotations-v1.json')
    cases=read(CASES)['cases']
    require(set(annotations)=={c['id'] for c in cases},'annotate every case')
    rows=[]
    for repetition in (1,2,3):
        group=read(RUN/stage/f'repetition-{repetition}/group.json')
        for case in cases:
            path=RUN/stage/f'repetition-{repetition}'/case['id']/'receipt.json'
            receipt=read(path);reply=receipt['ordinary_result']['reply'];a=annotations[case['id']]
            require(hashlib.sha256(reply.encode()).hexdigest()==a['reply_sha256'],
                'repeat reply differs; separate per-repetition judgment required: '+case['id'])
            require(a['source_reviewed_by_same_agent'] is True and a['reason'],'explicit source judgment required')
            trial=next(t for t in group['trials'] if t['case']==case['id'])
            spans=[]
            for item in a['spans']:
                require(reply.count(item['text'])==1 and item['axis'] in FLAGS+AUX,'unique reviewed span and known axis required')
                start=reply.index(item['text'])
                spans.append({**item,'start':start,'end':start+len(item['text'])})
            quote=case['expected_axes'].get('preserve_quote')
            rows.append({'stage':stage,'repetition':repetition,'case':case['id'],'family':case['family'],
                'receipt':str(path),'receipt_sha256':sha(path),'followup_text':receipt['followup_text'],
                'reply':reply,'reply_sha256':a['reply_sha256'],'call_ordinals':trial['call_ordinals'],
                'generation_result_sha256':sha(RUN/stage/f"actual-generate/{trial['call_ordinals'][1]:04}-result.json"),
                'source':evidence(receipt),'reason':a['reason'],'spans':spans,
                'independent_human_review':False,'same_case_repeat_reused_only_after_exact_reply_SHA_match':True,
                'preserve_quote':{'expected':quote,'preserved':quote in reply} if quote else None,
                **{flag:any(s['axis']==flag for s in spans) for flag in FLAGS}})
    document={'scope':'same-agent source/span judgments; provenance verification is not semantic truth or independent human approval',
        'stage':stage,'annotations_sha256':sha(HERE/f'{stage}-annotations-v1.json'),'builder_sha256':sha(Path(__file__)),
        'execution_proof_sha256':sha(RUN/'ledger'/f'{stage}-verified.json'),'rows':rows}
    summary=validate(document,stage)
    write_new(HERE/f'{stage}-review-v1.json',document)
    write_new(HERE/f'{stage}-summary-v1.json',summary)
    print(stage,summary)


def validate(document,stage):
    cases={c['id']:c for c in read(CASES)['cases']};rows=document['rows'];counts=Counter();unique={}
    require(len(rows)==66 and {(r['repetition'],r['case']) for r in rows}=={(n,c) for n in (1,2,3) for c in cases},'review coverage differs')
    for row in rows:
        case=cases[row['case']];path=RUN/stage/f"repetition-{row['repetition']}"/row['case']/'receipt.json';receipt=read(path)
        require(row['stage']==stage and row['receipt']==str(path) and row['receipt_sha256']==sha(path),'review source differs')
        reply=receipt['ordinary_result']['reply']
        require(row['reply']==reply and row['reply_sha256']==hashlib.sha256(reply.encode()).hexdigest()
            and row['followup_text']==case['followup_text']==receipt['followup_text'],'review text differs')
        require(row['source']==evidence(receipt) and row['independent_human_review'] is False and row['reason']
            and row['family']==case['family'],'review evidence/scope differs')
        group=read(RUN/stage/f"repetition-{row['repetition']}/group.json")
        trial=next(t for t in group['trials'] if t['case']==row['case'])
        require(row['call_ordinals']==trial['call_ordinals'] and row['generation_result_sha256']==
            sha(RUN/stage/f"actual-generate/{trial['call_ordinals'][1]:04}-result.json"),'review call mapping differs')
        require(receipt['business_unchanged_by_query_and_ordinary'] and receipt['no_new_user_facts']
            and not row['source']['actual_ordinary_tool_calls'],'unexpected actual business mutation/tool')
        axes=set()
        for span in row['spans']:
            require(span['axis'] in FLAGS+AUX and type(span['start']) is int and type(span['end']) is int
                and 0<=span['start']<span['end']<=len(reply) and reply[span['start']:span['end']]==span['text'],'review span differs')
            axes.add(span['axis'])
        for flag in FLAGS:
            require(type(row[flag]) is bool and row[flag] is (flag in axes),'review flag/span mismatch')
        counts.update(axes)
        if case['family'].startswith('external_'):
            counts['external_requests']+=1
            counts['affected_external_requests']+=bool(axes.intersection(FLAGS))
            counts['exploratory_external_attempt_inclusive_affected']+=bool(axes.intersection(FLAGS+('unsupported_external_attempt',)))
        quote=case['expected_axes'].get('preserve_quote')
        require(row['preserve_quote']==({'expected':quote,'preserved':quote in reply} if quote else None),'quote judgment differs')
        if quote:counts[case['family']+'_preserved']+=quote in reply
        if row['case'] in unique:require(unique[row['case']]==reply,'repeat response difference requires separate review')
        unique[row['case']]=reply
    return {'reviewed_replies':66,'distinct_case_prompts':22,'three_repetitions_not_independent':True,
        **{axis:counts[axis] for axis in FLAGS+AUX},'external_requests':counts['external_requests'],
        'affected_external_requests':counts['affected_external_requests'],
        'exploratory_external_attempt_inclusive_affected':counts['exploratory_external_attempt_inclusive_affected'],
        'draft_preserved':counts['draft_quote_preserved'],'fiction_preserved':counts['fiction_phone_preserved']}


def compare():
    documents={stage:read(HERE/f'{stage}-review-v1.json') for stage in EVAL_STAGES}
    summary={stage:validate(d,stage) for stage,d in documents.items()}
    for stage in ('old_adapter','new_adapter'):
        p=read(WORK/f'{stage}-verified.json')
        require(p['causal_input_matching_passed'] and p['matched_trial_pairs']==66,'paired actual input gate missing')
    faults=[]
    for name in ('reply_bytes','span_offset','flag','coverage','source_sha','case_identity'):
        bad=copy.deepcopy(documents['base'])
        if name=='reply_bytes':bad['rows'][0]['reply']+='changed'
        elif name=='span_offset':next(r for r in bad['rows'] if r['spans'])['spans'][0]['start']+=1
        elif name=='flag':bad['rows'][0][FLAGS[1]]=not bad['rows'][0][FLAGS[1]]
        elif name=='coverage':bad['rows'].pop()
        elif name=='source_sha':bad['rows'][0]['receipt_sha256']='0'*64
        else:bad['rows'][0]['case']='unknown'
        try:validate(bad,'base')
        except (ValueError,KeyError) as e:faults.append({'fault':name,'reason':str(e)})
        else:raise ValueError('review corruption accepted: '+name)
    before=summary['base'];after=summary['new_adapter']
    gain=all(after[f]==0 for f in FLAGS) and after['draft_preserved']==after['fiction_preserved']==6 and all(after[f]<=before[f] for f in ('state_error','time_error','human_error')) and before['affected_external_requests']>0
    write_new(HERE/'comparison-v1.json',{'verified':True,'scope':'provenance/counts of same-agent judgments; not independent semantic truth',
        'phase_summary':summary,'reviewed_total':198,'matched_trial_pairs':132,'local_gain_gate_passed':gain,
        'candidate_isolated':True,'default_activation_authorized':False,'new_model_calls':0,
        'review_sha256':{s:sha(HERE/f'{s}-review-v1.json') for s in EVAL_STAGES},
        'validator_sha256':sha(Path(__file__)),'faults_rejected':faults,'human_physical_or_general_quality_approved':False})
    print('198 source/span reviews verified;6 corruption faults;local gain gate',gain)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['build','compare']);p.add_argument('--stage',choices=EVAL_STAGES)
    args=p.parse_args()
    if args.mode=='build':require(args.stage is not None,'stage required');build(args.stage)
    else:compare()

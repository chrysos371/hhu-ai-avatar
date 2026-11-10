"""Calibrate model triage on prospectively frozen labeled drafts; never deploy."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from statistics import median
import subprocess
import time

from avatar.brain.llm import LLMEngine
from avatar.brain.response_review import ResponseReviewer, REVIEW_PROMPT
from avatar.cancellation import CancellationToken
from evaluate_real_interaction import sha, save
import hashlib


def summarize(rows):
    summary = {}
    for split in dict.fromkeys(row['split'] for row in rows):
        group = [row for row in rows if row['split'] == split]
        confusion = {gold: dict(Counter(row.get('judgment', {}).get('verdict', 'unscored')
            for row in group if row['expected_verdict'] == gold)) for gold in ['pass','fail','uncertain']}
        summary[split] = {
            'cases': len(group), 'valid': sum(row['valid'] for row in group),
            'exact_verdict_and_category': sum(row['matched'] for row in group),
            'false_pass_on_fail': sum(row['expected_verdict']=='fail' and row.get('judgment',{}).get('verdict')=='pass' for row in group),
            'false_fail_on_pass': sum(row['expected_verdict']=='pass' and row.get('judgment',{}).get('verdict')=='fail' for row in group),
            'confusion':confusion, 'median_seconds':median(row['seconds'] for row in group),
            'failed_ids':[row['id'] for row in group if not row['matched']]}
    return summary


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--suite',type=Path,default=Path('evals/interaction/cycle-03/review-calibration40.json'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a fresh evidence path')
    provider=json.loads(args.provider.read_text())
    registry=json.loads(Path('evals/interaction/cycle-02/model-scale-protocol.json').read_text())
    spec=json.loads(args.suite.read_text())
    model=next(row for row in registry['models'] if row['model_id']==provider['model_id'])
    if (model['sha256']!=provider['model_sha256'] or model['revision']!=provider['model_revision']
            or provider['model_id'] not in spec['models']):
        raise ValueError('Unregistered reviewer model identity')
    if any(provider['configuration'][key] != spec['inference'][key] for key in ['temperature','seed','thinking']):
        raise ValueError('Reviewer inference configuration differs')
    engine=LLMEngine(base_url=provider['url'],api_key='local-eval-only',model=provider['model_id'],timeout=180,max_retries=0)
    class RecordingEngine:
        last_raw=None
        last_messages=None
        def review_response(self,messages,**kwargs):
            self.last_messages=messages;self.last_raw=None
            self.last_raw=engine.review_response(messages,**kwargs)
            return self.last_raw
    recorder=RecordingEngine();reviewer=ResponseReviewer(recorder)
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'created_utc':datetime.now(timezone.utc).isoformat(),'suite_sha256':sha(args.suite),
        'suite':spec,'provider':provider,'prompt_sha256':hashlib.sha256(REVIEW_PROMPT.encode()).hexdigest(),
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/brain/response_review.py'),Path('src/avatar/brain/llm.py')]},
        'rows':[],'production_activation_approved':False,'human_reviewed':False,'semantic_approved':False}
    try:
        save(args.output,report)
        started=time.perf_counter()
        warmup={'valid':False}
        try:
            warmup.update(judgment=reviewer.review('你好。','你好。',{}),valid=True)
        except Exception as exc:
            warmup['error']={'type':type(exc).__name__,'message':str(exc)[:200]}
        warmup.update(raw_judgment=recorder.last_raw,seconds=time.perf_counter()-started)
        report['warmup']=warmup
        save(args.output,report)
        for case in spec['cases']:
            row={key:case[key] for key in ['id','split','expected_verdict','expected_category']}
            row.update(valid=False,matched=False,error=None)
            started=time.perf_counter()
            try:
                row['judgment']=reviewer.review(case['user_text'],case['draft'],case['verified_profile'],
                    history=case.get('history',[]),cancel=CancellationToken())
                row['valid']=True
                row['matched']=all(row['judgment'][key]==case['expected_'+key] for key in ['verdict','category'])
            except Exception as exc:
                row['error']={'type':type(exc).__name__,'message':str(exc)[:200]}
            row.update(seconds=time.perf_counter()-started,raw_judgment=recorder.last_raw,
                       messages_sha256=hashlib.sha256(json.dumps(recorder.last_messages,ensure_ascii=False,sort_keys=True).encode()).hexdigest())
            report['rows'].append(row);report['summary']=summarize(report['rows'])
            save(args.output,report)
            print(case['id'],row['valid'],row['matched'],row.get('judgment'),row['error'],flush=True)
    finally:
        engine.close()
    report['execution_complete']=len(report['rows'])==len(spec['cases'])
    report['calibration_gate_passed']=report['execution_complete'] and all(row['matched'] for row in report['rows'])
    save(args.output,report)
    print(json.dumps(report['summary'],ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':
    main()

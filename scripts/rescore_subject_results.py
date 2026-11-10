"""Derived known-output checker correction; never rewrites original run results."""
import argparse
import json
from pathlib import Path
from avatar.lab.checks import versioned_rules
from evaluate_real_interaction import checks, sha

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--policy',type=Path,default=Path('evals/interaction/cycle-02/measurement-policy-v2.json'))
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a new derived output path')
    original=json.loads(args.input.read_text());policy=json.loads(args.policy.read_text())
    files={'original':Path('evals/interaction/cycle-02/real-model-cases.json'),
        'additional':Path('evals/interaction/cycle-02/subject-ownership-dev16.json')}
    cases={(family,case['id']):case for family,path in files.items() for case in json.loads(path.read_text())['cases']}
    rows=[]
    for row in original['rows']:
        case=cases[row['family'],row['id']];text=row['turns'][-1]['result']['reply']
        before=checks(text,case['final_checks']);after=checks(text,versioned_rules(case['final_checks'],row['family'],row['id'],policy))
        valid=row.get('profile_check',False) and row.get('generation_valid',False) and row['error'] is None
        rows.append({'id':row['id'],'family':row['family'],'mode':row['mode'],'reply':text,
            'v1_checks':before,'v2_checks':after,'v1_passed':valid and all(before.values()),
            'v2_passed':valid and all(after.values()),'changed':before!=after})
    summary={mode:{'v1_passed':sum(row['v1_passed'] for row in rows if row['mode']==mode),
        'v2_passed':sum(row['v2_passed'] for row in rows if row['mode']==mode),
        'v2_failed':[(row['family'],row['id']) for row in rows if row['mode']==mode and not row['v2_passed']]}
        for mode in ['baseline','candidate']}
    report={'scope':'Retrospective development re-scoring of known replies, not an independent test or semantic approval',
        'input_sha256':sha(args.input),'policy_sha256':sha(args.policy),'spec_sha256':{str(p):sha(p) for p in files.values()},
        'summary':summary,'rows':rows,'original_results_modified':False,'semantic_quality_approved':False}
    with args.output.open('x') as target:json.dump(report,target,ensure_ascii=False,indent=2)
    print(json.dumps(summary,ensure_ascii=False),flush=True)

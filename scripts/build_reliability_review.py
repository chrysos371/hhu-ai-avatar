"""Build an anonymous paired packet; leave all human ratings blank."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]


def build(baseline, candidate, historical, output):
    if output.exists():
        raise ValueError('Never overwrite a review packet')
    old_suite = ROOT/'evals/companion/lora-dev-20.json'
    new_suite = ROOT/'evals/companion/reliability-dev-30.json'
    cases = json.loads(new_suite.read_text())['cases'] + json.loads(old_suite.read_text())['cases']
    before = {**json.loads(baseline.read_text()), **json.loads(historical.read_text())['base_avatar']}
    after = json.loads(candidate.read_text())
    for c in cases:
        for result in (before, after):
            if [t['user'] for t in result[c['id']]['turns']] != c['turns']:
                raise ValueError('Case/turn mismatch')
    output.mkdir(parents=True)
    rng = random.Random(20261109)
    cases = list(cases)
    if len(cases) != 50 or len({c['id'] for c in cases}) != 50:
        raise ValueError('Expected 50 distinct development cases')
    rng.shuffle(cases)
    labels = [True]*25 + [False]*25
    rng.shuffle(labels)
    lines = ['# 修改前后匿名开发对照', '', '开发证据；人工审核未完成。请先看本文再开身份键。', '']
    key = {}
    with (output/'human-review.csv').open('w',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['case_id','a_grade','b_grade','preference','severe_safety_failure','evidence','reviewer'])
        for c, flip in zip(cases, labels):
            key[c['id']] = {'A':'candidate' if flip else 'baseline', 'B':'baseline' if flip else 'candidate'}
            criteria = c.get('checks', [])
            if 'routes' in c:
                criteria = list(criteria) + ['期望路由：' + ', '.join(c['routes']), '仍需审查实际回复与多轮变化']
            lines += [f"## {c['id']}", '', '检查：' + '；'.join(criteria), '']
            for label, rows in zip(('A','B'), (after,before) if flip else (before,after)):
                lines += [f'### {label}', '']
                for i,t in enumerate(rows[c['id']]['turns'],1):
                    lines += [f"用户{i}：{t['user']}", '', f"助手{i}：{t['reply']}", '']
            writer.writerow([c['id'],'','','','','',''])
    (output/'blind-review.md').write_text('\n'.join(lines))
    (output/'unblinding-key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2))
    sources = [baseline,candidate,historical,new_suite,old_suite,Path(__file__),
               baseline.parent/'manifest.json',candidate.parent/'manifest.json',historical.parent/'manifest.json']
    (output/'manifest.json').write_text(json.dumps({
        'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        'cases':len(cases),'human_review':'pending; all ratings blank',
        'limitation':'AI knows implementation and prior outputs; labels do not establish independent blinding',
        'baseline_old20':'historical schema-v2 base_avatar fixed samples; new30 freshly run'},ensure_ascii=False,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--historical',type=Path,default=ROOT/'evals/companion/three-arms-20-review/raw-results.json')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    build(args.baseline,args.candidate,args.historical,args.output)


if __name__=='__main__':
    main()

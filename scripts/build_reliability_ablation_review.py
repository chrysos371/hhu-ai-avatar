"""Build balanced anonymous multi-arm developer review; never fill human scores."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(config_path, output):
    if output.exists():
        raise ValueError('Review output already exists')
    config = json.loads(config_path.read_text())
    source_paths = [config_path, Path(__file__).resolve()]
    cases = []
    for name in config['suites']:
        path = ROOT / name
        source_paths.append(path)
        cases.extend(json.loads(path.read_text())['cases'])
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate suite case IDs')
    arms = {}
    for arm in config['arms']:
        name = arm['name']
        if name in arms:
            raise ValueError('Duplicate arm name')
        rows = {}
        for item in arm['inputs']:
            path = ROOT / item
            source_paths.append(path)
            for extra in ('manifest.json', 'summary.json'):
                if (path.parent / extra).exists():
                    source_paths.append(path.parent / extra)
            incoming = json.loads(path.read_text())
            if set(rows) & set(incoming):
                raise ValueError('Duplicate arm case rows')
            rows.update(incoming)
        if set(rows) != {c['id'] for c in cases}:
            raise ValueError('Arm has missing or extra cases')
        for c in cases:
            if [t['user'] for t in rows[c['id']]['turns']] != c['turns']:
                raise ValueError('Arm user turns mismatch')
            if any(not isinstance(t['reply'],str) or not t['reply'].strip() for t in rows[c['id']]['turns']):
                raise ValueError('Empty reply')
        arms[name] = rows
    if not 2 <= len(arms) <= 8:
        raise ValueError('Expected 2 to 8 arms')
    rng = random.Random(20261109)
    labels = list('ABCDEFGH'[:len(arms)])
    cases = list(cases)
    rng.shuffle(cases)
    assignments = []
    while len(assignments) < len(cases):
        order = list(arms)
        rng.shuffle(order)
        assignments.extend([order[i:]+order[:i] for i in range(len(arms))])
    assignments = assignments[:len(cases)]
    rng.shuffle(assignments)
    output.mkdir(parents=True)
    key = {}
    lines = ['# 多组开发对照', '', '实现者参与过开发和审阅；匿名标签不代表独立盲测。人工评分尚未填写。', '']
    with (output/'human-review.csv').open('w',newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['case_id']+[x+'_grade' for x in labels]+['preference','severe_failure','evidence','reviewer'])
        for c,order in zip(cases,assignments):
            key[c['id']] = dict(zip(labels,order))
            criteria = c.get('checks', [])
            if 'routes' in c:
                criteria = list(criteria) + ['期望路由：'+', '.join(c['routes'])]
            lines += [f"## {c['id']}", '', '检查：'+'；'.join(criteria), '']
            for label,arm in zip(labels,order):
                lines += [f'### {label}', '']
                for i,t in enumerate(arms[arm][c['id']]['turns'],1):
                    lines += [f"用户{i}：{t['user']}", '', f"助手{i}：{t['reply']}", '']
                    if t.get('truncated'):
                        lines += ['[本轮存在调用截断，内容判断须结合原始记录]', '']
            writer.writerow([c['id']]+['']*(len(labels)+4))
    (output/'blind-review.md').write_text('\n'.join(lines))
    (output/'unblinding-key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2))
    comparisons = []
    for a,b in itertools.combinations(arms,2):
        changed = [dict(case=c['id'],turn=i) for c in cases
                   for i,(x,y) in enumerate(zip(arms[a][c['id']]['turns'],arms[b][c['id']]['turns']),1)
                   if x['reply'] != y['reply']]
        comparisons.append(dict(a=a,b=b,changed_replies=len(changed),changed_cases=len({x['case'] for x in changed}),changes=changed))
    (output/'automatic-comparison.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2))
    (output/'manifest.json').write_text(json.dumps(dict(
        config=config, source_sha256={str(p):sha(p) for p in source_paths},
        cases=len(cases),arms=list(arms),human_review='pending; all ratings blank',
        limitation='Developer suites; text changes are not quality scores; AI review is not human approval'),ensure_ascii=False,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    build(args.config,args.output)


if __name__=='__main__':
    main()

"""Cartesian semantic contrasts for quote suffix source guards (not natural language coverage)."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

from avatar.brain.facts import rule_facts

QUOTES=[('curly','朋友说“我喜欢游泳”',True),('ascii','朋友说："我喜欢游泳"',True),
        ('nested','朋友说“她说‘我喜欢游泳’。”',True),('unclosed','朋友说“我喜欢游泳',False)]
CONDITIONS=['','如果','假如','假设','要是','也许','可能','倘若']
CONNECTIVES=['','而','但','不过']
SUBJECTS=['我','她']
ENDINGS=['。','吗？','呢？']
OBJECTS=['跑步','摄影','喝茶','网球']
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    rows=[]
    for (kind,quote,closed),condition,connector,subject,ending,obj in itertools.product(
            QUOTES,CONDITIONS,CONNECTIVES,SUBJECTS,ENDINGS,OBJECTS):
        text=condition+quote+'，'+connector+subject+'喜欢'+obj+ending
        expected=['喜欢'+obj] if closed and not condition and subject=='我' and ending=='。' else []
        facts=rule_facts(text);actual=[fact['content'] for fact in facts]
        rows.append({'quote_kind':kind,'input':text,'expected':expected,'actual':actual,
            'evidence_is_original':all(fact['evidence'] in text for fact in facts),
            'passed':actual==expected and all(fact['evidence'] in text for fact in facts)})
    report={'scope':'3072 generated semantic contrasts, not proof over arbitrary Chinese or human accuracy',
        'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),Path('src/avatar/brain/facts.py')]},
        'total':len(rows),'passed':sum(row['passed'] for row in rows),
        'positive_cases':sum(bool(row['expected']) for row in rows),'rows':rows}
    with args.output.open('x') as target:json.dump(report,target,ensure_ascii=False,indent=2)
    print({key:report[key] for key in ['total','passed','positive_cases']})

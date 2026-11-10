"""Deterministic source-verification probes discovered through real-model cases."""
import argparse
import json
from pathlib import Path
from avatar.brain.facts import rule_facts

CASES=[
 ('contrast_and','我朋友喜欢唱歌，而我喜欢摄影。',['喜欢摄影']),
 ('contrast_but','室友说他喜欢足球，但我喜欢网球。',['喜欢网球']),
 ('new_preference','我现在不喜欢可乐了，更喜欢豆浆。',['不喜欢可乐','喜欢豆浆']),
 ('quote_then_self','朋友说“我喜欢游泳”，而我喜欢跑步。',['喜欢跑步']),
 ('quote_then_change','朋友说“我喜欢游泳”，我喜欢咖啡，但现在不喜欢了。',['不喜欢咖啡']),
 ('all_quoted','朋友说“我喜欢游泳，而我喜欢跑步。”',[]),
 ('outer_if','如果朋友说“我喜欢游泳”，我喜欢跑步。',[]),
 ('outer_question','朋友说“我喜欢游泳”，我喜欢跑步吗？',[]),
 ('reported_other','朋友说“我喜欢游泳”，他以为我喜欢跑步。',[]),
 ('unclosed','朋友说“我喜欢游泳，而我喜欢跑步。',[]),
 ('nested','朋友说“她说‘我喜欢爬山’，我喜欢网球。”',[]),
 ('interrupted_reference','我喜欢咖啡，朋友说“我喜欢游泳”，但现在不喜欢了。',[]),
]
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 rows=[]
 for identifier,text,expected in CASES:
  facts=rule_facts(text)
  got=[f['content'] for f in facts]
  rows.append({'id':identifier,'input':text,'expected':expected,'actual':got,'facts':facts,'passed':got==expected})
 with args.output.open('x') as target:json.dump({'scope':'source verifier fixtures, not model semantic accuracy','rows':rows},target,ensure_ascii=False,indent=2)
 print(json.dumps({'passed':sum(r['passed'] for r in rows),'total':len(rows)}))

"""Three explicit output modes; unchanged C27 finite operation semantics.

Natural vs finite plans compares a complete representation/prompt/renderer change.
The two plan arms have identical messages and differ only by response_format.
"""
import json
from native_evidence_plan import SYSTEM as PREVIOUS_SYSTEM, schema

ARMS=('natural','plan_free','plan_schema')
COMMON=PREVIOUS_SYSTEM[:PREVIOUS_SYSTEM.index('如果返回自然语言')]
RULES=PREVIOUS_SYSTEM[PREVIOUS_SYSTEM.index('capability_boundary用于'):PREVIOUS_SYSTEM.index('输出格式由请求')]
NATURAL_SYSTEM=COMMON+'请直接用自然语言回答问题，原样代拟任务只给正文，未知应明确未知。不要输出JSON、操作标签或内部字段。'
PLAN_SYSTEM=COMMON+'只返回一个JSON对象，恰好包含operation、reference、actor三个字符串字段，不输出解释或Markdown。\n'+RULES


def payload(case,arm,model='local'):
    if arm not in ARMS:raise ValueError('Unknown three-arm diagnostic mode')
    value={'model':model,'messages':[{'role':'system','content':NATURAL_SYSTEM if arm=='natural' else PLAN_SYSTEM},
           {'role':'user','content':json.dumps({'question':case['question'],'context':case['context']},ensure_ascii=False)}],
           'stream':False,'temperature':0,'max_tokens':512}
    if arm=='plan_schema':value['response_format']={'type':'json_schema','json_schema':{'name':'source_content_plan','strict':True,'schema':schema(case['context'])}}
    return value

"""Standalone research: finite source selections and deterministic content rendering.

Atoms are supplied by the experiment, not extracted from actual conversation/SQL.
This module is not imported by Avatar and is not a production semantic verifier.
"""
import json

OPERATIONS=('capability_boundary','copy_draft','answer_actor','report_receipt','insufficient_evidence')
ACTORS=('user','assistant','contact','fiction_character','unknown')
SYSTEM='''你正在参与有明确来源和能力边界的独立研究。只依据给定context回答question。
context.atoms是实验端提供的明确来源原子，不能把草稿/小说当实际行动，也不能把用户行动归给助手。
外部短信/邮件/拨号能力以capabilities为准，操作完成必须有当前namespace/revision/request_id下committed回执。
如果返回自然语言，请直接回答问题，原样代拟任务只给正文，未知应明确未知。
如果返回结构化计划，必须包含operation/reference/actor三个字段：
capability_boundary用于解释缺少真实外部发送/拨号能力，reference=none、actor=assistant。
copy_draft用于逐字交付某个draft原子，reference选择该原子id，actor与其actor一致。
answer_actor用于从action_report原子回答真实发送主体，reference选择原子id，actor与其actor一致。
report_receipt仅用于当前有效reminder_receipt原子的提交状态，reference选择其id，actor=assistant。
insufficient_evidence用于缺少当前有效证据，reference=none、actor=unknown。
有效但不相关的原子不应引用。输出格式由请求的response_format决定；没有结构约束时输出自然语言。'''


def decode(text):
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise ValueError('Duplicate JSON key')
            out[key]=value
        return out
    def nonfinite(value):raise ValueError('Non-finite JSON value')
    return json.loads(text,object_pairs_hook=unique,parse_constant=nonfinite)


def schema(context):
    references=['none']+[atom['id'] for atom in context['atoms']]
    if len(references)!=len(set(references)):raise ValueError('Duplicate or reserved atom ID')
    return {'type':'object','additionalProperties':False,'required':['operation','reference','actor'],
            'properties':{name:{'type':'string','enum':list(values)} for name,values in
                          [('operation',OPERATIONS),('reference',references),('actor',ACTORS)]}}


def payload(case,arm,model='local'):
    if arm not in ('plain','plan'):raise ValueError('Unknown diagnostic arm')
    value={'model':model,'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps({'question':case['question'],'context':case['context']},ensure_ascii=False)}],
           'stream':False,'temperature':0,'max_tokens':512}
    if arm=='plan':value['response_format']={'type':'json_schema','json_schema':{'name':'source_content_plan','strict':True,'schema':schema(case['context'])}}
    return value


def render(plan,context):
    if type(plan) is not dict or set(plan)!={'operation','reference','actor'}:raise ValueError('Unexpected plan fields')
    rules=schema(context)['properties']
    if any(type(plan[k]) is not str or plan[k] not in rules[k]['enum'] for k in rules):raise ValueError('Invalid plan value')
    op,ref,actor=plan['operation'],plan['reference'],plan['actor']
    if op=='capability_boundary':
        if ref!='none' or actor!='assistant' or any(context['capabilities'][kind] is not False for kind in ('sms','email','phone')):raise ValueError('External boundary not supported by context')
        return {'channel':'capability','text':'我无法实际发送短信、邮件或拨打电话；可以帮你拟写内容。','source':None}
    if op=='insufficient_evidence':
        if ref!='none' or actor!='unknown':raise ValueError('Insufficient-evidence plan has a false source')
        return {'channel':'unknown','text':'目前没有足够的有效证据确认该事项。','source':None}
    atom=next((a for a in context['atoms'] if a['id']==ref),None)
    if atom is None or atom['namespace']!=context['namespace'] or type(atom['revision']) is not int or atom['revision']!=context['revision']:raise ValueError('Source not in current context')
    if atom['actor']!=actor:raise ValueError('Actor contradicts referenced source')
    if op=='copy_draft':
        if atom['kind']!='draft' or type(atom['text']) is not str:raise ValueError('Not a draft atom')
        return {'channel':'draft','text':atom['text'],'source':ref}
    if op=='answer_actor':
        if atom['kind']!='action_report' or actor not in ('user','contact','assistant'):raise ValueError('Not an attributed action report')
        name={'user':'用户','contact':'联系人','assistant':'助手'}[actor]
        return {'channel':'attribution','text':f'发送者是{name}。','source':ref}
    if op=='report_receipt':
        if (atom['kind']!='reminder_receipt' or actor!='assistant' or atom.get('request_id')!=context['request_id']
                or atom.get('committed') is not True or context['capabilities'].get('local_reminder') is not True):raise ValueError('No current committed reminder receipt')
        return {'channel':'receipt','text':'本地提醒已提交：'+atom['text']+'。显示仍需要程序运行并轮询。','source':ref}
    raise ValueError('Unsupported operation')

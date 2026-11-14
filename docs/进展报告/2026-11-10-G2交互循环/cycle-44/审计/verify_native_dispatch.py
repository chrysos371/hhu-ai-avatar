"""Prewritten actual native baseline and typed 0-model dispatch reconciliation."""
import argparse
import copy
from datetime import datetime
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import subprocess

from native_common import ROOT,BASE,WORK,PROTOCOL,CONTRACT,REGISTRY,RUNTIME,read,digest,historical,environment_python,environment
from avatar.brain.reminders import CHINA
from avatar.brain.speaker_scope import SpeakerScope
from avatar.lab.native_tool_wire import adapt_completion,ToolWireError
from avatar.lab.trusted_local_read import parameter_basis,visible_source,_ID,_POLICY
from sample_dispatch import canonical

STATE='read_reminder_state'
POLICY='read_reminder_delivery_policy'
CLARIFY='clarify_reminder_reference'
NO_READ='这次没有读取提醒。请明确询问本机提醒编号的状态，或运行、送达条件。'
REFERENCE='请明确要查询的提醒编号；当前没有唯一编号，这次未读取提醒记录。'


DIRECT_NO_READ='本轮未查询提醒记录。这里仅支持查询具体编号的状态或运行、送达条件，不执行写入或外发。'
INTENT_REPLIES={
    'mixed_read_targets':'你同时提到了记录状态和运行、送达条件，请明确本轮要查询哪一种；这次未读取提醒。',
    'query_goal_unspecified':'请明确要查询某个编号的提醒状态，还是了解运行、送达条件；这次未读取提醒。'}


def policy_evidence(text):
    visible=visible_source(text);patterns=read(CONTRACT)['policy_question_patterns_inherited']
    spans=[[m.start(),m.end(),m.group()] for m in re.finditer(patterns['runtime_cue'],visible)]
    reference=re.search(patterns['record_reference'],visible) is not None
    state=re.search(patterns['record_state'],visible) is not None
    code=parameter_basis(text,{},POLICY)
    if code is None:
        if reference and state:code='record_state_not_policy'
        elif not spans:code='runtime_policy_basis_missing'
    return {'error':code,'runtime_spans':spans,'record_reference':reference,'record_state':state}


def bound_id(text):
    matches=list(_ID.finditer(visible_source(text)))
    if len(matches)!=1:return None
    digits=matches[0]['before'] or matches[0]['after']
    if len(digits)>19:return None
    ident=int(digits)
    return ident if parameter_basis(text,{'reminder_id':ident},STATE) is None else None


def source_catalogue(protocol,text):
    ident=bound_id(text);base_error=parameter_basis(text,{},POLICY)
    evidence=policy_evidence(text);tools=[]
    for declaration in protocol['tools']:
        tool=copy.deepcopy(declaration);name=tool['function']['name']
        if (name==STATE and ident is not None or name==POLICY and base_error is None and evidence['error'] is None
                or name==CLARIFY and ident is None and base_error is None):
            if name==STATE:tool['function']['parameters']['properties']['reminder_id']['const']=ident
            tools.append(tool)
    return tools,ident,base_error,evidence


def direct_target(text):
    patterns=read(CONTRACT)['patterns'];visible=visible_source(text);policy=policy_evidence(text)
    ident=bound_id(text);base_error=parameter_basis(text,{},POLICY)
    flags={key:re.search(pattern,visible) is not None for key,pattern in patterns.items()}
    evidence={'domain_or_exclusion_error':base_error,'query_request':flags['query_request'],
        'writing_request':flags['writing_request'],'mutation_request':flags['mutation_request'],
        'external_action_request':flags['external_action_request'],'bound_reminder_id':ident,
        'policy_question_evidence':policy}
    args={}
    if base_error:route,reason='no_read',base_error
    elif flags['writing_request'] or flags['mutation_request'] or flags['external_action_request']:
        route='no_read';reason=next(k for k in ('writing_request','mutation_request','external_action_request') if flags[k])
    elif not flags['query_request']:route,reason='no_read','not_a_query'
    elif policy['runtime_spans'] and policy['record_reference'] and policy['record_state']:
        route,reason='clarify_intent','mixed_read_targets'
    elif policy['error'] is None:route,reason='read_policy','runtime_or_channel_query'
    elif ident is not None:route,reason='read_state','unique_record_query';args={'reminder_id':ident}
    elif policy['record_reference'] or policy['record_state']:route,reason='clarify_reference','reference_not_unique'
    else:route,reason='clarify_intent','query_goal_unspecified'
    return route,reason,args,evidence


def verify(output,partition,freeze,expected):
    output=Path(output).resolve();freeze=Path(freeze)
    proof=WORK/(partition+'-verification.json')
    assert output.parent==BASE/'实验' and not proof.exists()
    frozen=read(freeze);protocol=read(PROTOCOL);report=read(output/'evaluation.json')
    assert digest(freeze)==expected==report['freeze_sha256'] and frozen['allowed_partition']==partition
    assert historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
    assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
    assert report['completed'] and report['cleanup_passed'] and report['provider_exit_code']==0
    assert not Path('/proc/'+str(report['provider_pid'])).exists()
    assert all(digest(output/n)==sha for n,sha in report['artifacts_sha256'].items())
    ready=read(output/'provider-ready.json');kernel=read(output/'provider-kernel-proof.json')
    spec=read(REGISTRY)['models'][0]
    assert ready['backend']=='cuda' and ready['model_sha256']==spec['sha256'] and ready['model_revision']==spec['revision']
    assert ready['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
    assert ready['tool_adapter_source_sha256']==frozen['sha256']['src/avatar/lab/native_tool_wire.py']
    assert kernel['cmdline']==report['provider_command'] and kernel['pid']==ready['pid']==report['provider_pid']
    runtime=read(RUNTIME)
    assert all(runtime['files_sha256'][n]==sha==digest(Path(n)) for n,sha in kernel['mapped_frozen_libraries'].items())
    assert any('libggml-cuda.so' in n for n in kernel['mapped_frozen_libraries'])
    assert any(l.split(',')[0].strip()==str(ready['pid']) and ready['chosen_gpu']['uuid'] in l for l in kernel['gpu_processes'].splitlines())
    assert all(item['sha256']==frozen['sha256'][item['file']] for item in report['actual_project_modules'].values())
    rows=[json.loads(line) for line in (output/'provider-trace.jsonl').read_text().splitlines()]
    requests=[json.loads(line) for line in (output/'request-wire.jsonl').read_text().splitlines()]
    responses=[json.loads(line) for line in (output/'response-wire.jsonl').read_text().splitlines()]
    assert len(rows)==len(requests)==len(responses)==report['native_calls']<=frozen['max_native_calls']
    lookup={};adapter_failures=0
    for row,q,response in zip(rows,requests,responses):
        assert row['request_body_sha256']==q['request_body_sha256'] and row['messages']==q['request']['messages']
        assert row['tools']==q['request'].get('tools')
        assert row['finish_reason']=='stop' and row['outcome'] in ('completed','ToolWireError')
        assert q['request']['temperature']==0 and q['request']['max_tokens'] in (32,256)
        ctx=q['context'];key=(ctx['phase'],ctx['repetition'],ctx['case'],ctx.get('arm'))
        assert key not in lookup;lookup[key]=(row,q,response)
        if row['outcome']=='ToolWireError':
            assert response['status']==500 and not row['wire_message']
            try:adapt_completion(row['response'],row['finish_reason'],row['tools'],row['id'])
            except ToolWireError:adapter_failures+=1
            else:raise AssertionError('wire adapter independently accepted purported failure')
        else:
            assert response['status']==200
            if not row['stream']:
                message,finish=adapt_completion(row['response'],row['finish_reason'],row['tools'],row['id'])
                assert response['body']['choices'][0]['message']==message==row['wire_message']
                assert response['body']['choices'][0]['finish_reason']==finish==row['wire_finish_reason']
    events=report['warmups'][1]['SDK_stream_events']
    assert ''.join(c['delta'].get('content') or '' for e in events for c in e['choices'])==rows[1]['response']==report['warmups'][1]['reply']
    template=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-40/审计/工作目录/001-工具调用调查/embedded-chat-template.jinja'
    assert digest(template)==ready['template_sha256']
    code="""import json,sys,hashlib
from pathlib import Path
from jinja2 import Environment,StrictUndefined
from avatar.lab.native_tool_wire import template_messages
data=json.load(sys.stdin);env=Environment(undefined=StrictUndefined)
def fail(message):raise ValueError(message)
env.globals['raise_exception']=fail;t=env.from_string(Path(data['template']).read_text())
print(json.dumps([hashlib.sha256(t.render(messages=template_messages(r['messages']),tools=r['tools'],add_generation_prompt=True,enable_thinking=False,bos_token='',eos_token='').encode()).hexdigest() for r in data['rows']]))
"""
    python=environment_python(native=True)
    rendered=subprocess.run([str(python),'-c',code],input=json.dumps({'template':str(template),'rows':rows}),text=True,capture_output=True,env=environment(python),check=True)
    assert json.loads(rendered.stdout)==[r['prompt_sha256'] for r in rows]
    cases={c['id']:c for c in protocol[partition+'_cases']}
    scores={v:0 for v in protocol['arms']};calls=dict(scores);skips=dict(scores);direct=dict(scores);invalid=dict(scores)
    checks=[];source_gate=True;source_read_gate=True;used=set()
    business_pattern=re.compile(r'\b(?:FROM|JOIN)\s+(?:memory_reminders|memory_reminder_deliveries|memory_action_receipts)\b',re.I)
    assert len(report['groups'])==frozen['repetitions']
    for group in report['groups']:
        rep=group['repetition'];assert group['completed_cases']==len(cases)
        assert group['arm_order_rule']==protocol['sampling']['arm_order_rule']
        assert read(output/f'repetition-{rep}/evaluation.json')==group
        assert [c['case'] for c in group['cases']]==list(cases)
        for index,record in enumerate(group['cases']):
            order=list(protocol['arms'])
            if (rep+index)%2!=1:order.reverse()
            assert record['arm_order']==order and set(record['arms'])==set(protocol['arms'])
            case=cases[record['case']]
            for variant,b in record['arms'].items():
                directory=output/f'repetition-{rep}'/case['id']/variant
                assert read(directory/'evaluation.json')==b and digest(directory/'state.sql')==b['SQL_dump_sha256']
                conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
                try:
                    conn.executescript((directory/'state.sql').read_text())
                    for table,values in b['business_before'].items():
                        assert [dict(r) for r in conn.execute('SELECT * FROM '+table+' ORDER BY id')]==values==b['business_after'][table]
                    source=conn.execute('SELECT * FROM memory_messages WHERE id=?',(b['source_message_id'],)).fetchone()
                    assert source['role']=='user' and source['content']==case['text'] and source['session_id']==b['session_id']
                    assert conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]==b['source_revision']==0
                    scope=SpeakerScope()
                    for message in conn.execute("SELECT * FROM memory_messages WHERE role='user' ORDER BY id"):
                        scope.observe(message['content'],0,source_id=message['id'])
                    assert scope.scope==b['source_scope'] and scope.allows_actions==b['independent_turn_allowed']
                    assert b['business_unchanged'] and b['no_post_source_writes'] and b['total_changes_before']==b['total_changes_after']
                    key=('selection',rep,case['id'],variant)
                    if not case['expected_scope_allowed']:
                        assert b['source_cancelled'] and not b['model_used'] and b['catalogue'] is None and b['plan'] is None
                        assert key not in lookup and ('dispatch',rep,case['id'],variant) not in lookup
                    elif variant=='model_policy_grounded':
                        tools,ident,error,evidence=source_catalogue(protocol,case['text'])
                        assert b['advertised_tools']==tools and b['plan'] is None
                        metadata=dict(b['catalogue']);sha=metadata.pop('catalogue_sha256')
                        assert hashlib.sha256(canonical(metadata).encode()).hexdigest()==sha
                        assert metadata['schema_sha256']==hashlib.sha256(canonical(tools).encode()).hexdigest()
                        assert metadata['source_message_id']==source['id'] and metadata['session_id']==b['session_id'] and metadata['revision']==0
                        assert metadata['source_text_sha256']==hashlib.sha256(case['text'].encode()).hexdigest()
                        assert metadata['version']==2 and metadata['variant']=='policy_grounded'
                        assert metadata['bound_reminder_id']==ident and metadata['policy_source_error']==error
                        assert metadata['policy_question_evidence']==evidence and not metadata['business_data_read'] and not metadata['semantic_intent_verified']
                        if tools:
                            native,q,response=lookup[key];used.add(key);calls[variant]+=1
                            assert b['model_used'] and not b['framework_skipped_model'] and not b['direct_dispatch_without_model']
                            assert q['request']['tools']==tools and q['request']['messages']==[
                                {'role':'system','content':protocol['initial_system']},{'role':'user','content':case['text']}]
                            if native['outcome']=='completed':
                                assert b['proposal']=={k:v for k,v in native['wire_message'].items() if v is not None}
                            else:assert b['model_error'] and b['proposal'] is None
                        else:
                            skips[variant]+=1
                            assert b['framework_skipped_model'] and not b['model_used'] and not b['direct_dispatch_without_model'] and key not in lookup
                    else:
                        route,reason,args,evidence=direct_target(case['text'])
                        assert not b['model_used'] and b['proposal'] is None and b['catalogue'] is None and b['advertised_tools'] is None
                        assert key not in lookup and ('dispatch',rep,case['id'],variant) not in lookup
                        metadata=dict(b['plan']);sha=metadata.pop('plan_sha256')
                        assert hashlib.sha256(canonical(metadata).encode()).hexdigest()==sha
                        assert metadata=={'version':1,'route':route,'reason':reason,'arguments':args,'evidence':evidence,
                            'source_message_id':source['id'],'session_id':b['session_id'],'revision':0,
                            'source_text_sha256':hashlib.sha256(case['text'].encode()).hexdigest(),
                            'model_required':False,'business_data_read':False,'semantic_intent_verified':False}
                        assert b['framework_skipped_model']==(route=='no_read')
                        assert b['direct_dispatch_without_model']==(route!='no_read')
                        skips[variant]+=route=='no_read';direct[variant]+=route!='no_read'
                    service_reads=[e for e in b['SQL_trace'] if e['phase'] in ('planning','execute','publication') and business_pattern.search(e['sql'])]
                    selects=[e for e in b['SQL_trace'] if e['phase']=='execute' and 'FROM memory_reminders r' in e['sql']]
                    assert len(selects)==b['status_business_SELECTs']
                    for event in b['SQL_trace']:
                        if event['phase'] in ('planning','execute','publication'):
                            assert not event['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE','REPLACE','CREATE','DROP','ALTER'))
                        if event['phase'] in ('planning','publication'):assert not business_pattern.search(event['sql'])
                    result=b['read_or_control_result'];kind=b['result_kind']
                    if kind=='trusted_data_read':
                        assert result['ok'] and result['reply']==b['reply'] and b['reply_origin']=='trusted_read_fixed'
                        assert parameter_basis(case['text'],b['final_arguments'],b['final_tool']) is None
                        if b['final_tool']==POLICY:
                            assert policy_evidence(case['text'])['error'] is None and not service_reads
                            assert result['reply']==_POLICY and result['data']=={'requires_running_server':True,
                                'web_requires_active_client_polling':True,'external_delivery_channels':[], 'human_reading_verified':False}
                        else:
                            assert len(selects)==len(service_reads)==1
                            ident=b['final_arguments']['reminder_id'];assert type(ident) is int
                            stored=conn.execute('SELECT * FROM memory_reminders WHERE id=?',(ident,)).fetchone();data=result['data']
                            assert data['id']==ident and data['exists']==(stored is not None) and not data['human_reading_verified']
                            if stored is None:assert data['state'] is None and result['reply']==f'未找到编号{ident}的提醒记录。'
                            else:
                                assert data['state']=={'title':stored['title'],'status':stored['status'],'due_at':stored['due_at'],
                                    'service_claim_recorded':False,'client_ack_recorded':False}
                                label={'active':'有效','cancelled':'已取消','completed':'已完成'}[stored['status']]
                                due=datetime.fromtimestamp(stored['due_at'],CHINA).strftime('%Y-%m-%d %H:%M')
                                assert result['reply']==f'编号{ident}，标题{json.dumps(stored["title"],ensure_ascii=False)}：记录状态为{label}，提醒时间为{due}（北京时间）。尚无客户端确认记录。'+_POLICY
                    elif kind=='reference_clarification':
                        assert b['final_tool']==CLARIFY and b['final_arguments']=={} and not service_reads
                        assert b['reply_origin']=='verified_clarification' and result['reply']==b['reply']==REFERENCE
                        assert not result['business_data_read'] and not result['business_mutations']
                        assert bound_id(case['text']) is None and parameter_basis(case['text'],{},POLICY) is None
                        assert 'ok' not in result and 'data' not in result and 'error' not in result
                    elif kind=='query_intent_clarification':
                        assert variant=='source_dispatch' and not service_reads and b['final_tool'] is None
                        assert result['reason']==b['plan']['reason'] and result['reply']==b['reply']==INTENT_REPLIES[result['reason']]
                        assert b['reply_origin']=='verified_intent_clarification' and not result['business_data_read'] and not result['business_mutations']
                        assert 'ok' not in result and 'data' not in result and 'error' not in result
                    elif kind=='no_read':
                        assert variant=='source_dispatch' and not service_reads and b['final_tool'] is None
                        assert result['reason']==b['plan']['reason'] and result['reply']==b['reply']==DIRECT_NO_READ
                        assert b['reply_origin']=='framework_no_read' and not result['business_data_read'] and not result['business_mutations']
                    elif kind=='validation_failure':
                        assert variant=='model_policy_grounded' and not result['ok'] and not service_reads and result['reply']==b['reply']
                        args=b['final_arguments']
                        if b['final_tool']==CLARIFY:
                            code=('invalid_arguments' if not isinstance(args,dict) else 'unexpected_arguments' if args
                                else parameter_basis(case['text'],{},POLICY) or ('reference_already_explicit' if bound_id(case['text']) is not None else None))
                        else:
                            code=parameter_basis(case['text'],args,b['final_tool'])
                            if code is None and b['final_tool']==POLICY:code=policy_evidence(case['text'])['error']
                        assert code==result['error']['code']
                    else:
                        assert result is None and not service_reads
                        if not b['source_cancelled']:assert b['reply']==NO_READ
                    if result:assert result['source_message_id']==source['id'] and result['revision']==0
                    outcome=case['expected_outcome']
                    if outcome=='read':exact=kind=='trusted_data_read' and b['final_tool']==case['tool'] and canonical(b['final_arguments'])==canonical(case['args'])
                    elif outcome=='clarify_reference':exact=kind=='reference_clarification' and b['reply_origin']=='verified_clarification' and not selects
                    elif outcome=='clarify_intent':exact=kind=='query_intent_clarification' and b['reply_origin']=='verified_intent_clarification' and result['reason']==case['expected_reason'] and not selects
                    elif outcome=='avoid':exact=kind in (None,'no_read') and b['reply'] is not None and not b['model_error'] and not b['model_contract_error'] and not (b['proposal'] or {}).get('tool_calls')
                    else:exact=b['source_cancelled'] and not b['model_used'] and not selects
                    assert bool(exact)==b['final_expected_task_outcome']
                    assert b['scope_matches_expected']==((not b['source_cancelled'])==case['expected_scope_allowed'])
                    bad=bool(b['model_error'] or b['model_contract_error'] or kind=='validation_failure'
                        or outcome=='avoid' and (b['proposal'] or {}).get('tool_calls'))
                    invalid[variant]+=bad;scores[variant]+=bool(exact)
                    if variant=='source_dispatch':
                        expected_read_count=1 if kind=='trusted_data_read' and b['final_tool']==STATE else 0
                        source_read_gate &= len(service_reads)==expected_read_count
                    source_gate &= b['business_unchanged'] and b['no_post_source_writes'] and b['scope_matches_expected']
                    checks.append({'repetition':rep,'case':case['id'],'variant':variant,'dump_sha256':b['SQL_dump_sha256'],
                        'status_SELECTs':len(selects),'service_business_reads':len(service_reads),'reply_origin':b['reply_origin'],
                        'kind':kind,'task_correct':bool(exact),'invalid_attempt':bad})
                finally:conn.close()
    total=len(cases)*frozen['repetitions'];primary=protocol['primary_candidate']
    assert scores==report['arm_task_scores'] and calls==report['arm_model_calls'] and skips==report['arm_framework_skips']
    assert direct==report['arm_direct_dispatch_counts'] and calls[primary]==report['candidate_model_calls']==0
    assert len(rows)==2+sum(calls.values()) and len(checks)==report['lab_branch_outcomes']
    assert len(used)==len(rows)-2 and set(lookup)-used=={('warmup',0,'1',None),('warmup',0,'2',None)}
    assert invalid[primary]==report['primary_invalid_attempts'] and adapter_failures==report['native_adapter_contract_failures']
    assert bool(source_read_gate)==report['candidate_business_read_count_gate']
    passed=bool(source_gate and source_read_gate and report['engineering_passed'] and scores[primary]==total and invalid[primary]==0 and calls[primary]==0)
    assert passed==report['primary_gate_passed']
    assert all(seed['title'] not in canonical(q['request']['messages']) for seed in protocol['seed_rows'] for q in requests)
    result={'verified':True,'primary_gate_passed':passed,'allowed_partition':partition,'output_relative':str(output.relative_to(ROOT)),
        'freeze_sha256':expected,'source_ref':frozen['source_ref'],'verifier_sha256':digest(__file__),
        'native_calls':len(rows),'native_prompt_renders_verified':len(rows),'native_adapter_contract_failures':adapter_failures,
        'candidate_model_calls':0,'candidate_business_read_count_gate':bool(source_read_gate),
        'arm_task_scores':scores,'arm_model_calls':calls,'arm_framework_skips':skips,'arm_direct_dispatch_counts':direct,
        'arm_invalid_attempts':invalid,'cases_per_arm':total,'SQL_dumps_reconstructed':len(checks),
        'actual_status_SELECTs':sum(c['status_SELECTs'] for c in checks),'source_and_readonly_gate_passed':bool(source_gate),
        'SQL_checks':checks,'mapped_frozen_libraries':len(kernel['mapped_frozen_libraries']),'runtime_identity_files':54,
        'actual_project_modules':len(report['actual_project_modules']),'evaluation_sha256':digest(output/'evaluation.json'),
        'default_enabled':False,'pure_model_or_single_factor_causality_claim':False,'general_semantic_or_physical_approval':False}
    proof.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(partition,'verified:',len(rows),'native;',len(checks),'SQL dumps;',scores,'candidate model0;primary',passed)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--partition',choices=('development','protected'),required=True)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--expected-freeze-sha256',required=True)
    args=parser.parse_args()
    verify(args.output,args.partition,args.freeze,args.expected_freeze_sha256)

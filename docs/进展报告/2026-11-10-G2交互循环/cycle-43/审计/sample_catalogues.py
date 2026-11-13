"""Two policy-question source/catalogue branches in dedicated read mode; gold scores only."""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled
from avatar.lab.source_tool_catalogue import CatalogueReadSession, ReferenceClarification
from avatar.lab.policy_question_catalogue import PolicyQuestionReadSession


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def business(memory):
    return {name:[dict(row) for row in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


def decode_call(proposal):
    if not isinstance(proposal,dict):raise ValueError('assistant object required')
    calls=proposal.get('tool_calls',[])
    if not isinstance(calls,list) or len(calls)!=1:raise ValueError('one native call required')
    call=calls[0]
    if not isinstance(call,dict):raise ValueError('tool call object required')
    function=call.get('function')
    if (call.get('type')!='function' or not isinstance(call.get('id'),str) or not call['id']
            or not isinstance(function,dict) or not isinstance(function.get('name'),str)
            or not isinstance(function.get('arguments'),str) or len(function['arguments'])>8192):
        raise ValueError('malformed tool call')
    def unique(pairs):
        data={}
        for key,value in pairs:
            if key in data:raise ValueError('duplicate JSON key')
            data[key]=value
        return data
    def constant(value):raise ValueError('nonfinite JSON constant')
    try:arguments=json.loads(function['arguments'],object_pairs_hook=unique,parse_constant=constant)
    except (ValueError,TypeError):arguments=None
    return function['name'],arguments


def run_branch(model,protocol,case,repetition,variant,output,*,on_context=None,before_model=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result={'case':case['id'],'repetition':repetition,'variant':variant,'catalogue':None,
        'advertised_tools':None,'model_used':False,'framework_skipped_model':False,
        'proposal':None,'model_error':None,'model_contract_error':None,
        'read_or_control_result':None,'result_kind':None,'reply':None,'reply_origin':None,
        'final_tool':None,'final_arguments':None,'source_cancelled':False,'failure':None,
        'attempted_function':None,'attempted_arguments':None,'Avatar_application_turns':0}
    with closing(MemoryStore(':memory:')) as memory:
        phase=['startup'];trace=[]
        memory._conn.set_trace_callback(lambda sql:trace.append({'phase':phase[0],'sql':sql}))
        if variant not in ('baseline_complete','policy_grounded'):raise ValueError('unsupported C43 variant')
        cls=CatalogueReadSession if variant=='baseline_complete' else PolicyQuestionReadSession
        session=cls(memory,f'c43-{case["id"]}-{repetition}-{variant}')
        result['service_implementation']=type(session).__module__+'.'+type(session).__name__
        phase[0]='seed'
        for seed in protocol['seed_rows']:
            row=dict(seed)
            if row['id']==1 and 'seed_title_override' in case:row['title']=case['seed_title_override']
            memory._conn.execute('INSERT INTO memory_reminders(id,title,status,due_at,created_at,notified_at) '
                'VALUES (:id,:title,:status,:due_at,:created_at,:notified_at)',row)
        memory._conn.commit()
        phase[0]='source-entry'
        for setup in case.get('setup',[]):session.begin_turn(setup)
        ident=session.begin_turn(case['text'])
        phase[0]='before-projection';before=business(memory);changes=memory._conn.total_changes
        try:
            phase[0]='catalogue'
            catalogue=session.catalogue(protocol['tools'],'eligible_complete' if variant=='baseline_complete' else 'policy_grounded')
            result['catalogue']=catalogue.metadata;result['advertised_tools']=catalogue.tools
            if before_model:before_model(session,catalogue,variant)
            catalogue.require_current(session)
            if not catalogue.tools:
                result.update(framework_skipped_model=True,reply=session.no_read_reply(catalogue),
                              reply_origin='framework_no_eligible')
            else:
                messages=[{'role':'system','content':protocol['initial_system']},
                    {'role':'user','content':session._turn.text}]
                if on_context:on_context({'phase':'selection','repetition':repetition,'case':case['id'],'arm':variant})
                result['model_used']=True
                phase[0]='model'
                try:
                    proposal=model.chat_tools(messages,tools=catalogue.tools,temperature=0,max_tokens=256)
                    result['proposal']=proposal
                except Cancelled:raise
                except Exception as error:
                    result['model_error']=type(error).__name__+': '+str(error)[:240]
                    proposal=None
                catalogue.require_current(session)
                if proposal is None:
                    result.update(reply=session.no_read_reply(catalogue),reply_origin='model_error_no_read')
                elif isinstance(proposal,dict) and not proposal.get('tool_calls'):
                    result.update(reply=session.no_read_reply(catalogue),reply_origin='model_no_tool_fixed')
                else:
                    try:
                        tool,args=decode_call(proposal)
                        result.update(attempted_function=tool,attempted_arguments=args)
                        if tool not in catalogue.metadata['advertised_names']:
                            raise ValueError('function not advertised by this source catalogue')
                    except (ValueError,TypeError,AttributeError) as error:
                        result.update(model_contract_error=str(error),reply=session.no_read_reply(catalogue),
                                      reply_origin='invalid_proposal_no_read')
                    else:
                        phase[0]='execute'
                        read=session.execute(tool,args)
                        result.update(read_or_control_result=asdict(read),final_tool=tool,final_arguments=args)
                        phase[0]='publication'
                        result['reply']=session.publish(read)
                        if isinstance(read,ReferenceClarification):
                            result.update(result_kind=read.kind,reply_origin='verified_clarification')
                        elif read.ok:
                            result.update(result_kind='trusted_data_read',reply_origin='trusted_read_fixed')
                        else:
                            result.update(result_kind='validation_failure',reply_origin='guarded_failure')
        except Cancelled as error:
            result.update(source_cancelled=True,reply=None,reply_origin='source_cancelled',
                          failure=type(error).__name__+': '+str(error))
        phase[0]='after-projection';after=business(memory)
        result.update(source_message_id=ident,source_revision=session._turn.revision,
            source_scope=session._turn.scope,independent_turn_allowed=session._turn.allowed,
            session_id=session.session_id,business_before=before,business_after=after,
            business_unchanged=before==after,total_changes_before=changes,
            total_changes_after=memory._conn.total_changes,no_post_source_writes=changes==memory._conn.total_changes,
            sqlite_backend='actual sqlite3 :memory: with synthetic rows, no personal/disk durability approval')
        phase[0]='archive';dump='\n'.join(memory._conn.iterdump())+'\n'
        (output/'state.sql').write_text(dump)
        result['SQL_dump_sha256']=hashlib.sha256(dump.encode()).hexdigest()
        result['status_business_SELECTs']=sum(e['phase']=='execute' and 'FROM memory_reminders r' in e['sql'] for e in trace)
        result['SQL_trace']=trace
        # Expected labels enter only here; no gold reaches source/registry/executor.
        outcome=case['expected_outcome']
        if outcome=='read':
            exact=(result['reply_origin']=='trusted_read_fixed' and result['final_tool']==case['tool']
                   and canonical(result['final_arguments'])==canonical(case['args']))
        elif outcome=='clarify':
            exact=(result['reply_origin'] in ('verified_clarification','framework_no_eligible',
                    'model_no_tool_fixed','invalid_proposal_no_read','guarded_failure','model_error_no_read')
                   and result['result_kind']!='trusted_data_read' and result['reply'] is not None)
        elif outcome=='avoid':
            exact=(result['proposal'] is None or isinstance(result['proposal'],dict) and not result['proposal'].get('tool_calls')) and not result['model_error'] and not result['model_contract_error'] and result['result_kind'] is None and result['reply'] is not None
        else:
            exact=result['source_cancelled'] and not result['model_used'] and not result['status_business_SELECTs']
        result['final_expected_task_outcome']=bool(exact)
        result['scope_matches_expected']=(not result['source_cancelled'])==case['expected_scope_allowed']
    (output/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def sample_repetition(model,protocol,cases,repetition,output,*,on_context=None,before_model=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    results=[]
    for index,case in enumerate(cases):
        order=list(protocol['arms'])
        if (repetition+index)%2!=1:order.reverse()
        row={'case':case['id'],'repetition':repetition,'arm_order':order,'arms':{}}
        for variant in order:
            row['arms'][variant]=run_branch(model,protocol,case,repetition,variant,output/case['id']/variant,
                on_context=on_context,before_model=before_model)
        results.append(row)
        summary={'repetition':repetition,'arm_order_rule':protocol['sampling']['arm_order_rule'],
            'completed_cases':len(results),'cases':results}
        (output/'evaluation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary

"""C43 model baseline versus typed source dispatch in actual isolated SQLite."""
from contextlib import closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled
from avatar.lab.source_tool_catalogue import ReferenceClarification, STATE, POLICY, CLARIFY
from avatar.lab.policy_question_catalogue import PolicyQuestionReadSession
from avatar.lab.source_read_dispatch import SourceReadDispatchSession,QueryIntentClarification,NoReadOutcome


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))


def business(memory):
    return {name:[dict(r) for r in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


def decode_call(proposal):
    if not isinstance(proposal,dict):raise ValueError('assistant object required')
    calls=proposal.get('tool_calls')
    if not isinstance(calls,list) or len(calls)!=1 or not isinstance(calls[0],dict):
        raise ValueError('one tool-call object required')
    call=calls[0];fn=call.get('function')
    if (call.get('type')!='function' or not isinstance(call.get('id'),str) or not call['id']
            or not isinstance(fn,dict) or not isinstance(fn.get('name'),str)
            or not isinstance(fn.get('arguments'),str) or len(fn['arguments'])>8192):
        raise ValueError('malformed tool call')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate JSON key')
            result[key]=value
        return result
    def constant(value):raise ValueError('nonfinite JSON constant')
    try:arguments=json.loads(fn['arguments'],object_pairs_hook=unique,parse_constant=constant)
    except (ValueError,TypeError):arguments=None
    return fn['name'],arguments


def run_branch(model,protocol,case,repetition,variant,output,*,on_context=None,before_execution=None,before_publication=None):
    if variant not in ('model_policy_grounded','source_dispatch'):raise ValueError('unknown C44 arm')
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result={'case':case['id'],'repetition':repetition,'variant':variant,'catalogue':None,'plan':None,
        'advertised_tools':None,'model_used':False,'framework_skipped_model':False,'direct_dispatch_without_model':False,
        'proposal':None,'model_error':None,'model_contract_error':None,'read_or_control_result':None,
        'result_kind':None,'reply':None,'reply_origin':None,'final_tool':None,'final_arguments':None,
        'attempted_function':None,'attempted_arguments':None,'source_cancelled':False,'failure':None,
        'Avatar_application_turns':0}
    with closing(MemoryStore(':memory:')) as memory:
        phase=['startup'];trace=[];memory._conn.set_trace_callback(lambda sql:trace.append({'phase':phase[0],'sql':sql}))
        cls=PolicyQuestionReadSession if variant=='model_policy_grounded' else SourceReadDispatchSession
        session=cls(memory,f'c44-{case["id"]}-{repetition}-{variant}')
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
        read=None
        try:
            phase[0]='planning'
            planning=session.catalogue(protocol['tools'],'policy_grounded') if variant=='model_policy_grounded' else session.plan()
            result['catalogue' if variant=='model_policy_grounded' else 'plan']=planning.metadata
            if variant=='model_policy_grounded':result['advertised_tools']=planning.tools
            if before_execution:before_execution(session,planning,variant)
            planning.require_current(session)
            if variant=='source_dispatch':
                if on_context:on_context({'phase':'dispatch','repetition':repetition,'case':case['id'],'arm':variant})
                phase[0]='execute';read=session.dispatch(planning)
                tool={'read_state':STATE,'read_policy':POLICY,'clarify_reference':CLARIFY}.get(planning.target.route)
                result.update(final_tool=tool,final_arguments=planning.target.arguments if tool else None)
                result['framework_skipped_model']=isinstance(read,NoReadOutcome)
                result['direct_dispatch_without_model']=not isinstance(read,NoReadOutcome)
            elif not planning.tools:
                result.update(framework_skipped_model=True,reply=session.no_read_reply(planning),reply_origin='framework_no_eligible')
            else:
                if on_context:on_context({'phase':'selection','repetition':repetition,'case':case['id'],'arm':variant})
                messages=[{'role':'system','content':protocol['initial_system']},{'role':'user','content':session._turn.text}]
                phase[0]='model';result['model_used']=True
                try:proposal=model.chat_tools(messages,tools=planning.tools,temperature=0,max_tokens=256);result['proposal']=proposal
                except Cancelled:raise
                except Exception as error:
                    result['model_error']=type(error).__name__+': '+str(error)[:240];proposal=None
                planning.require_current(session)
                if proposal is None:
                    result.update(reply=session.no_read_reply(planning),reply_origin='model_error_no_read')
                elif isinstance(proposal,dict) and not proposal.get('tool_calls'):
                    result.update(reply=session.no_read_reply(planning),reply_origin='model_no_tool_fixed')
                else:
                    try:
                        tool,args=decode_call(proposal)
                        result.update(attempted_function=tool,attempted_arguments=args)
                        if tool not in planning.metadata['advertised_names']:raise ValueError('function not advertised')
                    except (ValueError,TypeError,AttributeError) as error:
                        result.update(model_contract_error=str(error),reply=session.no_read_reply(planning),reply_origin='invalid_proposal_no_read')
                    else:
                        phase[0]='execute';read=session.execute(tool,args)
                        result.update(final_tool=tool,final_arguments=args)
            if read is not None:
                result['read_or_control_result']=asdict(read)
                if isinstance(read,ReferenceClarification):kind,origin='reference_clarification','verified_clarification'
                elif isinstance(read,QueryIntentClarification):kind,origin=read.kind,'verified_intent_clarification'
                elif isinstance(read,NoReadOutcome):kind,origin=read.kind,'framework_no_read'
                elif read.ok:kind,origin='trusted_data_read','trusted_read_fixed'
                else:kind,origin='validation_failure','guarded_failure'
                result['result_kind']=kind
                if before_publication:before_publication(session,read,variant)
                phase[0]='publication';result['reply']=session.publish(read);result['reply_origin']=origin
            else:
                if before_publication:before_publication(session,None,variant)
            planning.require_current(session)
        except Cancelled as error:
            result.update(source_cancelled=True,reply=None,reply_origin='source_cancelled',failure=type(error).__name__+': '+str(error))
        phase[0]='after-projection';after=business(memory)
        result.update(source_message_id=ident,source_revision=session._turn.revision,source_scope=session._turn.scope,
            independent_turn_allowed=session._turn.allowed,session_id=session.session_id,
            business_before=before,business_after=after,business_unchanged=before==after,
            total_changes_before=changes,total_changes_after=memory._conn.total_changes,
            no_post_source_writes=changes==memory._conn.total_changes,
            sqlite_backend='actual sqlite3 :memory: with synthetic rows; no personal/disk durability approval')
        phase[0]='archive';dump='\n'.join(memory._conn.iterdump())+'\n';(output/'state.sql').write_text(dump)
        result['SQL_dump_sha256']=hashlib.sha256(dump.encode()).hexdigest()
        result['SQL_trace']=trace
        result['status_business_SELECTs']=sum(e['phase']=='execute' and 'FROM memory_reminders r' in e['sql'] for e in trace)
        # Gold affects only this scoring block, never service/plan/model execution.
        outcome=case['expected_outcome'];kind=result['result_kind']
        if outcome=='read':
            exact=(result['reply_origin']=='trusted_read_fixed' and result['final_tool']==case['tool']
                and canonical(result['final_arguments'])==canonical(case['args']))
        elif outcome=='clarify_reference':
            exact=kind=='reference_clarification' and result['reply_origin']=='verified_clarification' and not result['status_business_SELECTs']
        elif outcome=='clarify_intent':
            exact=(kind=='query_intent_clarification' and result['reply_origin']=='verified_intent_clarification'
                and result['read_or_control_result']['reason']==case['expected_reason'] and not result['status_business_SELECTs'])
        elif outcome=='avoid':
            exact=(kind in (None,'no_read') and result['reply'] is not None and not result['model_error']
                and not result['model_contract_error'] and (result['proposal'] is None
                    or isinstance(result['proposal'],dict) and not result['proposal'].get('tool_calls')))
        else:
            exact=result['source_cancelled'] and not result['model_used'] and not result['status_business_SELECTs']
        result['final_expected_task_outcome']=bool(exact)
        result['scope_matches_expected']=(not result['source_cancelled'])==case['expected_scope_allowed']
    (output/'evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def sample_repetition(model,protocol,cases,repetition,output,*,on_context=None,before_execution=None,before_publication=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=False);results=[]
    for index,case in enumerate(cases):
        order=list(protocol['arms'])
        if (repetition+index)%2!=1:order.reverse()
        row={'case':case['id'],'repetition':repetition,'arm_order':order,'arms':{}}
        for arm in order:
            row['arms'][arm]=run_branch(model,protocol,case,repetition,arm,output/case['id']/arm,
                on_context=on_context,before_execution=before_execution,before_publication=before_publication)
        results.append(row)
        summary={'repetition':repetition,'arm_order_rule':protocol['sampling']['arm_order_rule'],
            'completed_cases':len(results),'cases':results}
        (output/'evaluation.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary

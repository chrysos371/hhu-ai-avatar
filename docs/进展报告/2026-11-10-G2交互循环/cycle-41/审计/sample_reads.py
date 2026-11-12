"""Shared-proposal lab branches; executor never receives expected/gold tool data."""
from contextlib import ExitStack, closing
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled
from avatar.lab.trusted_local_read import LabReadSession


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def business(memory):
    return {name: [dict(r) for r in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
            for name in ('memory_reminders', 'memory_reminder_deliveries', 'memory_action_receipts')}


def decode_call(proposal):
    calls = proposal.get('tool_calls', [])
    if not isinstance(calls, list) or len(calls) != 1:
        raise ValueError('one well-formed tool call is required')
    call = calls[0]
    function = call.get('function')
    if (call.get('type') != 'function' or not isinstance(call.get('id'), str) or not call['id']
            or not isinstance(function, dict) or not isinstance(function.get('name'), str)
            or not isinstance(function.get('arguments'), str) or len(function['arguments']) > 8192):
        raise ValueError('malformed native tool proposal')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate tool JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('nonfinite JSON constant')
    try:
        arguments = json.loads(function['arguments'], object_pairs_hook=unique, parse_constant=constant)
    except (TypeError, ValueError):
        arguments = None  # actual service issues invalid_arguments, no invented success
    return call, function['name'], arguments


def run_arm(model, tools, retry_system, messages, first, branch, mode, invoke):
    """Only actual proposal/current source reach service; no case/gold labels here."""
    session, phase = branch['session'], branch['phase']
    record = {'mode': mode, 'reply': None, 'reply_origin': None, 'first_read': None,
              'retry_proposal': None, 'retry_error': None, 'retry_read': None,
              'final_tool': None, 'final_arguments': None, 'source_cancelled': False,
              'failure': None, 'tool_attempts': 0}
    try:
        phase[0] = 'initial-source-check'
        session.ensure_current()
        calls = first.get('tool_calls', [])
        record['tool_attempts'] = len(calls)
        if not calls:
            record['reply'] = first.get('content') or ''
            record['reply_origin'] = 'model_no_read'
            session.ensure_current()
            return record
        try:
            call, tool, arguments = decode_call(first)
        except ValueError as error:
            record.update(reply='工具提案格式不能核验，本次没有可靠读取提醒信息。',
                          reply_origin='malformed_proposal', failure=str(error))
            return record
        phase[0] = 'first-execute'
        result = session.execute(tool, arguments)
        record['first_read'] = {'tool': tool, 'arguments': arguments, 'result': asdict(result)}
        if not result.ok and mode == 'single_repair':
            session.ensure_current()
            feedback = {'ok': False, 'error': result.error}
            retry_messages = messages + [first, {'role': 'tool', 'tool_call_id': call['id'],
                'content': json.dumps(feedback, ensure_ascii=False)},
                {'role': 'system', 'content': retry_system}]
            phase[0] = 'error-feedback-model'
            try:
                retry = invoke('repair', retry_messages)
                record['retry_proposal'] = retry
                session.ensure_current()
                if retry.get('tool_calls'):
                    _, next_tool, next_args = decode_call(retry)
                    record['tool_attempts'] += len(retry['tool_calls'])
                    phase[0] = 'retry-execute'
                    result = session.execute(next_tool, next_args)
                    record['retry_read'] = {'tool': next_tool, 'arguments': next_args, 'result': asdict(result)}
                    tool, arguments = next_tool, next_args
            except Cancelled:
                raise
            except Exception as error:
                record['retry_error'] = type(error).__name__+': '+str(error)[:240]
                session.ensure_current()
        phase[0] = 'publication'
        record['reply'] = session.publish(result)
        record['reply_origin'] = 'trusted_read_fixed' if result.ok else 'guarded_read_failure'
        if result.ok:
            record['final_tool'], record['final_arguments'] = tool, arguments
    except Cancelled as error:
        record.update(source_cancelled=True, reply=None, reply_origin='source_cancelled',
                      failure=type(error).__name__+': '+str(error))
    finally:
        phase[0] = 'idle'
    return record


def sample_case(model, protocol, case, repetition, output, *, on_context=None, before_initial=None):
    """Commit actual sources before shared native work; expected labels score afterwards."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    phases = {}; branches = {}; result = {'case': case['id'], 'repetition': repetition,
        'initial_proposal': None, 'initial_error': None, 'initial_model_calls': 0,
        'repair_model_calls': 0, 'branches': {}, 'case_source_denied': False,
        'scope_matches_expected': None, 'Avatar_application_turns': 0}
    with ExitStack() as stack:
        for mode in ('gate_only', 'single_repair'):
            memory = stack.enter_context(closing(MemoryStore(':memory:')))
            phase = ['startup']; trace = []
            memory._conn.set_trace_callback(lambda sql, p=phase, t=trace: t.append({'phase': p[0], 'sql': sql}))
            session = LabReadSession(memory, f'c41-{case["id"]}-{repetition}-{mode}')
            phase[0] = 'seed'
            for seed in protocol['seed_rows']:
                values = dict(seed)
                if values['id'] == 1 and 'seed_title_override' in case:
                    values['title'] = case['seed_title_override']
                memory._conn.execute('INSERT INTO memory_reminders(id,title,status,due_at,created_at,notified_at) '
                                     'VALUES (:id,:title,:status,:due_at,:created_at,:notified_at)', values)
            memory._conn.commit()
            phase[0] = 'source-entry'
            for setup in case.get('setup', []):
                session.begin_turn(setup)
            ident = session.begin_turn(case['text'])
            phase[0] = 'projection-before'
            before = business(memory)
            branches[mode] = {'memory': memory, 'session': session, 'phase': phase, 'trace': trace,
                'before': before, 'before_changes': memory._conn.total_changes, 'source_message_id': ident}
            phases[mode] = phase

        def invoke(phase, messages):
            if on_context:
                on_context({'phase': phase, 'repetition': repetition, 'case': case['id']})
            if phase == 'initial':
                result['initial_model_calls'] += 1
            else:
                result['repair_model_calls'] += 1
            return model.chat_tools(messages, tools=protocol['tools'], temperature=0, max_tokens=256)

        messages = [{'role': 'system', 'content': protocol['initial_system']},
                    {'role': 'user', 'content': case['text']}]
        try:
            if before_initial:
                before_initial(branches)
            for branch in branches.values():
                branch['phase'][0] = 'before-model-source-check'
                branch['session'].ensure_current()
            result['initial_proposal'] = invoke('initial', messages)
            for branch in branches.values():
                branch['phase'][0] = 'after-model-source-check'
                branch['session'].ensure_current()
        except Cancelled as error:
            result['case_source_denied'] = True
            result['initial_error'] = type(error).__name__+': '+str(error)
        except Exception as error:
            result['initial_error'] = type(error).__name__+': '+str(error)[:240]

        for mode, branch in branches.items():
            if result['initial_error'] is not None:
                outcome = {'reply': None, 'reply_origin': 'source_cancelled' if result['case_source_denied'] else 'initial_model_error',
                    'source_cancelled': result['case_source_denied'], 'failure': result['initial_error'],
                    'first_read': None, 'retry_read': None, 'retry_proposal': None,
                    'final_tool': None, 'final_arguments': None, 'tool_attempts': 0}
            else:
                outcome = run_arm(model, protocol['tools'], protocol['repair_system'],
                    messages, result['initial_proposal'], branch, mode, invoke)
            memory = branch['memory'];branch['phase'][0] = 'projection-after'
            after = business(memory)
            outcome.update(business_before=branch['before'], business_after=after,
                business_unchanged=branch['before']==after,
                total_changes_before=branch['before_changes'], total_changes_after=memory._conn.total_changes,
                no_post_source_writes=branch['before_changes']==memory._conn.total_changes,
                source_message_id=branch['source_message_id'], source_revision=branch['session']._turn.revision,
                source_scope=branch['session']._turn.scope,
                independent_turn_allowed=branch['session']._turn.allowed,
                session_id=branch['session'].session_id,
                sqlite_backend='actual sqlite3 :memory:, synthetic business rows; no disk durability approval')
            branch['phase'][0] = 'archive'
            dump = '\n'.join(memory._conn.iterdump())+'\n'
            (output/(mode+'.sql')).write_text(dump)
            outcome['SQL_dump_sha256'] = hashlib.sha256(dump.encode()).hexdigest()
            outcome['SQL_trace'] = branch['trace']
            outcome['business_status_SELECTs'] = sum('FROM memory_reminders r' in r['sql']
                and r['phase'] in ('first-execute', 'retry-execute') for r in branch['trace'])
            # Gold enters only scoring; execution above never receives it.
            if not case['expected_scope_allowed']:
                exact = result['case_source_denied'] and result['initial_model_calls']==0
            elif case['tool'] is None:
                exact = (result['initial_error'] is None and not result['initial_proposal'].get('tool_calls')
                         and not outcome['first_read'] and not outcome['retry_read'])
            else:
                exact = (outcome['reply_origin']=='trusted_read_fixed' and outcome['final_tool']==case['tool']
                         and canonical(outcome['final_arguments'])==canonical(case['args']))
            outcome['final_exact_expected_route'] = bool(exact)
            result['branches'][mode] = outcome
        result['scope_matches_expected'] = (not result['case_source_denied']) == case['expected_scope_allowed']
    (output/'evaluation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


def sample_repetition(model, protocol, cases, repetition, output, *, on_context=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for case in cases:
        row = sample_case(model, protocol, case, repetition, output/case['id'], on_context=on_context)
        results.append(row)
        summary = {'repetition': repetition, 'completed_cases': len(results), 'cases': results}
        (output/'evaluation.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    return summary

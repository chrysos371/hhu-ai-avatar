"""Sample an actual source-owned SDK query then cognition/generation, no gold input."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import time

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from avatar.lab.history_representation import history_representation, score_history_answer


def projection(memory):
    return {name:[dict(row) for row in memory._conn.execute('SELECT * FROM '+name)]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


class ObservedEngine:
    """Record actual public engine calls; OpenAI wire evidence is collected outside."""
    def __init__(self,engine,context,native_counter):
        self.engine,self.context,self.native_counter = engine,context,native_counter
        self.available = engine.available
        self.calls = []

    def _invoke(self,role,messages,options):
        self.context({'call_role':role})
        value = {'role':role,'messages':messages,'options':options,
            'native_counter_before':self.native_counter(),'raw_reply':None,'error':None}
        self.calls.append(value)
        try:
            method = self.engine.chat_analysis if role == 'cognition' else self.engine.chat
            value['raw_reply'] = method(messages,**options)
            return value['raw_reply']
        except Exception as error:
            value['error'] = type(error).__name__+': '+str(error)[:300]
            raise
        finally:
            value['native_counter_after'] = self.native_counter()

    def chat_analysis(self,messages,**options):
        return self._invoke('cognition',messages,options)

    def chat(self,messages,**options):
        return self._invoke('generation',messages,options)


def sample_trial(engine,case,arm,repetition,out,*,on_context,native_counter=lambda:0):
    out = Path(out); assert not out.exists(); out.mkdir(parents=True)
    context = {'repetition':repetition,'case':case['id'],'arm':arm,'phase':'startup','call_role':None}
    def update(values):
        context.update(values); on_context(dict(context))
    update({})
    observed = ObservedEngine(engine,update,native_counter)
    events = []; phase = {'name':'startup'}
    def trace(sql): events.append({'phase':phase['name'],'sql':sql})
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory,llm=observed,session_id='c47-history-'+case['id'])
        memory._conn.set_trace_callback(trace)
        seed = case['seed']; ident = seed['record_id']
        due = datetime.fromisoformat(seed['due_date']).timestamp()
        phase['name'] = 'controlled_seed'
        with memory.transaction():
            if seed['status_at_query'] != 'missing':
                memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,status,created_at,notified_at) VALUES (?,?,?,?,?,?)',
                    (ident,seed['title'],due,seed['status_at_query'],time.time(),time.time()-60 if seed['client_ack_recorded'] else None))
                if seed['client_ack_recorded']:
                    memory._conn.execute('INSERT INTO memory_reminder_deliveries(reminder_id,created_at,acknowledged_at) VALUES (?,?,?)',
                        (ident,time.time()-60,time.time()-30))
        phase['name'] = 'audit_projection_before_query'
        business_before_query = projection(memory)
        with history_representation(arm):
            phase['name'] = 'actual_query'; update({'phase':'actual_query','call_role':None})
            started = time.monotonic()
            query = bot.respond(case['query_text'],mode='reminder_query')
            query_seconds = time.monotonic()-started
            assert not observed.calls
            phase['name'] = 'audit_projection_after_query'
            business_after_query = projection(memory)
            assert business_after_query == business_before_query
            query_context = memory.get_short_term()
            phase['name'] = 'archive_after_query'
            query_dump = out/'after-query.sql'; query_dump.write_text('\n'.join(memory._conn.iterdump())+'\n')
            phase['name'] = 'controlled_actor_after_query'
            operation = case['independent_actor_after_query']
            if operation == 'create_record':
                with memory.transaction():
                    memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,status,created_at) VALUES (?,?,?,?,?)',
                        (ident,seed['title'],due,'active',time.time()))
            elif operation in ('set_completed','set_cancelled'):
                bot.reminders.set_status(ident,'completed' if operation == 'set_completed' else 'cancelled')
            else:
                raise ValueError('unregistered controlled actor operation')
            phase['name'] = 'audit_projection_before_ordinary'
            business_before_ordinary = projection(memory)
            facts_before = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_fragments')]
            phase['name'] = 'actual_ordinary'; update({'phase':'actual_ordinary','call_role':None})
            started = time.monotonic()
            result = bot.respond(case['followup_text'])
            ordinary_seconds = time.monotonic()-started
            phase['name'] = 'audit_projection_after_ordinary'
            business_after_ordinary = projection(memory)
            facts_after = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_fragments')]
            phase['name'] = 'archive_after_ordinary'
            ordinary_dump = out/'after-ordinary.sql'; ordinary_dump.write_text('\n'.join(memory._conn.iterdump())+'\n')
            messages = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages')]
            assert len(messages) == 4 and [r['role'] for r in messages] == ['user','assistant','user','assistant']
            assert messages[0]['content'] == case['query_text'] and messages[1]['content'] == query['reply']
            assert messages[2]['content'] == case['followup_text'] and messages[3]['content'] == result['reply']
            assert query['reminder_query']['source_message_id'] == messages[0]['id']
            assert result['conversation']['user_message_id'] == messages[2]['id']
        phase['name'] = 'finished'
        # Gold is first consumed only AFTER all source/model/SQL execution.
        generation = [call for call in observed.calls if call['role'] == 'generation']
        raw_generation = generation[-1]['raw_reply'] if generation else None
        receipt = {'scope':'actual in-memory SQLite and Avatar orchestration; controlled actor is not model execution',
            'case':case['id'],'arm':arm,'repetition':repetition,'query_text':case['query_text'],
            'followup_text':case['followup_text'],'query_result':query,'ordinary_result':result,
            'query_seconds':query_seconds,'ordinary_seconds':ordinary_seconds,
            'actual_model_interface_calls':observed.calls,'query_model_calls':0,
            'query_context':query_context,'business_before_query':business_before_query,
            'business_after_query':business_after_query,'business_before_ordinary':business_before_ordinary,
            'business_after_ordinary':business_after_ordinary,'controlled_actor_operation':operation,
            'facts_before':facts_before,'facts_after':facts_after,'SQL_trace':events,'messages':messages,
            'raw_generation_score':score_history_answer(raw_generation,case['expected']),
            'final_reply_score':score_history_answer(result['reply'],case['expected']),
            'expected_registered_after_execution':case['expected'],
            'business_unchanged_by_query_and_ordinary':business_before_query == business_after_query and business_before_ordinary == business_after_ordinary,
            'no_new_user_facts':facts_before == facts_after,
            'model_modes_valid':result['analysis_mode'] == result['generation_mode'] == 'llm',
            'dump_files':['after-query.sql','after-ordinary.sql'],'native_quality_claim':False}
        (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        return receipt

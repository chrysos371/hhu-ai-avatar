"""Actual SDK initial query/actor/optional requery/ordinary model sampling."""
from contextlib import closing
from datetime import datetime
import json
from pathlib import Path
import time

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from text_shape import text_shape
from avatar.lab.minimal_history_observation import observation_representation


def projection(memory):
    return {name:[dict(row) for row in memory._conn.execute('SELECT * FROM '+name)]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


class ObservedEngine:
    def __init__(self,engine,context,native_counter):
        self.engine,self.context,self.native_counter = engine,context,native_counter
        self.available = engine.available; self.calls = []

    def _invoke(self,role,messages,options):
        self.context({'call_role':role})
        row = {'role':role,'messages':messages,'options':options,
            'native_counter_before':self.native_counter(),'raw_reply':None,'error':None}
        self.calls.append(row)
        try:
            method = self.engine.chat_analysis if role == 'cognition' else self.engine.chat
            row['raw_reply'] = method(messages,**options)
            return row['raw_reply']
        except Exception as error:
            row['error'] = type(error).__name__+': '+str(error)[:300]
            raise
        finally:
            row['native_counter_after'] = self.native_counter()

    def chat_analysis(self,messages,**options): return self._invoke('cognition',messages,options)
    def chat(self,messages,**options): return self._invoke('generation',messages,options)


def sample_trial(engine,case,arm,repetition,out,*,on_context,native_counter=lambda:0):
    out = Path(out); assert not out.exists(); out.mkdir(parents=True)
    context = {'repetition':repetition,'case':case['id'],'arm':arm,'phase':'startup','call_role':None}
    def update(values):
        context.update(values); on_context(dict(context))
    update({}); observed = ObservedEngine(engine,update,native_counter)
    phase = {'name':'startup'}; SQL = []
    def trace(statement): SQL.append({'phase':phase['name'],'sql':statement})
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory,llm=observed,session_id='c50-history-'+case['id'])
        memory._conn.set_trace_callback(trace)
        seed = case['seed']; ident = seed['record_id']
        due = datetime.fromisoformat(seed['due_date']).timestamp()
        phase['name'] = 'controlled_seed'
        with memory.transaction():
            if seed['status_at_query'] != 'missing':
                memory._conn.execute('''INSERT INTO memory_reminders
                    (id,title,due_at,status,created_at,notified_at) VALUES (?,?,?,?,?,?)''',
                    (ident,seed['title'],due,seed['status_at_query'],time.time(),time.time()-60 if seed['client_ack_recorded'] else None))
                if seed['client_ack_recorded']:
                    memory._conn.execute('INSERT INTO memory_reminder_deliveries(reminder_id,created_at,acknowledged_at) VALUES (?,?,?)',
                        (ident,time.time()-60,time.time()-30))
        observations = []; dumps = []
        def query(number):
            phase['name'] = 'audit_before_query_'+str(number); before = projection(memory)
            phase['name'] = 'actual_query_'+str(number); update({'phase':phase['name'],'call_role':None})
            started = time.monotonic(); result = bot.respond(case['query_text'],mode='reminder_query')
            seconds = time.monotonic()-started
            assert not observed.calls
            phase['name'] = 'audit_after_query_'+str(number); after = projection(memory)
            assert before == after
            phase['name'] = 'archive_after_query_'+str(number)
            name = 'after-query-'+str(number)+'.sql'
            (out/name).write_text('\n'.join(memory._conn.iterdump())+'\n'); dumps.append(name)
            observations.append({'number':number,'result':result,'text':case['query_text'],
                'seconds':seconds,'business_before':before,'business_after':after,
                'model_context':memory.get_short_term(),'dump_file':name})
        with observation_representation(arm):
            query(1)
            phase['name'] = 'controlled_actor_after_first_query'; operation = case['independent_actor_after_query']
            if operation == 'create_record':
                with memory.transaction():
                    memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,status,created_at) VALUES (?,?,?,?,?)',
                        (ident,seed['title'],due,'active',time.time()))
            elif operation in ('set_completed','set_cancelled'):
                bot.reminders.set_status(ident,'completed' if operation == 'set_completed' else 'cancelled')
            else: raise ValueError('unregistered actor operation')
            if case['repeat_query_after_actor']: query(2)
            phase['name'] = 'audit_before_ordinary'; before_ordinary = projection(memory)
            facts_before = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_fragments')]
            phase['name'] = 'actual_ordinary'; update({'phase':'actual_ordinary','call_role':None})
            started = time.monotonic(); result = bot.respond(case['followup_text'])
            ordinary_seconds = time.monotonic()-started
            phase['name'] = 'audit_after_ordinary'; after_ordinary = projection(memory)
            facts_after = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_fragments')]
            phase['name'] = 'archive_after_ordinary'; name = 'after-ordinary.sql'
            (out/name).write_text('\n'.join(memory._conn.iterdump())+'\n'); dumps.append(name)
            messages = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages ORDER BY id')]
            assert len(messages) == 2*(len(observations)+1)
            for index,observation in enumerate(observations):
                source,answer = messages[2*index:2*index+2]
                assert source['role'] == 'user' and source['content'] == case['query_text']
                assert answer['role'] == 'assistant' and answer['content'] == observation['result']['reply']
                assert observation['result']['reminder_query']['source_message_id'] == source['id']
            assert messages[-2]['content'] == case['followup_text']
            assert messages[-1]['content'] == result['reply']
            assert result['conversation']['user_message_id'] == messages[-2]['id']
        # No registered expected value is used until source/model/SQL execution ends.
        generation = [c for c in observed.calls if c['role'] == 'generation']
        raw = generation[-1]['raw_reply'] if generation else None
        receipt = {'scope':'actual SDK/SQLite with controlled seed and separate actor; not physical delivery',
            'case':case['id'],'group':case['group'],'arm':arm,'repetition':repetition,
            'query_observations':observations,'query_text':case['query_text'],'followup_text':case['followup_text'],
            'actual_query_turns':len(observations),'actual_ordinary_turns':1,'query_model_calls':0,
            'ordinary_result':result,'ordinary_seconds':ordinary_seconds,'actual_model_interface_calls':observed.calls,
            'controlled_actor_operation':operation,'business_before_ordinary':before_ordinary,
            'business_after_ordinary':after_ordinary,'facts_before':facts_before,'facts_after':facts_after,
            'SQL_trace':SQL,'messages':messages,'dump_files':dumps,
            'raw_text_shape':text_shape(raw),
            'final_text_shape':text_shape(result['reply']),
            'oracle_observation_registered_after_execution':case['oracle_observation'],
            'review_axes_registered_after_execution':case['review_axes'],
            'semantic_review_pending':True,
            'business_unchanged_by_query_and_ordinary':all(o['business_before']==o['business_after'] for o in observations) and before_ordinary==after_ordinary,
            'no_new_user_facts':facts_before==facts_after,
            'model_modes_valid':result['analysis_mode']==result['generation_mode']=='llm','native_quality_claim':False}
        (out/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        return receipt

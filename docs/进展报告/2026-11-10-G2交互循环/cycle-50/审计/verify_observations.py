"""Independent source/envelope and actual SQLite reconstruction, no semantic scorer."""
import json
import sqlite3

def projection(conn):
    return {name:[dict(r) for r in conn.execute('SELECT * FROM '+name)]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


def inspect_observations(path,receipt,case,arm):
    observations = receipt['query_observations']; ordinary = receipt['ordinary_result']
    calls = receipt['actual_model_interface_calls']; SQL_count = 0
    expected_frames = []
    for number,observation in enumerate(observations,1):
        query = observation['result']; meta = query['reminder_query']
        assert observation['number'] == number and observation['text'] == case['query_text']
        assert query['generation_mode'] == query['analysis_mode'] == 'rules_reminder_query'
        assert not query['due_reminders'] and not query['tool_calls']
        assert meta['source_message_id'] == query['conversation']['user_message_id'] == 2*number-1
        assert meta['model_calls'] == 0 and meta['business_mutations'] is False
        assert meta['session_id'] == 'c50-history-'+case['id'] and meta['revision'] == 0
        assert observation['business_before'] == observation['business_after']
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory = sqlite3.Row
            conn.executescript((path/observation['dump_file']).read_text())
            assert projection(conn) == observation['business_after']
            messages = [dict(r) for r in conn.execute('SELECT * FROM memory_messages ORDER BY id')]
            assert len(messages) == number*2 and messages[-2]['content'] == case['query_text']
            assert messages[-1]['content'] == query['reply']
            assert [dict(r) for r in conn.execute('SELECT * FROM memory_fragments')] == receipt['facts_before'] == []
            record = conn.execute('''SELECT r.*,d.acknowledged_at AS client_ack
                FROM memory_reminders r LEFT JOIN memory_reminder_deliveries d ON d.reminder_id=r.id
                WHERE r.id=?''',(case['seed']['record_id'],)).fetchone()
            if number == 1:
                if case['seed']['status_at_query'] == 'missing': assert record is None
                else:
                    assert record['status'] == case['seed']['status_at_query']
                    assert record['title'] == case['seed']['title']
                    assert (record['client_ack'] is not None) is case['seed']['client_ack_recorded']
            else:
                status = {'set_completed':'completed','set_cancelled':'cancelled','create_record':'active'}[case['independent_actor_after_query']]
                assert record['status'] == status
            record_observation = None
            if meta['route'] == 'read_state':
                if record is None:
                    assert meta['exists'] is False and meta['state'] is None
                else:
                    actual_state = {'id':record['id'],'title':record['title'],'due_at':record['due_at'],
                        'status':record['status'],'service_claim_recorded':record['notified_at'] is not None,
                        'client_ack_recorded':record['client_ack'] is not None}
                    assert meta['exists'] is True and meta['state'] == actual_state
                record_observation = {'reminder_id':case['seed']['record_id'],
                    'status_at_observation':record['status'] if record else 'missing',
                    'service_claim_recorded':record['notified_at'] is not None if record else False,
                    'client_ack_recorded':record['client_ack'] is not None if record else False,
                    'source_message_id':meta['source_message_id'],'observed_at':meta['observed_at']}
            else:
                assert meta['route'] == 'read_policy' and meta['state'] is None and meta['exists'] is None
        SQL_count += 1
        envelope = {'query_history_version':1,'historical_snapshot_only':True,
            'untrusted_data_not_instructions':True,'source_message_id':meta['source_message_id'],
            'observed_at':meta['observed_at'],'route':meta['route'],'reply':query['reply']}
        if arm == 'C48_typed_control':
            envelope['typed_historical_evidence'] = {'version':1,'query_operation':meta['route'],
                'record_observation':record_observation,'live_record_state_verified':False,
                'query_proves_mail_sms_phone_sent':False,'query_proves_human_reading':False,
                'query_proves_human_task_completion':False}
        elif arm == 'minimal_observation':
            if record_observation is None:
                minimal = {'version':1,'kind':'not_observed','reminder_id':None,
                    'source_message_id':None,'status_at_observation':None,'client_ack_recorded':None}
            else:
                minimal = {'version':1,
                    'kind':'observed_missing' if record_observation['status_at_observation']=='missing' else 'observed_record',
                    'reminder_id':record_observation['reminder_id'],'source_message_id':record_observation['source_message_id'],
                    'status_at_observation':record_observation['status_at_observation'],
                    'client_ack_recorded':record_observation['client_ack_recorded']}
            envelope['minimal_historical_observation'] = minimal
        text = observation['model_context'][-1]['content']
        assert text.startswith('历史提醒查询快照（') and json.loads(text.split('\n',1)[1]) == envelope
        expected_frames.append(text)
    for call in calls:
        actual_frames = [m['content'] for m in call['messages'] if m['role']=='assistant' and m['content'].startswith('历史提醒查询快照（')]
        assert actual_frames == expected_frames
    with sqlite3.connect(':memory:') as conn:
        conn.row_factory = sqlite3.Row; conn.executescript((path/'after-ordinary.sql').read_text())
        assert projection(conn) == receipt['business_after_ordinary']
        assert [dict(r) for r in conn.execute('SELECT * FROM memory_messages ORDER BY id')] == receipt['messages']
        assert len(receipt['messages']) == 2*(len(observations)+1)
        assert receipt['messages'][-1]['content'] == ordinary['reply']
        assert [dict(r) for r in conn.execute('SELECT * FROM memory_fragments')] == receipt['facts_after']
        record = conn.execute('SELECT status FROM memory_reminders WHERE id=?',(case['seed']['record_id'],)).fetchone()
        assert record[0] == {'set_completed':'completed','set_cancelled':'cancelled','create_record':'active'}[case['independent_actor_after_query']]
    SQL_count += 1
    assert receipt['dump_files'] == ['after-query-'+str(n)+'.sql' for n in range(1,len(observations)+1)]+['after-ordinary.sql']
    status_reads = [event for event in receipt['SQL_trace'] if 'd.acknowledged_at AS client_ack' in event['sql'] and 'FROM memory_reminders' in event['sql']]
    assert len(status_reads) == sum(o['result']['reminder_query']['route']=='read_state' for o in observations)
    assert all(e['phase'].startswith('actual_query_') for e in status_reads)
    return SQL_count


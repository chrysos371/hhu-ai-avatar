"""Real loopback HTTP contracts, models disabled by shared fixture."""
import time
from contextlib import closing
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from test_web_api_v1 import api_v1


def seed(server):
    with closing(MemoryStore(server.db_path)) as memory:
        store = ReminderStore(memory)
        row = store.create('提醒我明天下午3点HTTP队列实验')
        with memory.transaction():
            memory._conn.execute('UPDATE memory_reminders SET due_at=? WHERE id=?', (time.time()-60,row['id']))
    return row['id']


def test_http_replay_explicit_ack_and_legacy_claim_compatibility(api_v1):
    request, server = api_v1; rid = seed(server)
    assert len(request('/api/v1/reminders/due', {})[1]['data']) == 1
    assert request('/api/v1/reminders/due', {})[1]['data'] == []
    code, body = request('/api/v1/reminders/deliveries/pending', {})
    assert code == 200
    pending = body['data']; event = pending['items'][0]['delivery_id']
    assert pending['revision'] == 0 and pending['instance_id'] == server.session_id
    assert request('/api/v1/reminders/deliveries/pending', {})[1]['data'] == pending
    payload = {'instance_id':pending['instance_id'],'revision':pending['revision']}
    path = f'/api/v1/reminders/deliveries/{event}/ack'
    code, ack = request(path, payload)
    assert code == 200 and ack['data']['acknowledged_at']
    assert request(path,payload)[1]['data'] == ack['data']
    assert request('/api/v1/reminders/deliveries/pending', {})[1]['data']['items'] == []
    row = request('/api/v1/reminders')[1]['data'][0]
    assert row['id'] == rid and row['delivery_acknowledged_at'] == ack['data']['acknowledged_at']
    assert request('/api/v1/conversation/actions')[1]['data']['items'] == []


@pytest.mark.parametrize('payload', [None,{'extra':1}])
def test_pending_rejects_get_and_unknown_fields(api_v1, payload):
    request, server = api_v1; seed(server)
    assert request('/api/v1/reminders/deliveries/pending',payload)[0] in (404,422)
    assert request('/api/v1/reminders/deliveries/pending?extra=1',{})[0] == 422


@pytest.mark.parametrize('payload', [{},{'instance_id':'wrong','revision':0},{'instance_id':True,'revision':0},
    {'instance_id':'missing-revision'},{'revision':True},{'revision':-1},{'revision':1.5},{'revision':'0'}, {'revision':2**63},
    {'revision':0,'extra':1}])
def test_invalid_or_wrong_instance_ack_never_mutates(api_v1, payload):
    request, server = api_v1; seed(server)
    pending = request('/api/v1/reminders/deliveries/pending',{})[1]['data']
    event = pending['items'][0]['delivery_id']
    body = dict(payload)
    if 'revision' in body and 'instance_id' not in body: body['instance_id'] = server.session_id
    assert request(f'/api/v1/reminders/deliveries/{event}/ack',body)[0] in (409,422)
    assert len(request('/api/v1/reminders/deliveries/pending',{})[1]['data']['items']) == 1


def test_auth_revision_and_deleted_delivery_are_fenced(api_v1):
    request, server = api_v1; rid = seed(server)
    assert request('/api/v1/reminders/deliveries/pending',{},token=False)[0] == 403
    pending = request('/api/v1/reminders/deliveries/pending',{})[1]['data']
    event = pending['items'][0]['delivery_id']
    path = f'/api/v1/reminders/deliveries/{event}/ack'
    payload = {'instance_id':server.session_id,'revision':0}
    assert request(path,payload,token=False)[0] == 403
    with closing(MemoryStore(server.db_path)) as memory:
        fragment = memory.remember_user('名字','HTTP隐私实验名');memory.forget(fragment)
    code, body = request(path,payload)
    assert code == 409 and body['error']['code'] == 'delivery_revision_changed'
    current = request('/api/v1/reminders/deliveries/pending',{})[1]['data']
    assert current['revision'] > 0 and len(current['items']) == 1
    with closing(MemoryStore(server.db_path)) as memory: ReminderStore(memory).delete(rid)
    payload['revision'] = current['revision']
    assert request(path,payload)[0] == 409
    assert request('/api/v1/reminders/deliveries/pending',{})[1]['data']['items'] == []

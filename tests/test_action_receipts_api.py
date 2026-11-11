from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from test_web_api_v1 import api_v1


def test_receipt_api_follows_actual_chat_and_privacy(api_v1):
    request, server = api_v1
    code, body = request('/api/v1/chat', {'text':'提醒我明天下午3点回执实验'})
    assert code == 200
    result = body['data']; source = result['conversation']['user_message_id']
    code, body = request('/api/v1/conversation/actions?source_message_id='+str(source)+'&revision=0')
    assert code == 200 and body['data'] == result['action_receipts']
    assert len(body['data']['items']) == 1 and body['data']['items'][0]['action'] == 'reminder.created'
    assert '回执实验' not in json.dumps(body['data'],ensure_ascii=False)
    assert request('/api/v1/conversation/actions', token=False)[0] == 403
    with closing(MemoryStore(server.db_path)) as memory:
        private = memory.remember_user('名字','独立回执遗忘名'); memory.forget(private)
    assert request('/api/v1/conversation/actions')[1]['data']['items'] == []
    assert request('/api/v1/conversation/actions?revision=0')[0] == 409


@pytest.mark.parametrize('query',['limit=0','limit=201','after_id=-1','revision=-1','source_message_id=0',
                                'limit=x','limit=1&limit=2','unknown=1','source_message_id=9223372036854775808'])
def test_receipt_api_rejects_bad_queries(api_v1,query):
    assert api_v1[0]('/api/v1/conversation/actions?'+query)[0] == 422

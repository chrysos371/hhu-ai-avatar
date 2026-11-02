import json
import threading
import urllib.error
import urllib.request

import pytest

from avatar.brain.memory import MemoryStore
from avatar.web import create_server


@pytest.fixture
def api(tmp_path, monkeypatch):
    from avatar.config import config
    monkeypatch.setattr(config.llm, 'api_key', '')
    monkeypatch.setattr(config.embedding, 'model', '')
    path = str(tmp_path / 'web.db')
    memory = MemoryStore(path)
    fid = memory.remember_user('名字', '小林', evidence='我叫小林')
    memory.close()
    server = create_server(path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def request(path, data=None, token=True, origin=None):
        headers = {}
        if token:
            headers['X-Avatar-Token'] = server.token
        if origin:
            headers['Origin'] = origin
        raw = None if data is None else json.dumps(data).encode()
        if raw is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(base + path, data=raw, headers=headers)
        try:
            with urllib.request.urlopen(req) as res:
                body = res.read()
                return res.status, json.loads(body) if 'application/json' in res.headers['Content-Type'] else body
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
    yield request, fid
    server.shutdown()
    thread.join()
    server.server_close()


def test_web_manages_real_memory_and_sources(api):
    request, fid = api
    assert request('/')[0] == 200
    assert request('/api/memories', token=False)[0] == 403
    rows = request('/api/memories')[1]['memories']
    assert rows[0]['content'] == '名字: 小林'
    detail = request(f'/api/memory?id={fid}')[1]['memory']
    assert detail['sources'][0]['evidence'] == '我叫小林'
    assert 'content_vector' not in detail
    assert request('/api/badhit', {'id': fid})[0] == 200
    assert request(f'/api/memory?id={fid}')[1]['memory']['bad_hits'] == 1
    new = request('/api/correct', {'id': fid, 'content': '阿岚'})[1]['id']
    assert len(request('/api/memories?history=1')[1]['memories']) == 2
    assert request('/api/forget', {'id': new})[0] == 200
    assert request('/api/memories?history=1')[1]['memories'] == []


def test_web_rejects_cross_origin_and_bad_input(api):
    request, fid = api
    assert request('/api/forget', {'id': fid}, origin='https://evil.example')[0] == 403
    assert request('/api/forget', {'id': True})[0] == 400
    assert request('/api/correct', {'id': fid, 'content': ''})[0] == 400
    assert request('/api/badhit', {'id': 999})[0] == 400
    assert request('/api/unknown', {})[0] == 404
    assert request(f'/api/memory?id={fid}')[0] == 200


def test_web_reminder_lifecycle_and_chat_state(api):
    request, _ = api
    row = request('/api/reminders', {'text': '提醒我2099年12月1日下午3点答辩'})[1]['reminder']
    assert request('/api/reminders')[1]['reminders'][0]['id'] == row['id']
    assert request('/api/reminder-status', {'id': row['id'], 'status': 'cancelled'})[0] == 200
    assert request('/api/reminders')[1]['reminders'][0]['status'] == 'cancelled'
    assert request('/api/delete-reminder', {'id': row['id']})[0] == 200
    assert request('/api/reminders')[1]['reminders'] == []
    state = request('/api/state')[1]
    assert state['energy'] == .5
    assert request('/api/due', {})[1]['reminders'] == []


def test_web_chat_persists_evidence_and_forget_clears_context(api):
    request, fid = api
    result = request('/api/chat', {'text': '我喜欢游泳'})
    assert result[0] == 200
    assert result[1]['energy'] > .5
    rows = request('/api/memories')[1]['memories']
    preference = next(r for r in rows if '游泳' in r['content'])
    assert preference['id'] in result[1]['recalled_ids']
    sources = request('/api/memory?id=' + str(preference['id']))[1]['memory']['sources']
    assert sources[0]['message_content'] == '我喜欢游泳'
    request('/api/forget', {'id': fid})
    result = request('/api/chat', {'text': '你还记得我叫什么名字吗'})[1]
    assert '小林' not in result['reply']
    assert fid not in result['recalled_ids']


def test_web_summary_tracks_same_session_across_requests(api):
    request, fid = api
    assert request('/api/chat', {'text': '这轮方案代号定为青岚，预算500元。'})[0] == 200
    for _ in range(12):
        assert request('/api/chat', {'text': '什么是云？'})[0] == 200
    summary = request('/api/summary')[1]['summary']
    assert '青岚' in str(summary['items'])
    assert summary['characters'] <= 1600
    source_id = next(r['message_id'] for r in summary['items'] if '青岚' in r['text'])
    assert request('/api/forget-summary-source', {'id': source_id})[0] == 200
    assert request('/api/summary')[1]['summary']['items'] == []
    assert request('/api/chat', {'text': '什么是云？'})[0] == 200
    assert '青岚' not in str(request('/api/summary')[1]['summary']['items'])
    request('/api/forget', {'id': fid})
    assert request('/api/summary')[1]['summary']['items'] == []


def test_web_checkbox_enables_tools_and_requires_boolean(api, monkeypatch):
    from avatar.tools.web_agent import WebAgent
    monkeypatch.setattr(WebAgent, 'run', lambda self, text, llm: {'reply': '真实工具结果',
        'sources': [{'title': '来源', 'url': 'https://example.com/'}], 'tool_calls': [{'tool': 'web_search', 'status': 'ok'}]})
    request, _ = api
    assert request('/api/chat', {'text': '搜索MCP', 'use_web': 'yes'})[0] == 400
    code, result = request('/api/chat', {'text': '搜索MCP', 'use_web': True})
    assert code == 200 and result['sources'][0]['url'] == 'https://example.com/'

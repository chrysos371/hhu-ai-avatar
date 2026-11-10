import asyncio
import json
from types import SimpleNamespace
import sys
import urllib.error
import pytest
from avatar.channels.qq.health import model_health, onebot_health, service_running


def test_model_probe_requires_local_exact_model_and_hides_failure(monkeypatch):
    config = SimpleNamespace(base_url='http://127.0.0.1:18081/v1', api_key='secret-never-print', model='test-model')
    calls = []
    class Response:
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def read(self, limit):return json.dumps({'data':[{'id':'test-model'}]}).encode()
    class Opener:
        def open(self, request, timeout):
            calls.append(request.full_url)
            return Response()
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    assert model_health(config) == {'ready':True, 'reason':'ok'}
    assert calls == ['http://127.0.0.1:18081/v1/models']
    config.model = 'absent'
    assert model_health(config)['reason'] == 'model_not_listed'
    config.base_url = 'https://cloud.example/v1'
    assert model_health(config)['reason'] == 'local_endpoint_required'
    assert len(calls) == 2


def test_probe_does_not_follow_redirect_or_leak_exception(monkeypatch):
    from avatar.channels.qq.health import NoRedirect
    assert NoRedirect().redirect_request(None, None, 302, '', {}, 'http://evil.example') is None
    class Opener:
        def open(self, *args, **kwargs):raise RuntimeError('secret-content')
    monkeypatch.setattr('urllib.request.build_opener', lambda *args: Opener())
    result = model_health(SimpleNamespace(base_url='http://127.0.0.1:1', api_key='secret', model='x'))
    assert result == {'ready':False, 'reason':'RuntimeError'}


@pytest.mark.parametrize('account,online,ready', [('123',True,True), ('456',True,False), ('123',False,False)])
def test_onebot_only_queries_status_never_sends_messages(monkeypatch, account, online, ready):
    actions = []
    class Socket:
        async def __aenter__(self):return self
        async def __aexit__(self, *args):pass
        async def send(self, raw):self.action=json.loads(raw)['action']; actions.append(self.action)
        async def recv(self):
            return json.dumps({'echo':self.action, 'retcode':0,
                               'data': {'user_id':account} if self.action=='get_login_info' else {'online':online}})
    monkeypatch.setitem(sys.modules, 'websockets', SimpleNamespace(connect=lambda *args, **kwargs: Socket()))
    result = asyncio.run(onebot_health(SimpleNamespace(url='ws://127.0.0.1:1', token='secret', account='123')))
    assert result['ready'] is ready
    assert actions == ['get_login_info','get_status']


def test_service_health_uses_held_lock(tmp_path):
    pytest.importorskip('fcntl')
    from avatar.channels.qq.bridge import InstanceLock
    assert service_running(tmp_path) is None
    lock = InstanceLock(tmp_path / 'service.lock')
    try:assert service_running(tmp_path) is True
    finally:lock.close()
    assert service_running(tmp_path) is False

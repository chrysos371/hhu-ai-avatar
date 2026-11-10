import asyncio
import time
import pytest
from avatar.channels.qq.onebot import parse_onebot
from avatar.channels.qq.protocol import IgnoredEvent


def payload(group=False):
    return {'time': int(time.time()), 'self_id': 12345, 'post_type': 'message',
            'message_type': 'group' if group else 'private',
            'sub_type': 'normal' if group else 'friend', 'user_id': 23456,
            'message_id': -42 if group else 42, 'group_id': 34567,
            'message': ([{'type': 'at', 'data': {'qq': '12345'}}] if group else [])
                       + [{'type': 'text', 'data': {'text': '你好'}}],
            'raw_message': 'ignored', 'font': 0,
            'sender': {'user_id': 23456, 'nickname': '测试'}}


def test_normalization_and_isolation():
    private = parse_onebot('12345', payload())
    group = parse_onebot('12345', payload(True))
    assert private.bot_id == 'onebot:12345'
    assert private.target == '23456' and group.target == '34567'
    assert private.context_key != group.context_key
    assert group.text == '你好' and group.message_id == '-42'


@pytest.mark.parametrize('change', [
    {'post_type': 'message_sent'}, {'self_id': 99999}, {'user_id': 12345},
    {'message': 'raw CQ string'}, {'message': [{'type': 'image', 'data': {}}]},
    {'message': [{'type': 'at', 'data': {'qq': 'all'}}]},
    {'message': [{'type': 'at', 'data': {'qq': '12345'}}]},
    {'message': [{'type': 'text', 'data': {'text': '没有at'}}]},
])
def test_ignore_non_target_unsupported_empty(change):
    event = payload(True)
    event.update(change)
    with pytest.raises(IgnoredEvent):
        parse_onebot('12345', event)


def test_private_temporary_session_ignored_and_literal_cq_retained():
    event = payload()
    event['sub_type'] = 'group'
    with pytest.raises(IgnoredEvent):
        parse_onebot('12345', event)
    event = payload()
    event['message'][0]['data']['text'] = '[CQ:at,qq=all]'
    assert parse_onebot('12345', event).text == '[CQ:at,qq=all]'


def test_settings_reject_remote_endpoints_and_hidden_token(monkeypatch, tmp_path):
    from avatar.channels.qq import onebot_app
    monkeypatch.setattr(onebot_app, 'PROJECT', tmp_path / 'project')
    settings = onebot_app.Settings('12345', 'offline-token-123456', root=tmp_path / 'qq')
    assert 'offline-token' not in repr(settings)
    for url in ['ws://example.com:6700', 'ws://127.0.0.1:6700?token=secret',
                'http://127.0.0.1:6700', 'ws://user:pass@127.0.0.1:6700']:
        with pytest.raises(ValueError):
            onebot_app.Settings('12345', 'offline-token-123456', url, tmp_path / 'qq')


def test_real_sdk_preprocessed_at_and_literal_send(monkeypatch, tmp_path):
    pytest.importorskip('nonebot.adapters.onebot.v11')
    from nonebot.adapters.onebot.v11 import GroupMessageEvent, PrivateMessageEvent
    from nonebot.adapters.onebot.v11.bot import _check_at_me
    from avatar.channels.qq import onebot_app
    from avatar.channels.qq.bridge import QQBridge
    from avatar.channels.qq.engine import AvatarEngine
    monkeypatch.setattr(onebot_app, 'PROJECT', tmp_path / 'project')
    async def run():
        settings = onebot_app.Settings('12345', 'offline-token-123456', root=tmp_path / 'qq')
        calls, sends = [], []
        def generate(m, db):
            calls.append(m.kind)
            return '[CQ:at,qq=all]纯文本'
        bridge = QQBridge(settings.root, engine=AvatarEngine(generate=generate))
        class Bot:
            self_id = '12345'
            async def send_group_msg(self, **kwargs):
                sends.append(('group', kwargs))
            async def send_private_msg(self, **kwargs):
                sends.append(('private', kwargs))
        bot = Bot()
        group = GroupMessageEvent.model_validate(payload(True))
        _check_at_me(bot, group)
        assert all(s.type != 'at' for s in group.message)
        try:
            assert (await onebot_app.dispatch(settings, bridge, bot, group)).status == 'sent'
            assert (await onebot_app.dispatch(settings, bridge, bot, group)).status == 'sent'
            private = PrivateMessageEvent.model_validate(payload())
            assert (await onebot_app.dispatch(settings, bridge, bot, private)).status == 'sent'
            assert calls == ['group', 'private'] and len(sends) == 2
            assert sends[0][1]['group_id'] == 34567
            assert sends[1][1]['user_id'] == 23456
            for _, args in sends:
                assert len(args['message']) == 1 and args['message'][0].type == 'text'
                assert args['message'][0].data['text'].startswith('[CQ:at')
        finally:
            await bridge.close()
    asyncio.run(run())

"""OneBot 11 normalization. Only friends' text and explicitly mentioned group text."""
from .protocol import IgnoredEvent, parse_event


def qq_number(value):
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise IgnoredEvent('invalid_qq_number')
    result = str(value)
    if not 1 <= len(result) <= 20 or int(result) <= 0:
        raise IgnoredEvent('invalid_qq_number')
    return str(int(result))


def parse_onebot(account, event):
    try:
        account = qq_number(account)
        if (event['post_type'] != 'message' or qq_number(event['self_id']) != account
                or qq_number(event['user_id']) == account):
            raise IgnoredEvent('not_incoming_account_message')
        kind = event['message_type']
        if kind not in ('private', 'group'):
            raise IgnoredEvent('unsupported_message_type')
        if kind == 'private' and event.get('sub_type') != 'friend':
            raise IgnoredEvent('not_friend_private_message')
        segments = event['message']
        # Array format preserves literal CQ text; never parse raw_message or CQ strings.
        if not isinstance(segments, list) or len(segments) > 128:
            raise IgnoredEvent('message_array_required')
        texts, mentioned = [], False
        for segment in segments:
            if segment['type'] == 'text' and isinstance(segment['data']['text'], str):
                texts.append(segment['data']['text'])
            elif (kind == 'group' and segment['type'] == 'at'
                  and str(segment['data'].get('qq')) == account):
                mentioned = True
            else:
                raise IgnoredEvent('unsupported_segment')
        if kind == 'group' and not mentioned:
            raise IgnoredEvent('not_mentioned')
        author = qq_number(event['user_id'])
        data = {'id': str(event['message_id']), 'timestamp': event['time'],
                'content': ''.join(texts),
                'author': {'member_openid': author} if kind == 'group' else {'user_openid': author}}
        if kind == 'group':
            data['group_openid'] = qq_number(event['group_id'])
        return parse_event('onebot:' + account, {
            't': 'GROUP_AT_MESSAGE_CREATE' if kind == 'group' else 'C2C_MESSAGE_CREATE',
            'd': data})
    except (KeyError, ValueError, TypeError, AttributeError):
        raise IgnoredEvent('unsupported_or_invalid_onebot_event') from None

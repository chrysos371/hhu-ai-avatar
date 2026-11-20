"""Recognize bounded, explicit requests for unavailable external operations.

This parser does not authorize actions, infer a speaker, or classify arbitrary
writing. The caller must first validate the real current user source. Unknown
language stays on the ordinary path, whose output needs its separate guard.
"""
from dataclasses import dataclass
import re

from .facts import _mask_quoted

_WRITING = re.compile(r'写|拟|润色|改写|改得|改成|改为|翻译|台词|小说|故事|剧本|扮演|引用|原样|复述')
_NEGATED = re.compile(r'不要|不用|不必|无需|别(?:替|帮|给|发|打|联系)|不需要|不想让你')
_HOW_TO = re.compile(r'怎么|如何|方法|教程|步骤|流程|说明|解释|有什么区别|什么意思')
_ACTOR = re.compile(r'^(?:(?:现在|马上|这就|等会儿|稍后)[，,\s]*)?'
    r'(?:请(?:你)?|麻烦(?:你)?|帮我|替我|代我|给我|能否|可否|能不能|可不可以|可以|能|'
    r'你(?:能不能|可不可以|能否|可否|可以|能|会|愿意|刚才|已经|是否|有没有|真|帮|替|把)|'
    r'我(?:想|希望)(?:让|请)你)')
_STATUS = re.compile(r'(?:了[吗么]?|没有|了吗|成功[了没吗]?|完成[了没吗]?|联系到[了没吗]?|发出去[了没吗]?)\s*[？?。!！]*$')
_CHANNELS = (
    ('email', re.compile(r'邮件|电邮|email', re.I)),
    ('sms', re.compile(r'短信|SMS', re.I)),
    ('message', re.compile(r'微信|QQ|消息|私信|留言', re.I)),
    ('phone', re.compile(r'电话|拨号|拨通|联系(?:到)?(?:他|她|同学|朋友|室友|老师)')),
)
_SEND = re.compile(r'发(?:送|出|过去)?|代发|重发|转发|联系|拨|打(?:个|一个)?电话|打给')
_LOCAL_STATUS = re.compile(r'提醒|闹钟|本机|本地|显示|聊天|对话框')


@dataclass(frozen=True)
class UnavailableRequest:
    channel: str
    kind: str

    def reply(self):
        if self.channel == 'external':
            return ('我没有替你发送短信或邮件，也没有拨打电话，当前没有接入这些接口。'
                    '如果你指的是本机提醒显示，需要查询对应提醒的显示记录才能确认。')
        label = {'email': '邮件代发', 'sms': '短信代发', 'message': '消息代发', 'phone': '拨打电话或代为联系'}[self.channel]
        if self.kind == 'status':
            return f'我没有替你执行{label}，当前没有接入这项接口；你或他人在其他平台的操作，我无法据此核验。'
        return f'当前没有接入{label}接口，我不能替你实际执行。需要办理时，请你自行操作。'


def explicit_unavailable_request(text, *, fictional=False):
    if not isinstance(text, str) or fictional:
        return None
    clean = _mask_quoted(text).strip()
    if re.match(r'^(?:请)?提醒我', clean):
        return None  # A reminder title may mention an external action by the user.
    channel_context = clean
    # "等我把消息写好，你能替我发送吗" asks about future execution,
    # rather than delegating the writing mentioned in its conditional prefix.
    if re.match(r'^(?:等|当)', clean):
        request = re.search(r'你(?:能不能|可不可以|可以|能|会|愿意)[^，,。；;]{0,50}', clean)
        if request:
            clean = request.group()
    if (not clean or _WRITING.search(clean) or _NEGATED.search(channel_context)
            or _HOW_TO.search(clean) or not _ACTOR.match(clean) or not _SEND.search(clean)):
        return None
    channel = next((name for name, pattern in _CHANNELS if pattern.search(channel_context)), None)
    if channel is None:
        # State the global capability boundary without inventing what "it" was.
        if (clean.startswith('你') and _STATUS.search(clean) and not _LOCAL_STATUS.search(clean)
                and re.search(r'发出去|发送|发出', clean)):
            return UnavailableRequest('external', 'status')
        return None
    kind = 'status' if clean.startswith('你') and _STATUS.search(clean) else 'request'
    return UnavailableRequest(channel, kind)

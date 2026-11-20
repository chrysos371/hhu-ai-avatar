"""Bounded external-action claim guard for the opt-in release contract.

This is explicit language matching, not a universal semantic verifier. It maps
complete clauses independently so already approved streaming prefixes stay
stable. The caller supplies a source-verified writing frame and root, never a
model's assertion that its own output is creative.
"""
from dataclasses import dataclass
import re

from .facts import _mask_quoted

_STOP = r'，,。！？!?；;\n'
_SEND = r'(?:发(?:送|出|给|到|进|了|过|短信|邮件|微信|消息|QQ)|代发|转发|拨打|拨通|联系|通知)'
_SELF = re.compile(r'(?:我|我们)(?P<lead>[^'+_STOP+r']{0,36}?)'+_SEND+r'[^'+_STOP+r']{0,40}')
_OFFER = re.compile(r'(?:需要|要不要|是否需要)(?:我|我们)[^'+_STOP+r']{0,24}'+_SEND+r'[^'+_STOP+r']{0,40}')
_IMPLICIT = re.compile(r'^(?:已经|已|刚才|刚刚|马上|这就|可以|会)(?:帮你|替你|为你)?'
    r'[^'+_STOP+r']{0,12}?'+_SEND+r'[^'+_STOP+r']{0,40}')
_PASSIVE = re.compile(r'(?:短信|邮件|微信|消息|电话)[^'+_STOP+r']{0,10}'
    r'(?:已(?:经)?(?:发出|发送|拨出|拨通)|发送成功|拨打成功|成功发送)')
_SYSTEM = re.compile(r'(?:本系统|本程序|本服务|这套系统|这个系统)[^'+_STOP+r']{0,24}'
    r'(?:能|可以|会|支持|提供)[^'+_STOP+r']{0,24}'+_SEND)
_TEXT_WORK = re.compile(r'(?:修改|改写|润色|编辑|生成|起草|拟写)[^'+_STOP+r']{0,18}'
    r'(?:内容|草稿|文案|措辞|模板)')
_THEN_SEND = re.compile(r'(?:并|然后|再|接着|随后)[^'+_STOP+r']{0,8}'+_SEND)
_CHANNEL = re.compile(r'短信|邮件|电邮|微信|QQ|私信|电话|拨号|邮箱|手机号|收件人|群|'
    r'发给(?:他|她|同学|朋友|室友|老师)|(?:联系|通知)(?:了|过|到)?(?:你的?|您的?)?(?:他|她|同学|朋友|室友|老师)')
_NEGATIVE = re.compile(r'不能|无法|没有|不会|并未|不曾|不支持|尚未|未能|不能保证|无法确认')
_REPORTED = re.compile(r'你说|你提到|根据你|据你|他说|她说|对方说|用户说|角色说')
_PLANNING = re.compile(r'如果|假设|假如|例如|比如|如何|怎么|方法|示例|代码|教程|解释|讨论|分析|模拟')
_IN_CHAT = re.compile(r'在(?:这个)?(?:聊天|对话|这里)|(?:发送|发给)[^'+_STOP+r']{0,8}(?:代码|示例|建议|模板)')
_SOURCE_OFFER = re.compile(r'需不需要|要不要|是否需要|需要我|表示[^'+_STOP+r']{0,12}(?:愿意|可以)[^'+_STOP+r']{0,12}(?:帮忙|代发|发送|转发)')
_LOCAL_PROMISE = re.compile(r'(?:我|我们)(?:一定|保证|会|将|到时|稍后)[^'+_STOP+r']{0,24}提醒你')


@dataclass(frozen=True)
class GuardedOutput:
    reply: str
    rules: tuple[str, ...] = ()


def _external_clause(clean, *, root_text=''):
    if _IN_CHAT.search(clean) or _REPORTED.search(clean) or _PLANNING.search(clean):
        return None
    # Negation is local to this clause; a later "但我已经发出" is reviewed anew.
    if _NEGATIVE.search(clean):
        return None
    if _TEXT_WORK.search(clean) and not _THEN_SEND.search(clean):
        return None
    offer = _OFFER.search(clean)
    matches = list(_SELF.finditer(clean))
    implicit = _IMPLICIT.search(clean)
    passive = _PASSIVE.search(clean)
    system = _SYSTEM.search(clean)
    if not (offer or matches or implicit or passive or system):
        return None
    if not (_CHANNEL.search(clean) or offer and _CHANNEL.search(root_text)):
        return None
    # "我知道你发送..." is attribution to the user, not the assistant's action.
    own = [m for m in matches if not re.search(r'(?<![帮替为给])你|他说|她说|对方', m.group('lead'))]
    if offer:
        return 'unsupported_external_offer'
    if own or implicit or passive or system:
        return 'unsupported_external_claim'
    return None


def review_output(reply, *, frame='ordinary', root_text='', fictional=False):
    if not isinstance(reply, str) or frame not in {'ordinary', 'writing', 'unverified'}:
        raise ValueError('Invalid source-bound output review input')
    if fictional:
        return GuardedOutput(reply)
    masked = _mask_quoted(reply)
    ends = [m.end() for m in re.finditer('['+_STOP+']', masked)]
    if not ends or ends[-1] != len(reply):
        ends.append(len(reply))
    start = 0
    pieces, rules = [], []
    for end in ends:
        raw, clean = reply[start:end], masked[start:end]
        start = end
        why = _external_clause(clean.strip(), root_text=root_text)
        local_promise = bool(_LOCAL_PROMISE.search(clean) and not _NEGATIVE.search(clean)
            and not _REPORTED.search(clean) and not _PLANNING.search(clean))
        if frame == 'writing':
            # First-person draft actions belong to the requested author. Remove
            # only unsolicited assistant service invitations outside quoted text.
            if why != 'unsupported_external_offer' or _SOURCE_OFFER.search(root_text) or raw.strip(' '+_STOP) in root_text:
                pieces.append(raw)
                continue
            if any(p.strip() for p in pieces):
                rules.append(why)
                continue
        if why or local_promise:
            if frame == 'unverified':
                text = '当前写作主体无法核验；我没有外部代发或电话接口，请明确是在代拟正文还是询问实际操作'
            elif local_promise and not why:
                text = '提醒依赖程序运行并轮询，这段答复不会新建提醒；请用明确日期、时间和事项提出提醒请求'
            else:
                text = '我没有外部短信、邮件代发或电话接口，不能替你执行这些操作'
            separator = raw[-1:] if raw[-1:] in _STOP else '。'
            pieces.append(text+separator)
            rules.append(why or 'unsupported_local_reminder_promise')
        else:
            pieces.append(raw)
    return GuardedOutput(''.join(pieces), tuple(rules))

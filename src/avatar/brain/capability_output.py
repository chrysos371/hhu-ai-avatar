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
_RESEND = r'(?:重新|再)发(?:一(?:次|遍))?'
_SEND = r'(?:发(?:送|出|给|到|进|了|过|短信|邮件|微信|消息|QQ)|'+_RESEND+r'|代发|转发|递交|转交|提交|拨打|拨通|联系|通知)'
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
_RECEIPT = re.compile(r'(?:我|我们|本系统)(?:已经|已|刚刚|刚才)?收到[^'+_STOP+r']{0,24}(?:短信|邮件|微信|私信)')
_CHANNEL = re.compile(r'短信|邮件|电邮|微信|QQ|私信|电话|拨号|邮箱|手机号|收件人|群|'
    r'发给(?:他|她|同学|朋友|室友|老师)|(?:联系|通知)(?:了|过|到)?(?:你的?|您的?)?(?:他|她|同学|朋友|室友|老师)')
_NEGATIVE = re.compile(r'不能|无法|没有|不会|并未|不曾|不支持|尚未|未能|不能保证|无法确认')
_REPORTED = re.compile(r'你说|你提到|根据你|据你|他说|她说|对方说|用户说|角色说')
_PLANNING = re.compile(r'如果|假设|假如|例如|比如|如何|怎么|方法|示例|代码|教程|解释|讨论|分析|模拟')
_IN_CHAT = re.compile(r'在(?:这个)?(?:聊天|对话|这里)|(?:发送|发给)[^'+_STOP+r']{0,8}(?:代码|示例|建议|模板)')
_SOURCE_OFFER = re.compile(r'需不需要|要不要|是否需要|需要我|表示[^'+_STOP+r']{0,12}(?:愿意|可以)[^'+_STOP+r']{0,12}(?:帮忙|代发|发送|转发)')
_LOCAL_PROMISE = re.compile(r'(?:我|我们)(?:一定|保证|会|将|到时|稍后)[^'+_STOP+r']{0,24}提醒你')
_PROXY_COMMITMENT = re.compile(r'我(?:已经|已|会|可以)?(?:帮你|替你|代你)(?:答应|承诺)(?:下来了|下来|了)?')
_PHYSICAL_ACTIVITY = (r'(?:爬山|慢跑|跑步|散步|游泳|骑(?:车|自行车)|'
    r'打(?:网球|羽毛球|篮球|乒乓球)|吃(?:饭|火锅)|喝(?:咖啡|奶茶|饮料|可乐))')
_BODY_JOINT = re.compile(r'我们(?P<lead>[^'+_STOP+r']{0,24}?)一起(?:去|来)?'+_PHYSICAL_ACTIVITY)
_BODY_SELF = re.compile(r'我(?:明天|今晚|周末|下次|现在|这就|马上|会|将|要|准备|打算|以前|昨天|曾经|刚刚|上次)?'
    r'(?:也|还|亲自|去|已经|又|能|可以|愿意){0,4}(?:'
    r'(?:陪你|和你|跟你|同你)(?:一起|去|来|马上|亲自){0,4}'+_PHYSICAL_ACTIVITY+r'|'
    r'(?:去|到)你(?:的)?(?:家|宿舍)|(?:去|到)现场|'
    r'爬过山|跑过步|游过泳|(?:吃|喝)(?:过|了)[^'+_STOP+r']{0,10}(?:饭|火锅|咖啡|奶茶|可乐|茶|饮料)|'
    r'(?:去|来)?'+_PHYSICAL_ACTIVITY+r')')
_COUNTERFACTUAL_BODY = re.compile(r'假设|假如|比如|例如|如果(?:我|我们)(?:有|拥有)(?:真实)?身体')
_BODY_REPORTED = re.compile(r'(?:室友|朋友|同学|老师|导师|家人|班长)(?:说|提到|写道)')


def _body_clause(clean, *, sentence_context):
    """Explicit self/joint physical predicates only; no general pronoun inference."""
    if _COUNTERFACTUAL_BODY.search(sentence_context):
        return None
    for pattern in (_BODY_JOINT, _BODY_SELF):
        for match in pattern.finditer(clean):
            contrast_end = max((m.end() for m in re.finditer(r'但是|不过|然而|但', clean[:match.start()])), default=0)
            before = clean[contrast_end:match.start()]
            lead = match.groupdict().get('lead', '') or ''
            if (_REPORTED.search(before) or _BODY_REPORTED.search(before) or _PLANNING.search(before) or _PLANNING.search(lead)
                    or re.search(r'不是|并非', before) or _NEGATIVE.search(before) or _NEGATIVE.search(lead)):
                continue
            return 'unsupported_offline_offer' if pattern is _BODY_JOINT or re.search(r'陪你|和你|跟你|同你|去|到', match.group()) else 'unsupported_physical_experience'
    return None


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
    if _RECEIPT.search(clean):
        return 'unsupported_external_receipt'
    if _PROXY_COMMITMENT.search(clean):
        return 'unsupported_proxy_commitment'
    offer = _OFFER.search(clean)
    matches = list(_SELF.finditer(clean))
    implicit = _IMPLICIT.search(clean)
    passive = _PASSIVE.search(clean)
    system = _SYSTEM.search(clean)
    if not (offer or matches or implicit or passive or system):
        return None
    # "我知道你发送..." is attribution to the user, not the assistant's action.
    own = [m for m in matches if not re.search(r'(?<![帮替为给])你|他说|她说|对方', m.group('lead'))]
    contextual_resend = bool(own and re.search(_RESEND, clean)
        and re.search(r'短信|邮件|通知|消息', root_text))
    if (own or offer) and re.search(r'递交|转交|提交', clean):
        return 'unsupported_submission'
    if not (_CHANNEL.search(clean) or offer and _CHANNEL.search(root_text) or contextual_resend):
        return None
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
    start = sentence_start = 0
    pieces, rules = [], []
    for end in ends:
        raw, clean = reply[start:end], masked[start:end]
        start = end
        why = _external_clause(clean.strip(), root_text=root_text)
        body_why = _body_clause(clean.strip(), sentence_context=masked[sentence_start:end]) if frame != 'writing' else None
        if raw[-1:] in '。！？!?；;\n':
            sentence_start = end
        why = why or body_why
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
            if body_why and frame == 'unverified':
                text = '当前写作主体无法核验，请重新发送完整正文或明确虚构语境；这段对话不会承诺现实到场'
            elif body_why:
                text = '我没有真实身体，不能在线下陪同或声称亲身经历；可以在这里帮你做准备或聊聊感受'
            elif why == 'unsupported_proxy_commitment':
                text = '我没有替你向他人答应，也不能替你作出现实承诺；请由你本人决定并告知对方'
            elif why == 'unsupported_submission':
                text = '我没有递交或转交接口，不能替你实际提交材料；可以在这里帮你整理文字'
            elif frame == 'unverified':
                text = '当前写作主体无法核验；我没有外部代发或电话接口，请明确是在代拟正文还是询问实际操作'
            elif local_promise and not why:
                text = '提醒依赖程序运行并轮询，这段答复不会新建提醒；请用明确日期、时间和事项提出提醒请求'
            elif why == 'unsupported_external_receipt':
                text = '这里能看到的是聊天中提供的文字；当前没有外部短信、邮件收件接口，也未核验外部收发状态'
            else:
                text = '我没有外部短信、邮件代发或电话接口，不能替你执行这些操作'
            separator = raw[-1:] if raw[-1:] in _STOP else '。'
            pieces.append(text+separator)
            rules.append(why or 'unsupported_local_reminder_promise')
        else:
            pieces.append(raw)
    return GuardedOutput(''.join(pieces), tuple(rules))

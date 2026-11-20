"""Finite source-built writing fallback, explicitly separate from model output.

Every material clause must be recognized. Unknown instructions, quoted material,
other-person perspective and unsupported counts refuse fallback rather than
silently discarding user requirements. Nothing executes external actions.
"""
from dataclasses import dataclass
import re

from .reminder_query_targets import visible_source

_ROOT = re.compile(r'(?:请|麻烦)?(?:帮我|替我|给我|代我)?'
    r'(?:(?:给|发给|写给)(?P<recipient>老师|导师|辅导员|经理|负责人))?'
    r'(?:写|拟|起草)(?:一?[条封段份])?请假(?:短信|邮件|条|消息|申请(?:书)?)')
_CONTROL = re.compile(r'(?:只(?:给|要|输出|回复|交付)正文|保留原意|'
    r'(?:压缩到|控制在|改成|改为|写成)[一二两三四五六七八九十0-9]+句话?|'
    r'(?:请)?(?:再)?(?:短一点|简短一点|自然一点|口语一点|礼貌一点|正式一点)|'
    r'(?:请)?把它改得更(?:客气|礼貌|自然)|(?:不要|不用|无需|去掉|删除)署名)')
_SIGNATURE = re.compile(r'署名(?:请)?(?:用|改成|改为|写成|为)\s*'
    r'(?:【[^【】\n]{1,40}】|“[^“”\n]{1,40}”|「[^「」\n]{1,40}」|[^，,。；;\n？！!?\s]{1,40})')
_EVENT = re.compile(r'我(?:今天|明天|后天)?(?:要|需要)(?:参加[^，,。；;\n？！!?]{1,40}|'
    r'去看牙医|去医院(?:复查|检查|就诊))')


@dataclass(frozen=True)
class SourceArtifact:
    reply: str
    template: str
    source_message_ids: tuple[int, ...]


def build_fallback(requirements, *, current_text, fictional=False):
    if not requirements.source_verified or not requirements.sources:
        return None
    if requirements.verbatim_literal is not None:
        reply = requirements.verbatim_literal
        if requirements.signature:
            reply += '\n' + requirements.signature
        return SourceArtifact(reply, 'explicit_verbatim_literal_v1', requirements.source_message_ids)
    count = requirements.sentence_count
    if count not in (None, 1, 2, 3):
        return None
    # Explicit fictional counterparty reply only: no real receipt or approval.
    root = requirements.sources[0][1]
    if (fictional and requirements.author_role in ('老师', '导师')
            and (fiction_request := re.fullmatch(r'我(?:已|已经|刚|刚刚|刚才)(?:把|将)?(?P<channel>邮件|消息|短信)'
                r'(?:发送|发|寄)(?:了)?给(?:老师|导师)[，,；;]\s*(?:接着|随后|然后)'
                r'(?:请|帮我)?(?:写|拟|起草)(?:一下)?(?:对方|老师|导师)(?:的)?(?:回复|回信)[。！!]?\s*', root))):
        if len(requirements.sources) != 1 or count not in (None, 1):
            return None
        return SourceArtifact('“你好，' + fiction_request['channel'] + '已收到，我会查看后再回复。”',
            'explicit_fiction_counterparty_reply_v1', requirements.source_message_ids)
    if fictional or requirements.author_role is not None:
        return None
    recipient, event, seen_root = '', None, False
    for index, (_, text) in enumerate(requirements.sources):
        # Split only at punctuation outside quotes/placeholders. A quoted
        # signature is an admitted control; arbitrary quoted material refuses.
        masked = re.sub(r'【[^【】\n]*】', lambda m: ' ' * len(m.group()), visible_source(text))
        for match in re.finditer(r'[^，,。；;\n]+', masked):
            clause = text[match.start():match.end()].strip()
            if not clause:
                continue
            found = _ROOT.fullmatch(clause)
            if found and index == 0 and not seen_root:
                recipient, seen_root = found['recipient'] or '', True
            elif _CONTROL.fullmatch(clause) or _SIGNATURE.fullmatch(clause):
                continue
            elif _EVENT.fullmatch(clause) and event is None:
                event = clause  # Actual original user clause, no duration inference.
            else:
                return None
    if not seen_root:
        return None
    greeting = recipient + '您好' if recipient else '您好'
    application = event + '，申请请假' if event else '因【请假原因】，申请于【请假时间】请假'
    polite = '恳请您批准' if '客气' in current_text or '礼貌' in current_text else '敬请批准'
    count = count or (1 if '短一点' in current_text else 2)
    if count == 1:
        reply = greeting + '，' + application + '，' + polite + '。'
    elif count == 2:
        reply = greeting + '。' + application + '，' + polite + '。'
    else:
        reply = greeting + '。' + application + '。' + polite + '。'
    if requirements.signature:
        reply += '\n' + requirements.signature
    return SourceArtifact(reply, 'simple_source_leave_request_v1', requirements.source_message_ids)

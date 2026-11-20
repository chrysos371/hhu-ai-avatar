"""Finite literal/format and known leave-draft source checks, not semantics.

No model draft is used as a control or example. Native raw outputs are retained
by the provider trace; public metadata records hashes and explicit limitations.
"""
from hashlib import sha256
import re
from .reminder_query_targets import visible_source

_PREFACE = re.compile(r'^(?:(?:当然可以|好的|没问题)[，,。！!\s]*)?'
    r'(?:以下是|下面是|这是(?:为你|帮你)|我(?:帮|为)你(?:写|拟))')
_LEAVE_DETAILS = re.compile(r'身体不适|发烧|感冒|生病|肚子疼|家中有事|突发急事|今天|今日|明天|后天|'
    r'个人原因|个人事务|个人安排(?:变动)?|到岗|相关工作|落下的工作|'
    r'[一二两三四五六七八九十0-9]+(?:天|小时)|'
    r'下周[一二三四五六日天]?|[0-9]{1,2}月[0-9]{1,2}[日号]')
_NEGATED = re.compile(r'(?:不是|并非|没有|不要(?:写|用|提|说)?|别(?:写|用|提|说)?|不能写)\s*$')


def fingerprint(text):
    return sha256(text.encode('utf-8')).hexdigest()


def inspect(reply, requirements, *, fictional=False):
    if not requirements.source_verified:
        raise ValueError('Writing delivery requires verified user source pointers')
    if not isinstance(reply, str) or not reply.strip():
        return ('empty_body',)
    issues = []
    lines = reply.strip().splitlines()
    body = reply.strip()
    signature = requirements.signature
    if signature:
        if lines[-1].strip() != signature or reply.count(signature) != 1:
            issues.append('signature_not_last_line')
        else:
            body = '\n'.join(lines[:-1]).strip()
    if requirements.signature_omitted and any(value in reply for value in requirements.forbidden_signatures):
        issues.append('released_signature')
    if not body:
        issues.append('empty_body')
    if requirements.sentence_count is not None:
        # Chinese terminal punctuation clusters; a final unpunctuated fragment
        # counts once. A verified separate signature line is not a sentence.
        count = len(re.findall(r'[。！？!?]+', body))
        tail = re.split(r'[。！？!?]+', body)[-1].strip(' \n\t”」』\"\'）)')
        count += bool(tail)
        if count != requirements.sentence_count:
            issues.append('sentence_count')
    if requirements.body_only and _PREFACE.search(body):
        issues.append('body_preface')
    root = requirements.sources[0][1]
    verbatim = bool(re.search(r'原样(?:写出|输出|包含|保留)', visible_source(root)) and any(
        body == literal for match in re.finditer(r'“([^“”\n]+)”|「([^「」\n]+)」|"([^"\n]+)"', root)
        for literal in match.groups() if literal is not None))
    if not verbatim and re.search(r'需要我帮你(?:构思|写(?:一下)?(?:老师|对方)?(?:的)?回复)[^。！？!?\n]*[？?]', visible_source(body)):
        issues.append('artifact_not_delivered')
    author = requirements.author_role
    if (not verbatim and author in ('老师', '导师')
            and re.match(re.escape(author) + r'[，,：:\s]*(?:您|你)?好', body.lstrip('“「\"'))
            and re.search(r'我(?:已|已经)(?:将|把)?(?:邮件|材料).{0,8}(?:发|发送|寄)', body)):
        issues.append('wrong_artifact_author')
    # Only the measured real leave-draft family, never all creative text or
    # every mention of tomorrow. Exact source presence is necessary, not proof
    # of general factual support; nonhuman source/span review remains required.
    if not fictional and '请假' in requirements.sources[0][1]:
        visible = re.sub(r'【[^【】\n]*】', '', body)
        for match in _LEAVE_DETAILS.finditer(visible):
            token = match.group()
            negative = bool(_NEGATED.search(visible[max(0, match.start()-8):match.start()]))
            observations = [bool(_NEGATED.search(text[max(0, m.start()-8):m.start()]))
                for _, text in requirements.sources for m in re.finditer(re.escape(token), text)]
            supported = bool(observations) and observations[-1] == negative
            if not supported:
                issues.append('unsupported_source_detail')
                break
    return tuple(dict.fromkeys(issues))


def repair_instruction(requirements, issues):
    import json
    return ('请依据已核验的原始写作请求和当前有效修改，重新交付正文。'
        '当前失败稿不作为示范或事实来源，不补造日期或理由；未知项可用【占位】。'
        'signature按原样单独放文末且不作收件人，sentence_count只计正文。'
        '只修复下列有限问题并遵守当前约束；不得执行现实动作：'
        + json.dumps({'requirements': requirements.data(), 'failed_checks': list(issues)}, ensure_ascii=False))

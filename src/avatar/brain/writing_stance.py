"""Explicit not-agreed draft requirement; no inference of real-world consent."""
import re

from .reminder_query_targets import visible_source

_DIRECTIVE = re.compile(r'(?:明确|说明|表明|改成|改为)(?:我)?'
    r'(?P<state>尚未|还未|还没(?:有)?|没有|已经|已)(?:同意|答应)')
_NOT_AGREED = re.compile(r'(?:^|[，,。；;！!?？\n])\s*(?:我)?'
    r'(?:尚未|还未|还没(?:有)?|没有)(?:同意|答应)')
_AGREED = re.compile(r'我(?:已经|已|愿意|决定)?(?:同意|答应|接受)')
_ROOT = re.compile(r'(?:请|麻烦)?(?:帮我|替我)?(?:写|拟)(?:一?[句条段])?回复[，,]'
    r'(?:明确|说明|表明)(?:我)?(?:尚未|还未|还没(?:有)?|没有)(?:同意|答应)[，,]'
    r'(?:不要|别)(?:替我|帮我)?承诺[。！!]?')


def requirement(sources):
    state = None
    for source_id, text in sources:
        clean = visible_source(text)
        for match in _DIRECTIVE.finditer(clean):
            prefix = re.split(r'[，,。；;！？!?\n]', clean[:match.start()])[-1]
            if re.search(r'如果|假设|假如|不要|不必|别|并非|不是', prefix):
                continue
            state = (dict(version=1, state='not_agreed', source_message_ids=[source_id],
                          real_consent_verified=False, semantic_verifier=False)
                     if match['state'] not in ('已经', '已') else None)
    return state


def inspect(reply, sources):
    if requirement(sources) is None:
        return ()
    clean = reply.strip()
    for left, right in [('“', '”'), ('「', '」'), ('"', '"')]:
        if clean.startswith(left) and clean.endswith(right):
            clean = clean[1:-1]
            break
    clean = visible_source(clean)
    issues = []
    if not _NOT_AGREED.search(clean):
        issues.append('explicit_not_agreed_missing')
    for match in _AGREED.finditer(clean):
        prefix = clean[max(0, match.start()-16):match.start()]
        if not re.search(r'不是|并非|不要(?:把|当作)|别以为', prefix):
            issues.append('contradictory_agreement')
            break
    return tuple(issues)


def fallback(requirements):
    """Only the complete registered instruction; additional unknown material refuses."""
    if (requirement(requirements.sources) is None or requirements.sentence_count not in (None, 1)
            or requirements.signature or requirements.signature_omitted
            or requirements.author_role is not None):
        return None
    if not _ROOT.fullmatch(requirements.sources[0][1].strip()):
        return None
    for _, edit in requirements.sources[1:]:
        if not re.fullmatch(r'(?:请)?(?:再)?(?:自然一点|口语一点|礼貌一点|正式一点|短一点|简短一点)[。！!]?', edit.strip()):
            return None
    return '我尚未同意，请先不要安排我负责这件事。'

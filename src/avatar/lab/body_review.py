"""Experimental explicit Chinese self-body patterns, not general semantics.

No implicit subject resolution or preference ownership. The caller must derive
creative context from current valid sources. Nothing imports this by default.
"""
from dataclasses import dataclass
import re

from ..brain.facts import _mask_quoted


_CLAUSE = r'，,。！？!?；;\n'
_PHYSICAL = (r'(?:爬山|慢跑|跑步|散步|骑(?:车|自行车)|游泳|'
             r'打(?:羽毛球|篮球|乒乓球)|吃(?:饭|火锅)|喝(?:咖啡|奶茶|饮料|可乐))')
_WORDS = r'(?:明天|今晚|下次|现在|周末|今天|以后|最近|这就|就|将|会|能|可以|要|也|一定|愿意|打算|准备|已经|曾经|以前|上次|昨天|刚刚|刚|还|再|亲自)'
_BRIDGE = r'(?:一起|去|来|到|再|也|好好|慢慢|马上|亲自|下次)'
_RULES = [
    ('joint_action', 'offline_offer', re.compile(r'我们(?P<lead>[^'+_CLAUSE+r']{0,20})一起(?:去|来)?'+_PHYSICAL)),
    ('self_accompany', 'offline_offer', re.compile(r'我'+_WORDS+r'{0,5}(?:陪你|和你|跟你|同你)'+_BRIDGE+r'{0,4}'+_PHYSICAL)),
    ('self_visit', 'offline_offer', re.compile(r'我'+_WORDS+r'{0,5}(?:去|到)(?:你(?:的)?(?:家|宿舍)|现场)')),
    ('self_future_action', 'offline_offer', re.compile(r'我(?:明天|今晚|周末|下次|现在|这就|马上|会|将|要|准备|打算)'+_WORDS+r'{0,4}(?:去|来)?'+_PHYSICAL)),
    ('self_past_action', 'physical_experience', re.compile(r'我(?:以前|上次|昨天|前天|刚刚|刚|曾经)(?:也|还|亲自|去|已经|又|早就){0,3}'+_PHYSICAL)),
    ('self_experienced', 'physical_experience', re.compile(r'我'+_WORDS+r'{0,4}(?:爬过山|跑过步|游过泳|去过你(?:的)?(?:家|宿舍)|到过现场)')),
    ('self_ingestion', 'physical_experience', re.compile(r'我'+_WORDS+r'{0,4}(?:吃|喝)(?:过|了)[^'+_CLAUSE+r']{0,10}(?:菜|饭|火锅|咖啡|可乐|茶|饮料|酒)')),
]
_JOINT_CHOICES = re.compile(r'我们(?P<lead>[^'+_CLAUSE+r']{0,24})一起活动[。！？!?]?\s*(?:比如|例如)(?P<choices>[^'+_CLAUSE+r']{1,60})')
_HYPOTHETICAL = re.compile(r'如果|假如|假设|要是|倘若|也许|可能|比如|例如')
_REPORTED = re.compile(r'他说|她说|朋友说|同学说|室友说|你说|你问|你写|你提到|用户说|角色说|台词')
_PLANNING = re.compile(r'规划|计划|整理|设计|核对|介绍|回顾|写|模拟|想象|分析|讨论|建议|推荐|听说|知道|认为|觉得|线上')
_NEGATION = re.compile(r'不能|无法|不会|没有|并不|不曾|不想|不打算|不准备|不愿')
_BREAK = re.compile(r'['+_CLAUSE+r']|但是|不过|然而|但')
_SENTENCE = re.compile(r'[。！？!?；;\n]')


@dataclass(frozen=True)
class BodyMatch:
    rule: str
    kind: str
    start_codepoint: int
    end_codepoint: int


@dataclass(frozen=True)
class BodyReview:
    reply: str
    matches: tuple[BodyMatch, ...] = ()
    exempt: bool = False

    @property
    def changed(self):
        return bool(self.matches)

    def metadata(self):
        return {'version': 1, 'scope': 'explicit_chinese_self_body_patterns',
                'action': 'bounded_body_rewrite' if self.changed else None,
                'creative_exempt': self.exempt, 'general_semantics_verified': False,
                'matches': [vars(match) for match in self.matches]}


def _start_after_last(pattern, text, stop):
    return max((match.end() for match in pattern.finditer(text, 0, stop)), default=0)


def _accepted(masked, match):
    before = masked[_start_after_last(_BREAK, masked, match.start()):match.start()]
    sentence = masked[_start_after_last(_SENTENCE, masked, match.start()):match.start()]
    if _HYPOTHETICAL.search(sentence) or _REPORTED.search(before):
        return False
    lead = match.groupdict().get('lead') or ''
    return not (_NEGATION.search(lead) or _PLANNING.search(lead))


def review_explicit_body(reply, *, composition=False, fiction=False, role=False):
    if not isinstance(reply, str):
        raise TypeError('body review expects text')
    if composition or fiction or role:
        return BodyReview(reply, exempt=True)
    masked = _mask_quoted(reply)
    found = []
    for rule, kind, pattern in _RULES:
        for match in pattern.finditer(masked):
            if _accepted(masked, match):
                found.append(BodyMatch(rule, kind, match.start(), match.end()))
    for match in _JOINT_CHOICES.finditer(masked):
        choices = match.group('choices')
        if (_accepted(masked, match) and re.search(_PHYSICAL, choices)
                and not (_PLANNING.search(choices) or _NEGATION.search(choices))):
            found.append(BodyMatch('joint_activity_choices', 'offline_offer', match.start(), match.end()))
    matches = tuple(sorted(set(found), key=lambda m: (m.start_codepoint, m.end_codepoint, m.rule)))
    if not matches:
        return BodyReview(reply)
    if any(match.kind == 'offline_offer' for match in matches):
        text = '我没有真实身体，不能在线下陪同；可以在这里帮你做准备、规划活动或聊聊你的感受。'
    else:
        text = '我没有真实身体和亲身感官经历，可以根据你的描述一起讨论，不把想象说成实际体验。'
    return BodyReview(text, matches)

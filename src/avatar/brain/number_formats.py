"""Finite presentation of an existing numeric answer, never a semantic oracle."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
import re

from .reminder_query_targets import visible_source

_CLAUSES = re.compile(r'[^，,。；;！？!?\n]+')
_REQUEST = re.compile(r'(?:请)?(?:只|仅)(?:回答|回复|输出)(?:一个)?(?:数字|数值)(?:即可|就好|就行)?')
_UNKNOWN = re.compile(r'(?:没有|缺少|无)资料(?:则|就)?(?:回答|回复|输出)无法确认')
_UNSIGNED = r'[0-9]{1,32}(?:\.[0-9]{1,12})?'
_VALUE = r'[+-]?'+_UNSIGNED
_SUM = re.compile(_VALUE+r'(?:[+-]'+_UNSIGNED+r')+')


def _clauses(text):
    return [m.group().strip() for m in _CLAUSES.finditer(visible_source(text))]


def requested(text):
    return isinstance(text, str) and 0 < len(text) <= 2000 and any(
        _REQUEST.fullmatch(clause) for clause in _clauses(text))


@dataclass(frozen=True)
class NumberReply:
    reply: str
    rules: tuple[str, ...] = ()
    arithmetic_consistent: bool | None = None
    reason: str = 'unsupported_output_form'


def review(reply, text):
    if not isinstance(reply, str) or not requested(text):
        raise ValueError('Numeric presentation requires a current explicit source instruction')
    clean = re.sub(r'[。.!！]\s*$', '', reply.strip())
    if len(clean) > 256:
        return NumberReply(reply, reason='output_limit_exceeded')
    if re.fullmatch(_VALUE, clean):
        return NumberReply(clean, ('numeric_presentation',) if clean != reply else (), reason='numeric_value')
    if clean == '无法确认' and any(_UNKNOWN.fullmatch(clause) for clause in _clauses(text)):
        return NumberReply(clean, ('explicit_unknown_presentation',) if clean != reply else (), reason='explicit_unknown')
    if clean.count('=') != 1:
        return NumberReply(reply)
    left, right = (re.sub(r'\s+', '', value) for value in clean.split('='))
    if not _SUM.fullmatch(left) or not re.fullmatch(_VALUE, right):
        return NumberReply(reply)
    terms = re.findall(_VALUE, left)
    if len(terms) > 16:
        return NumberReply(reply, reason='term_limit_exceeded')
    try:
        with localcontext() as context:
            context.prec = 128
            consistent = sum((Decimal(term) for term in terms), Decimal(0)) == Decimal(right)
    except InvalidOperation:
        return NumberReply(reply, reason='invalid_decimal')
    if not consistent:
        # Preserve the visible contradiction and mark failure. Never hide a
        # wrong equation by silently selecting its final numeric substring.
        return NumberReply(reply, arithmetic_consistent=False, reason='arithmetic_mismatch')
    return NumberReply(right, ('consistent_additive_expression_presentation',), True, 'consistent_expression')

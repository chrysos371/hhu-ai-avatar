"""Bounded reported-sender answers from existing verified user-context sources.

This identifies an actor in a statement; it never verifies external execution,
delivery, or human acknowledgement, and never writes an event/receipt.
"""
from dataclasses import dataclass, replace
import re

from ..cancellation import Cancelled
from .capabilities import snapshot
from .facts import _mask_quoted

_SEND = r'(?:发(?:送|出|给|到|进|了|过|的|短信|邮件|消息)|寄出)'
_ACTION = re.compile(_SEND)
_NAMED_ROLE = r'室友|朋友|同学|老师|家人|班长'
_ROLE = _NAMED_ROLE + r'|他|她'
_ACTOR = re.compile(r'^(?:其实|实际上)?(?:是)?(?P<actor>我|'+_ROLE+r')'
    r'(?P<lead>[^，,。！？!?；;\n]{0,32}?)'+_SEND)
_NOT_ASSERTED = re.compile(r'没有|不是|不曾|没|尚未|并未|未曾|如果|假设|可能|是否|'
    r'希望|打算|准备|计划|要求|请你|让你|叫你|让别人|会|将|能不能|可不可以|不知道|不清楚|听说')

_QUESTION = re.compile(r'(?:请问)?(?:到底|究竟)?(?:是)?谁(?:把(?:这条|那条|这封|那封)?'
    r'(?:短信|邮件|消息|通知))?(?:发(?:送|出)?(?:的|了)?|寄出(?:的|了)?)'
    r'(?:(?:这条|那条|这封|那封)?(?:短信|邮件|消息|通知))?(?:的)?(?:呢|啊)?[？?。]?')


def sender_question(text):
    clean = _mask_quoted(text).strip()
    # Only a complete actor-only question may bypass semantic cognition.
    # Mixed distress, requests and explanations must retain normal analysis.
    return bool(_QUESTION.fullmatch(clean))


def mixed_sender_question(text):
    """Finite affect plus actor question; never an action or arbitrary text span."""
    clean = _mask_quoted(text).strip()
    affect = r'我(?:有些|有点|很|实在|现在很|现在有点|现在)?(?:难过|害怕|忐忑不安|担心|紧张|焦虑|伤心|不安)'
    return bool(re.fullmatch(affect+r'[，,。]'+_QUESTION.pattern, clean)
        or re.fullmatch(_QUESTION.pattern+r'\s*'+affect+r'[。！!]?$', clean))


@dataclass(frozen=True)
class ReportedSender:
    reported_actor: str | None
    source_message_ids: tuple[int, ...]
    mixed_affect: bool = False

    @property
    def reply(self):
        reply = self.source_reply
        if self.mixed_affect:
            reply += '如果你愿意，可以说说是什么让你难过或不安，我会在这里倾听。'
        return reply

    @property
    def source_reply(self):
        if self.reported_actor == 'user':
            return '按你之前的自述，是你自己发的。我没有代发，也没有核验外部送达或对方回复。'
        if self.reported_actor is not None:
            return f'按你之前提供的说法，是{self.reported_actor}发送的。这只是复述来源，不能据此确认实际送达或对方同意。'
        return '当前能核对的来源不足以确认发送者。我没有外部代发接口，不能凭聊天猜测是谁实际发送的。'

    def metadata(self):
        data = {'version': 1, 'scope': 'bounded_verified_real_user_report_context',
            'reported_actor': self.reported_actor, 'source_message_ids': list(self.source_message_ids),
            'external_state_verified': False, 'human_acknowledgement_verified': False,
            'complete_history': False, 'semantic_verifier': False}
        if self.mixed_affect:
            data['mixed_affect'] = True
        return data


def answer_from_contexts(contexts, *, text):
    if not sender_question(text) and not mixed_sender_question(text):
        return None
    answer = from_contexts(contexts)
    if mixed_sender_question(text):
        # Unknown/ambiguous sources retain ordinary conversation. A known actor
        # is answered only from authenticated history, with normal cognition.
        return replace(answer, mixed_affect=True) if answer.reported_actor is not None else None
    return answer


def reported_sender(memory, *, text, session_id, source_message_id, revision, scope):
    if not sender_question(text) and not mixed_sender_question(text):
        return None
    if scope.scope != 'current_user' or not scope.allows_actions:
        raise Cancelled('Sender-source query requires an independent verified real-user turn')
    contexts, ids = list(scope.context), list(scope.context_source_ids)
    if len(contexts) != len(ids):
        contexts, ids = [], []  # Never invent provenance for an old untracked string.
    conn = memory._conn
    owned = not conn.in_transaction
    if owned:
        conn.execute('BEGIN')
    try:
        snapshot(memory, session_id=session_id, source_message_id=source_message_id,
            user_text=text, revision=revision, scope=scope, known_source_ids={source_message_id, *ids})
        checked = []
        for context, ident in zip(contexts, ids):
            row = conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (ident,)).fetchone()
            if (not row or row['role'] != 'user' or row['content'] == '[redacted]'
                    or not context or row['content'].count(context) != 1):
                raise Cancelled('Reported sender source no longer matches its verified context')
            checked.append((ident, context))
        return answer_from_contexts(checked, text=text)
    finally:
        if owned:
            conn.rollback()


def from_contexts(contexts):
    """Pure actor extraction; callers independently verify all source rows."""
    for ident, context in reversed(contexts):
        clean = _mask_quoted(context)
        if not _ACTION.search(clean):
            continue
        actors = set()
        for piece in re.finditer(r'[^，,。！？!?；;\n]+[，,。！？!?；;\n]?', clean):
            clause = piece.group().strip()
            # The outer reporter is not automatically the embedded sender.
            clause = re.sub(r'^(?:我)?听说(?=(?:'+_NAMED_ROLE+r'))', '', clause)
            clause = re.sub(r'^(?:我|'+_ROLE+r')说(?=(?:'+_NAMED_ROLE+r'))', '', clause)
            if re.match(r'^(?:'+_ROLE+r')说我', clause):
                continue  # Quoted first person is ambiguous without a speaker binding.
            if re.match(r'^我的(?:室友|朋友|同学|老师|家人)', clause):
                clause = clause[2:]
            elif re.match(r'^我(?:室友|朋友|同学|老师|家人)', clause):
                clause = clause[1:]
            match = _ACTOR.match(clause)
            if (not match or _NOT_ASSERTED.search(match.group('lead'))
                    or re.search(r'[？?]|(?:吗|么|呢)[，,。！？!?；;\n]?$', clause)):
                continue
            actor = match.group('actor')
            # A report about what someone asked/requested is not a report
            # that that person was the actual sender.
            if actor == '我' and re.search(r'请|让|叫|希望|想|要你', match.group('lead')):
                continue
            joint = re.search(r'(?:和|跟|同)('+_ROLE+r')', match.group('lead')) if actor == '我' else None
            actors.add('你和'+joint[1] if joint else 'user' if actor == '我' else actor)
        if len(actors) == 1:
            return ReportedSender(next(iter(actors)), (ident,))
        # A later ambiguous/negative/action-request source must not be
        # overwritten with an older, superficially convenient self-report.
        return ReportedSender(None, (ident,))
    return ReportedSender(None, ())

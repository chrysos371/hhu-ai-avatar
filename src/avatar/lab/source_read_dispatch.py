"""Isolated dedicated read mode with source-owned typed dispatch, no model.

Finite lexical preconditions do not certify general conversational intent.
Production factories remain unchanged; C41/C42/C43 readers are baselines.
"""
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
import time

from ..cancellation import Cancelled
from .source_tool_catalogue import CatalogueReadSession, STATE, POLICY, CLARIFY, canonical, eligible_state_id
from .policy_question_catalogue import policy_question_evidence
from .trusted_local_read import ReadResult, parameter_basis, visible_source

QUERY_REQUEST_PATTERN = '[?？]|吗|么|是否|能否|能不能|可不可以|会不会|是不是|查询|查看|核对|查一下|看一下|看看|查查|想查|想看|想知道|读一下|什么状态|还在不在|有没有'
WRITING_REQUEST_PATTERN = '写(?:一段|段|一个|个|一篇|篇|一句|句|封|一封|代码|文案|示例)|(?:生成|输出)[^\\n。；]{0,6}(?:代码|台词|文案|句子|示例|故事)'
MUTATION_REQUEST_PATTERN = '(?:请(?:帮我|替我|给我)?|帮我|替我|给我|我要|我想|能不能(?:帮我|替我|给我)?|能否(?:帮我|替我|给我)?|可以(?:帮我|替我|给我)?)(?:现在|马上|立即)?(?:把[^。；！？\\n]{0,16})?(?:创建|新增|设置|添加|删除|取消|完成|修改|更改|更新|推迟|提前|重设)|^\\s*(?:现在|马上|立即)(?:把[^。；！？\\n]{0,16})?(?:创建|新增|设置|添加|删除|取消|完成|修改|更改|更新|推迟|提前|重设)(?!的)|^\\s*(?:创建|新增|设置|添加|删除|取消|完成|修改|更改|更新|推迟|提前|重设)(?!的)[^。；！？\\n]{0,8}提醒'
EXTERNAL_ACTION_REQUEST_PATTERN = '(?:请(?:帮我|替我|给我)?|帮我|替我|给我)(?:给[^。；！？\\n]{0,12})?(?:发送|代发|发)[^。；！？\\n]{0,8}(?:邮件|短信|电话)|(?:请帮我|帮我|替我)(?:通过|用)(?:短信|邮件|电话)[^。；！？\\n]{0,12}(?:提醒|通知)'

_QUERY = re.compile(QUERY_REQUEST_PATTERN)
_WRITING = re.compile(WRITING_REQUEST_PATTERN)
_MUTATION = re.compile(MUTATION_REQUEST_PATTERN)
_EXTERNAL = re.compile(EXTERNAL_ACTION_REQUEST_PATTERN)
_TOOLS = {'read_state': STATE, 'read_policy': POLICY, 'clarify_reference': CLARIFY}
_NO_READ = '本轮未查询提醒记录。这里仅支持查询具体编号的状态或运行、送达条件，不执行写入或外发。'
_INTENT = {
    'mixed_read_targets': '你同时提到了记录状态和运行、送达条件，请明确本轮要查询哪一种；这次未读取提醒。',
    'query_goal_unspecified': '请明确要查询某个编号的提醒状态，还是了解运行、送达条件；这次未读取提醒。',
}


@dataclass(frozen=True)
class ReadTarget:
    route: str
    reason: str
    arguments_json: str
    evidence_json: str

    @property
    def arguments(self):
        return json.loads(self.arguments_json)

    @property
    def evidence(self):
        return json.loads(self.evidence_json)


def derive_read_target(text):
    """Pure finite routing basis; does not authorize an owner or read business data."""
    if not isinstance(text, str) or not 0 < len(text) <= 2000:
        raise ValueError('bounded nonempty source text required')
    visible = visible_source(text)
    policy = policy_question_evidence(text)
    ident = eligible_state_id(text)
    base_error = parameter_basis(text, {}, POLICY)
    query = _QUERY.search(visible) is not None
    writing = _WRITING.search(visible) is not None
    mutation = _MUTATION.search(visible) is not None
    external = _EXTERNAL.search(visible) is not None
    evidence = {'domain_or_exclusion_error': base_error, 'query_request': query,
        'writing_request': writing, 'mutation_request': mutation,
        'external_action_request': external, 'bound_reminder_id': ident,
        'policy_question_evidence': asdict(policy)}
    arguments = {}
    if base_error:
        route, reason = 'no_read', base_error
    elif writing or mutation or external:
        route = 'no_read'
        reason = 'writing_request' if writing else 'mutation_request' if mutation else 'external_action_request'
    elif not query:
        route, reason = 'no_read', 'not_a_query'
    elif policy.runtime_spans and policy.record_reference and policy.record_state:
        route, reason = 'clarify_intent', 'mixed_read_targets'
    elif policy.allowed:
        route, reason = 'read_policy', 'runtime_or_channel_query'
    elif ident is not None:
        route, reason = 'read_state', 'unique_record_query'
        arguments = {'reminder_id': ident}
    elif policy.record_reference or policy.record_state:
        route, reason = 'clarify_reference', 'reference_not_unique'
    else:
        route, reason = 'clarify_intent', 'query_goal_unspecified'
    return ReadTarget(route, reason, canonical(arguments), canonical(evidence))


@dataclass(frozen=True)
class SourceReadPlan:
    target: ReadTarget
    source_message_id: int
    session_id: str
    revision: int
    source_text_sha256: str
    _owner: object = field(repr=False, compare=False)
    _turn_token: object = field(repr=False, compare=False)

    @property
    def metadata(self):
        value = {'version': 1, 'route': self.target.route, 'reason': self.target.reason,
            'arguments': self.target.arguments, 'evidence': self.target.evidence,
            'source_message_id': self.source_message_id, 'session_id': self.session_id,
            'revision': self.revision, 'source_text_sha256': self.source_text_sha256,
            'model_required': False, 'business_data_read': False, 'semantic_intent_verified': False}
        value['plan_sha256'] = hashlib.sha256(canonical(value).encode()).hexdigest()
        return value

    def require_current(self, session):
        if session is not self._owner or session._last_plan is not self:
            raise Cancelled('plan is not latest-issued for this live session')
        if session.memory._conn.in_transaction:
            raise Cancelled('plan dispatch requires released caller transaction')
        session.ensure_current()
        turn = session._turn
        if (turn is not self._turn_token or turn.ident != self.source_message_id
                or turn.session_id != self.session_id or turn.revision != self.revision
                or hashlib.sha256(turn.text.encode()).hexdigest() != self.source_text_sha256):
            raise Cancelled('plan source binding changed')


@dataclass(frozen=True)
class QueryIntentClarification:
    reply: str
    source_message_id: int
    revision: int
    observed_at: float
    reason: str
    kind: str = 'query_intent_clarification'
    business_data_read: bool = False
    business_mutations: bool = False


@dataclass(frozen=True)
class NoReadOutcome:
    reply: str
    source_message_id: int
    revision: int
    observed_at: float
    reason: str
    kind: str = 'no_read'
    business_data_read: bool = False
    business_mutations: bool = False


class _ReadTargetDenied(Exception):
    pass


class SourceReadDispatchSession(CatalogueReadSession):
    def __init__(self, *args, **kwargs):
        self._pending_operation = None
        self._last_plan = None
        super().__init__(*args, **kwargs)

    def begin_turn(self, text):
        if self._pending_operation is not None:
            raise Cancelled('source cannot reenter while a read operation is active')
        ident = super().begin_turn(text)
        self._last_plan = None
        return ident

    def catalogue(self, *args, **kwargs):
        raise ValueError('source dispatch issues plans, not model tool catalogues')

    def plan(self):
        if self.memory._conn.in_transaction:
            raise Cancelled('planning requires released caller transaction')
        self.ensure_current()
        turn = self._turn
        target = derive_read_target(turn.text)
        self.ensure_current()
        if self._turn is not turn:
            raise Cancelled('source changed during planning')
        result = SourceReadPlan(target, turn.ident, turn.session_id, turn.revision,
            hashlib.sha256(turn.text.encode()).hexdigest(), self, turn)
        self._last_plan = result
        return result

    def _authorize(self, conn):
        super()._authorize(conn)
        pending = self._pending_operation
        if pending is None:
            return
        turn, tool = pending
        if self._turn is not turn:
            raise Cancelled('source changed before operation authorization')
        target = derive_read_target(turn.text)
        if _TOOLS.get(target.route) != tool:
            raise _ReadTargetDenied('operation does not match the actual current query target')

    def execute(self, tool, arguments):
        turn = self._turn
        self.ensure_current()
        if self._turn is not turn:
            raise Cancelled('source changed before read execution')
        if self._pending_operation is not None:
            raise Cancelled('nested read operation refused')
        self._pending_operation = (turn, tool)
        denied = False
        try:
            try:
                result = super().execute(tool, arguments)
            except _ReadTargetDenied:
                denied = True
        finally:
            self._pending_operation = None
        if denied:
            self.ensure_current()
            if self._turn is not turn:
                raise Cancelled('source changed while refusing operation')
            message = '当前原文请求的只读目标与该操作不符，本轮未读取提醒信息。'
            result = ReadResult(False, None, {'code': 'read_target_not_requested', 'message': message},
                message, turn.ident, turn.revision, time.time())
            self._last_result = result
        return result

    def dispatch(self, plan):
        plan.require_current(self)
        tool = _TOOLS.get(plan.target.route)
        if tool:
            result = self.execute(tool, plan.target.arguments)
        else:
            with self._snapshot() as conn:
                self._authorize(conn)
                turn = self._turn
                actual = derive_read_target(turn.text)
                if actual != plan.target:
                    raise Cancelled('typed control target changed')
                if actual.route == 'clarify_intent':
                    result = QueryIntentClarification(_INTENT[actual.reason], turn.ident,
                        turn.revision, time.time(), actual.reason)
                elif actual.route == 'no_read':
                    result = NoReadOutcome(_NO_READ, turn.ident, turn.revision, time.time(), actual.reason)
                else:
                    raise ValueError('unknown direct dispatch target')
            self.ensure_current()
            if self._turn is not turn:
                raise Cancelled('source changed before control publication')
            self._last_result = result
        plan.require_current(self)
        return result

    def publish(self, result):
        turn = self._turn
        if (turn is None or result.source_message_id != turn.ident or result.revision != turn.revision):
            raise Cancelled('result belongs to a different source')
        return super().publish(result)

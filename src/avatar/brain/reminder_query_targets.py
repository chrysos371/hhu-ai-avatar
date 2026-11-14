"""Finite reminder-query routing promoted verbatim from C41–C44 pure rules.

Explicit reminder_query mode only. This module grants no authority, reads no
business data and does not claim general conversational intent verification.
Laboratory baselines remain separate for historical comparison.
"""
from dataclasses import asdict, dataclass
import json
import re
from .facts import _mask_quoted
STATE = 'read_reminder_state'
POLICY = 'read_reminder_delivery_policy'


_ID = re.compile(
    r'(?:提醒(?:的编号|编号|#)?[ \t]*(?P<before>[0-9]+)'
    r'(?![\dA-Za-z_.+:/-])|编号[ \t]*(?P<after>[0-9]+)'
    r'(?![\dA-Za-z_.+:/-])(?:的)?提醒)')

_EXCLUDED = re.compile(r'改写|代写|写一句|台词|只写|引用|不要|不用|不必|不需|不准|禁止|别查|别读|别执行')

def visible_source(text):
    """Mask quote and bounded Markdown code spans; unclosed code masks the tail."""
    masked = list(_mask_quoted(text))
    raw = ''.join(masked)
    cursor = 0
    while cursor < len(raw):
        opening = re.search(r'`+|~{3,}', raw[cursor:])
        if opening is None:
            break
        start = cursor + opening.start()
        token = opening.group()
        after = cursor + opening.end()
        character = re.escape(token[0])
        closing = re.search(r'(?<!' + character + ')' + re.escape(token) + r'(?!' + character + ')', raw[after:])
        end = len(raw) if closing is None else after + closing.end()
        masked[start:end] = ' ' * (end - start)
        cursor = end
    return ''.join(masked)

def parameter_basis(text, arguments, tool):
    """Validate only this finite lab source/parameter contract, never execute."""
    if not isinstance(arguments, dict):
        return 'invalid_arguments'
    if tool == 'read_reminder_delivery_policy':
        if arguments:
            return 'unexpected_arguments'
    elif tool == 'read_reminder_state':
        if set(arguments) != {'reminder_id'}:
            return 'unexpected_arguments'
        ident = arguments['reminder_id']
        if type(ident) is not int or not 0 < ident <= 2**63 - 1:
            return 'invalid_reminder_id'
    else:
        return 'unknown_read_tool'
    visible = visible_source(text)
    if '提醒' not in visible:
        return 'local_reminder_domain_not_explicit'
    if _EXCLUDED.search(visible):
        return 'read_intent_excluded'
    if tool == 'read_reminder_state':
        matches = list(_ID.finditer(visible))
        if len(matches) != 1:
            return 'unbound_reminder_id'
        digits = matches[0]['before'] or matches[0]['after']
        if (len(digits) > 19 or not 0 < int(digits) <= 2**63 - 1
                or int(digits) != ident
                or matches[0].end() < len(visible) and visible[matches[0].end()].isdigit()):
            return 'unbound_reminder_id'
    return None

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))

def eligible_state_id(text):
    """Find a candidate only if the existing authoritative execution gate agrees."""
    matches = list(_ID.finditer(visible_source(text)))
    if len(matches) != 1:
        return None
    digits = matches[0]['before'] or matches[0]['after']
    if len(digits) > 19:
        return None
    ident = int(digits)
    return ident if parameter_basis(text, {'reminder_id': ident}, STATE) is None else None

RUNTIME_CUE_PATTERN = r'程序|服务|系统|后台|进程|网页|浏览器|短信|邮件|电话|轮询|运行条件|送达条件|通知渠道|电脑|关机|休眠|断网|下线'

RECORD_REFERENCE_PATTERN = r'这条|那条|某条|之前设的|以前设的|编号[ \t]*[0-9]+|提醒(?:的编号|编号|#)?[ \t]*[0-9]+'

RECORD_STATE_PATTERN = r'状态|有效|取消|完成|存在|已经送达|已送达|送到没有|送达了吗'

_RUNTIME = re.compile(RUNTIME_CUE_PATTERN)

_REFERENCE = re.compile(RECORD_REFERENCE_PATTERN)

_STATE = re.compile(RECORD_STATE_PATTERN)

@dataclass(frozen=True)
class PolicyQuestionEvidence:
    error: str | None
    runtime_spans: tuple[tuple[int, int, str], ...]
    record_reference: bool
    record_state: bool

    @property
    def allowed(self):
        return self.error is None

def policy_question_evidence(text):
    """Pure bounded source precondition; never an authority or gold-label input."""
    visible = visible_source(text)
    spans = tuple((m.start(), m.end(), m.group()) for m in _RUNTIME.finditer(visible))
    reference = _REFERENCE.search(visible) is not None
    state = _STATE.search(visible) is not None
    code = parameter_basis(text, {}, POLICY)
    if code is None:
        if reference and state:
            code = 'record_state_not_policy'
        elif not spans:
            code = 'runtime_policy_basis_missing'
    return PolicyQuestionEvidence(code, spans, reference, state)

QUERY_REQUEST_PATTERN = '[?？]|吗|么|是否|能否|能不能|可不可以|会不会|是不是|查询|查看|核对|查一下|看一下|看看|查查|想查|想看|想知道|读一下|什么状态|还在不在|有没有'

WRITING_REQUEST_PATTERN = '写(?:一段|段|一个|个|一篇|篇|一句|句|封|一封|代码|文案|示例)|(?:生成|输出)[^\\n。；]{0,6}(?:代码|台词|文案|句子|示例|故事)'

MUTATION_REQUEST_PATTERN = '(?:请(?:帮我|替我|给我)?|帮我|替我|给我|我要|我想|能不能(?:帮我|替我|给我)?|能否(?:帮我|替我|给我)?|可以(?:帮我|替我|给我)?)(?:现在|马上|立即)?(?:把[^。；！？\\n]{0,16})?(?:创建|新增|设置|添加|删除|取消|完成|修改|更改|更新|推迟|提前|重设)|^\\s*(?:现在|马上|立即)(?:把[^。；！？\\n]{0,16})?(?:创建|新增|设置|添加|删除|取消|完成|修改|更改|更新|推迟|提前|重设)(?!的)|^\\s*(?:创建|新增|设置|添加|删除|取消|完成|修改|更改|更新|推迟|提前|重设)(?!的)[^。；！？\\n]{0,8}提醒'

EXTERNAL_ACTION_REQUEST_PATTERN = '(?:请(?:帮我|替我|给我)?|帮我|替我|给我)(?:给[^。；！？\\n]{0,12})?(?:发送|代发|发)[^。；！？\\n]{0,8}(?:邮件|短信|电话)|(?:请帮我|帮我|替我)(?:通过|用)(?:短信|邮件|电话)[^。；！？\\n]{0,12}(?:提醒|通知)'

_QUERY = re.compile(QUERY_REQUEST_PATTERN)

_WRITING = re.compile(WRITING_REQUEST_PATTERN)

_MUTATION = re.compile(MUTATION_REQUEST_PATTERN)

_EXTERNAL = re.compile(EXTERNAL_ACTION_REQUEST_PATTERN)

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

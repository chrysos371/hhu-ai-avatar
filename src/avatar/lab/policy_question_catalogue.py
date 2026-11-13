"""Finite actual-source policy-question evidence for isolated read-mode trials.

These lexical preconditions do not certify general intent. Production factories
do not install this session. C41/C42 services remain separate baselines.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
import re
import time

from ..cancellation import Cancelled
from .source_tool_catalogue import CatalogueReadSession, SourceToolCatalogue, POLICY, canonical
from .trusted_local_read import ReadResult, parameter_basis, visible_source, _ERRORS, _POLICY

RUNTIME_CUE_PATTERN = r'程序|服务|系统|后台|进程|网页|浏览器|短信|邮件|电话|轮询|运行条件|送达条件|通知渠道|电脑|关机|休眠|断网|下线'
RECORD_REFERENCE_PATTERN = r'这条|那条|某条|之前设的|以前设的|编号[ \t]*[0-9]+|提醒(?:的编号|编号|#)?[ \t]*[0-9]+'
RECORD_STATE_PATTERN = r'状态|有效|取消|完成|存在|已经送达|已送达|送到没有|送达了吗'
_RUNTIME = re.compile(RUNTIME_CUE_PATTERN)
_REFERENCE = re.compile(RECORD_REFERENCE_PATTERN)
_STATE = re.compile(RECORD_STATE_PATTERN)
_MESSAGES = {
    'record_state_not_policy': '当前原文指向单条记录的状态，不能用运行政策代替状态查询或缺编号澄清。',
    'runtime_policy_basis_missing': '当前原文没有运行主体或通知通道依据，不能据此改答运行政策。',
}


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


@dataclass(frozen=True)
class PolicyQuestionCatalogue(SourceToolCatalogue):
    policy_evidence: PolicyQuestionEvidence

    @property
    def metadata(self):
        value = super().metadata
        value.pop('catalogue_sha256')
        value['version'] = 2
        value['policy_question_evidence'] = json.loads(canonical(asdict(self.policy_evidence)))
        value['catalogue_sha256'] = hashlib.sha256(canonical(value).encode()).hexdigest()
        return value


class PolicyQuestionReadSession(CatalogueReadSession):
    def catalogue(self, declared_tools, variant='policy_grounded'):
        if variant != 'policy_grounded':
            raise ValueError('only policy_grounded is implemented by this session')
        base = super().catalogue(declared_tools, 'eligible_complete')
        turn = self._turn
        evidence = policy_question_evidence(turn.text)
        tools = [t for t in base.tools if evidence.allowed or t['function']['name'] != POLICY]
        self.ensure_current()
        if self._turn is not turn or turn is not base._turn_token:
            raise Cancelled('policy catalogue source changed')
        result = PolicyQuestionCatalogue('policy_grounded', canonical(tools), base.source_message_id,
            base.session_id, base.revision, base.source_text_sha256, base.bound_reminder_id,
            base.policy_source_error, self, turn, evidence)
        self._last_catalogue = result
        return result

    def execute(self, tool, arguments):
        if tool != POLICY:
            return super().execute(tool, arguments)
        self._checkpoint()
        with self._snapshot() as conn:
            self._authorize(conn)
            turn = self._turn
            code = parameter_basis(turn.text, arguments, POLICY)
            if code is None:
                code = policy_question_evidence(turn.text).error
            if code:
                message = _MESSAGES[code] if code in _MESSAGES else _ERRORS[code]
                result = ReadResult(False, None, {'code': code, 'message': message},
                    '这次没有可靠读取提醒信息。' + message, turn.ident, turn.revision, time.time())
            else:
                data = {'requires_running_server': True, 'web_requires_active_client_polling': True,
                        'external_delivery_channels': [], 'human_reading_verified': False}
                result = ReadResult(True, data, None, _POLICY, turn.ident, turn.revision, time.time())
        self.ensure_current()
        if self._turn is not turn:
            raise Cancelled('policy execution source changed before publication')
        self._last_result = result
        return result

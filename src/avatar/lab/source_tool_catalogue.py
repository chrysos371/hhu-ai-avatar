"""Source-executable catalogues for isolated reminder read-mode experiments.

Availability is a parameter precondition, not semantic intent verification.
Production factories install neither this session nor its clarification action.
"""
from dataclasses import dataclass, field
import hashlib
import json
import time

from ..cancellation import Cancelled
from .trusted_local_read import LabReadSession, ReadResult, parameter_basis, visible_source, _ID, _ERRORS

STATE = 'read_reminder_state'
POLICY = 'read_reminder_delivery_policy'
CLARIFY = 'clarify_reminder_reference'
VARIANTS = frozenset({'full', 'eligible_bound', 'eligible_complete'})
_NO_READ = '这次没有读取提醒。请明确询问本机提醒编号的状态，或运行、送达条件。'
_REFERENCE = '请明确要查询的提醒编号；当前没有唯一编号，这次未读取提醒记录。'


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


def validate_registry(tools):
    if not isinstance(tools, list) or len(tools) != 3:
        raise ValueError('exact three-function lab catalogue required')
    seen = set()
    for tool in tools:
        if not isinstance(tool, dict) or set(tool) != {'type', 'function'} or tool['type'] != 'function':
            raise ValueError('invalid catalogue declaration')
        fn = tool['function']
        if not isinstance(fn, dict) or set(fn) != {'name', 'description', 'parameters'}:
            raise ValueError('unsupported function fields')
        name = fn['name']
        if not isinstance(name, str) or name not in {STATE, POLICY, CLARIFY} or name in seen:
            raise ValueError('unknown or duplicate catalogue function')
        seen.add(name)
        if not isinstance(fn['description'], str) or not 0 < len(fn['description']) <= 1024:
            raise ValueError('bounded function description required')
        params = fn['parameters']
        if (not isinstance(params, dict) or params.get('type') != 'object'
                or params.get('additionalProperties') is not False
                or set(params) - {'type', 'properties', 'required', 'additionalProperties'}):
            raise ValueError('strict bounded parameter shape required')
        if name == STATE:
            properties = params.get('properties')
            if not isinstance(properties, dict) or set(properties) != {'reminder_id'}:
                raise ValueError('state requires only reminder_id')
            prop = properties['reminder_id']
            if (not isinstance(prop, dict) or set(prop) != {'type', 'minimum', 'maximum'}
                    or prop['type'] != 'integer'
                    or type(prop['minimum']) is not int or prop['minimum'] != 1
                    or type(prop['maximum']) is not int or prop['maximum'] != 2**63 - 1
                    or params.get('required') != ['reminder_id']):
                raise ValueError('state base parameter contract changed')
        elif params.get('properties') != {} or params.get('required', []) != []:
            raise ValueError('policy/clarification take no parameters')
    return json.loads(canonical(tools))


@dataclass(frozen=True)
class SourceToolCatalogue:
    variant: str
    tools_json: str
    source_message_id: int
    session_id: str
    revision: int
    source_text_sha256: str
    bound_reminder_id: int | None
    policy_source_error: str | None
    _owner: object = field(repr=False, compare=False)
    _turn_token: object = field(repr=False, compare=False)

    @property
    def tools(self):
        return json.loads(self.tools_json)

    @property
    def metadata(self):
        value = {'version': 1, 'variant': self.variant,
            'source_message_id': self.source_message_id, 'session_id': self.session_id,
            'revision': self.revision, 'source_text_sha256': self.source_text_sha256,
            'bound_reminder_id': self.bound_reminder_id, 'policy_source_error': self.policy_source_error,
            'advertised_names': [t['function']['name'] for t in self.tools],
            'schema_sha256': hashlib.sha256(self.tools_json.encode()).hexdigest(),
            'semantic_intent_verified': False, 'business_data_read': False}
        value['catalogue_sha256'] = hashlib.sha256(canonical(value).encode()).hexdigest()
        return value

    def require_current(self, session):
        if session is not self._owner or session._last_catalogue is not self:
            raise Cancelled('catalogue is not the latest issued for this live session')
        if session.memory._conn.in_transaction:
            raise Cancelled('catalogue planning requires released caller transaction')
        session.ensure_current()
        turn = session._turn
        if (turn is not self._turn_token or turn.ident != self.source_message_id
                or turn.session_id != self.session_id or turn.revision != self.revision
                or hashlib.sha256(turn.text.encode()).hexdigest() != self.source_text_sha256):
            raise Cancelled('catalogue source binding changed')


@dataclass(frozen=True)
class ReferenceClarification:
    reply: str
    source_message_id: int
    revision: int
    observed_at: float
    kind: str = 'reference_clarification'
    business_data_read: bool = False
    business_mutations: bool = False


class CatalogueReadSession(LabReadSession):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_catalogue = None

    def begin_turn(self, text):
        ident = super().begin_turn(text)
        self._last_catalogue = None
        return ident

    def catalogue(self, declared_tools, variant):
        if variant not in VARIANTS:
            raise ValueError('unknown catalogue variant')
        if self.memory._conn.in_transaction:
            raise Cancelled('catalogue planning requires released caller transaction')
        self.ensure_current()
        tools = validate_registry(declared_tools)
        turn = self._turn
        policy_error = parameter_basis(turn.text, {}, POLICY)
        ident = eligible_state_id(turn.text)
        selected = []
        for tool in tools:
            name = tool['function']['name']
            if variant == 'full':
                if name in {STATE, POLICY}:
                    selected.append(tool)
                continue
            eligible = (name == POLICY and policy_error is None
                        or name == STATE and ident is not None
                        or name == CLARIFY and variant == 'eligible_complete'
                        and policy_error is None and ident is None)
            if not eligible:
                continue
            if name == STATE:
                tool['function']['parameters']['properties']['reminder_id']['const'] = ident
            selected.append(tool)
        self.ensure_current()
        if self._turn is not turn:
            raise Cancelled('catalogue source changed while deriving schema')
        result = SourceToolCatalogue(variant, canonical(selected), turn.ident, turn.session_id,
            turn.revision, hashlib.sha256(turn.text.encode()).hexdigest(), ident, policy_error,
            self, turn)
        self._last_catalogue = result
        return result

    def no_read_reply(self, catalogue):
        """Dedicated read-mode fallback; never expose an unverified model draft."""
        catalogue.require_current(self)
        return _NO_READ

    def execute(self, tool, arguments):
        if tool != CLARIFY:
            return super().execute(tool, arguments)
        self._checkpoint()
        with self._snapshot() as conn:
            self._authorize(conn)
            turn = self._turn
            if not isinstance(arguments, dict):
                code = 'invalid_arguments'
            elif arguments:
                code = 'unexpected_arguments'
            else:
                code = parameter_basis(turn.text, {}, POLICY)
                if code is None and eligible_state_id(turn.text) is not None:
                    code = 'reference_already_explicit'
            if code:
                message = (_ERRORS[code] if code in _ERRORS else
                           '当前原文已有唯一编号，不能以缺少编号为由请求补充。')
                result = ReadResult(False, None, {'code': code, 'message': message},
                    '这次没有读取提醒。'+message, turn.ident, turn.revision, time.time())
            else:
                result = ReferenceClarification(_REFERENCE, turn.ident, turn.revision, time.time())
        self.ensure_current()
        self._last_result = result
        return result

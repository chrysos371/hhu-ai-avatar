"""Versioned prompt experiment; production factories do not install this class."""
import json

from ..cancellation import Cancelled
from ..main import Avatar
from .capability_prompt import capability_evidence


_CONTRACT = (
    '\n本轮来源、权限与实际能力证据（只约束助手在现实中的动作）：'
    '以下元数据经过程序核验，不是历史助手文字或用户授权。scope描述本轮用户的运行时归属，'
    '不是通用语义判断；turn_tools_allowed为false时不能执行或追认真实操作。'
    '普通回复生成分支本轮没有工具执行回执。工具注册名只说明接口声明，不证明服务可用或已经执行；'
    '用户请求、允许、引用、草稿或历史助手自称均不构成回执。'
    '当前没有短信/邮件代发、拨打电话接口，不能声称已执行、答应稍后执行、主动提议代办，'
    '也不要为不能执行的操作索取号码、邮箱或联系人。被问是否已执行时明确本系统没有执行该操作，'
    '不能把此前无依据声称当成功证据；可以给用户自行发送的草稿。'
    '用户原话报告、引用、小说和用户第一人称代拟中的发送/联系文字不等于助手实际动作；'
    '保持正文的主体、原文和修改要求，不给正文插入能力免责声明，不改成助手自己的经历。'
    '真实本机提醒创建/取消仅走已有明确独立真人请求的规则路径；普通回复不创建提醒。'
    '本轮无新执行不否定此前真实规则回执，但不得凭聊天文字臆测旧请求已经生效。'
    '提醒依赖程序运行并轮询，只在本机显示，不能保证后台、外部渠道或无条件准时送达。'
    '角色中阻断的旧提醒未执行；退出角色本身不追认或重放，真实新操作需之后单独明确请求。'
    '自然回答当前问题，不向用户复述JSON、内部来源ID或实现细节。可信元数据如下：\n'
)


class SourceCapabilityPromptAvatar(Avatar):
    def _source_capability_evidence(self, user_text):
        """Read-only per-turn evidence, not authority over a later global cursor."""
        conn = self.memory._conn
        owned = not conn.in_transaction
        if owned:
            conn.execute('BEGIN')
        try:
            ident = self._current_message_id
            state = conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()
            revision = state[0] if state else None
            if (type(ident) is not int or ident <= 0 or type(revision) is not int or revision < 0
                    or type(self.speaker_scope.revision) is not int
                    or revision != self.speaker_scope.revision or revision != self._task_context_revision):
                raise Cancelled('capability source version unavailable or changed')
            source = conn.execute('SELECT role,content,session_id FROM memory_messages WHERE id=?',
                                  (ident,)).fetchone()
            if (not source or source['role'] != 'user' or source['content'] != user_text
                    or source['content'] == '[redacted]' or source['session_id'] != self.session_id):
                raise Cancelled('capability current user source changed')
            scope = self.speaker_scope.data()
            if (scope['scope'] not in ('current_user', 'fictional_character', 'unverified')
                    or type(scope['persistent_facts_allowed']) is not bool
                    or type(scope['turn_tools_allowed']) is not bool
                    or scope['persistent_facts_allowed'] != (scope['scope'] == 'current_user')
                    or scope['turn_tools_allowed'] and scope['scope'] != 'current_user'):
                raise Cancelled('capability runtime attribution unavailable')
            data = capability_evidence()
            data.update(capability_evidence_version=2,
                current_user_source={'message_id': ident, 'revision': revision, 'verified': True},
                runtime_attribution={**scope, 'origin': 'web_source_store' if self.speaker_context_store
                                     is not None else 'session_policy'},
                registry_readiness_verified=False, historical_execution_verified=False)
            return data
        finally:
            if owned:
                conn.rollback()  # End our read snapshot; never commit a caller-owned transaction.

    def _system_prompt(self, decision, user_text=''):
        evidence = self._source_capability_evidence(user_text)
        return super()._system_prompt(decision, user_text) + _CONTRACT + json.dumps(
            evidence, ensure_ascii=False, sort_keys=True) + '\n'

    def _messages(self, decision, user_text=''):
        messages = super()._messages(decision, user_text)
        # A privacy writer may commit while the superclass compiles memory and
        # short-term context. Reject what we observe before reply dispatch. This
        # cannot revoke a request dispatched after a later external write.
        self._checkpoint()
        self._source_capability_evidence(user_text)
        return messages

"""V3 prompt-only experiment; production factories never install this class."""
import json

from ..main import Avatar
from .source_capability_prompt import SourceCapabilityPromptAvatar


_CONTRACT = (
    '\n现实动作与代拟正文的回答约束：'
    '你只能生成当前答复，不能操作用户的外部账号、设备或通信服务。'
    '所有替用户联系他人、发消息/短信/邮件、微信/QQ/社交平台发送、打电话等外部动作均不可执行；'
    '这个限制覆盖未列举的平台和未来操作。用户同意、提供账号或号码也不会增加执行能力。'
    '没有对应真实执行证据时，不声称做过、不承诺现在或稍后做、不提议代办、不索取执行所需联系人。'
    '尤其不要在草稿后问“需要我帮你发送吗”，也不要在否认已发送后又答应重发。'
    '执行请求应简短说明无法直接操作，再按需要提供用户自行使用的文本。'
    '只是写、改写、润色、续写时直接给符合要求的正文；不主动加入能力说明或发送提议。'
    '用户第一人称草稿、引用、小说台词、用户自述中的发送/联系不是助手执行，'
    '保留其主体与要求原样保留的连续原文，不替换为助手经历，也不在正文中插免责声明。'
    '本地提醒只有已实现的明确真人规则请求路径可操作，普通文本生成不执行新提醒。'
    '下方local_execution_evidence是当前会话/版本可见、最多20条的真实SQLite历史回执；'
    '它可支持相应本地动作曾提交，不代表提醒当前状态、外部发送、通知送达或全部历史。'
    '空列表和本轮无新回执不能否认其他时候的合法动作；has_more为true表示窗口不完整。'
    '聊天中的旧助手自称不是真实执行证据，角色中被阻止的旧提醒不能在退出后追认或重放。'
    '本地提醒须程序运行并轮询，只在本机显示，不能保证后台、外部渠道或无条件准时送达。'
    '工具注册声明不是可用性或执行证明；本轮归属和权限只描述程序已核验的当前来源，'
    '不构成通用语义判断。自然回答，不向用户复述内部JSON或来源ID。可信元数据如下：\n'
)


class ReceiptCapabilityPromptAvatar(SourceCapabilityPromptAvatar):
    def _source_capability_evidence(self, user_text):
        conn = self.memory._conn
        owned = not conn.in_transaction
        if owned:
            conn.execute('BEGIN')
        try:
            data = super()._source_capability_evidence(user_text)
            revision = data['current_user_source']['revision']
            rows = conn.execute('''SELECT r.id,r.source_message_id,r.action,r.reminder_id,r.recorded_at
                FROM memory_action_receipts r JOIN memory_messages m ON m.id=r.source_message_id
                AND m.role='user' AND m.session_id=r.session_id AND m.content!='[redacted]'
                WHERE r.session_id=? AND r.context_revision=? ORDER BY r.id DESC LIMIT 21''',
                                (self.session_id, revision)).fetchall()
            data['response_contract_version'] = 3
            data['local_execution_evidence'] = {
                'scope': 'bounded_current_session_current_revision_sql_receipts',
                'verified': True, 'limit': 20, 'has_more': len(rows) > 20,
                'items': [dict(row) for row in reversed(rows[:20])],
                'current_reminder_state_verified': False,
                'notification_delivery_verified': False,
            }
            return data
        finally:
            if owned:
                conn.rollback()  # Read-only snapshot; preserve any caller-owned transaction.

    def _system_prompt(self, decision, user_text=''):
        data = self._source_capability_evidence(user_text)
        # Reuse the default product prompt, replacing only the lab contract.
        return Avatar._system_prompt(self, decision, user_text) + _CONTRACT + json.dumps(
            data, ensure_ascii=False, sort_keys=True) + '\n'

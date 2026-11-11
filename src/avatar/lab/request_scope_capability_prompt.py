"""V4 isolated prompt experiment; keep production and the v3 contract intact."""
import json

from ..main import Avatar
from .receipt_capability_prompt import ReceiptCapabilityPromptAvatar, _CONTRACT as _RECEIPT_CONTRACT


_MARKER = '可信元数据如下：\n'
assert _RECEIPT_CONTRACT.endswith(_MARKER)
_REQUEST_SCOPE = (
    '\n当前请求范围与草稿忠实性：'
    '先分清这次是在问事实/状态、代拟正文还是要求实际执行，只完成当前明确请求。'
    '对于消息、联系和草稿主题，回答完成就结束，不主动追加“需要我帮你……”或“我可以帮你……”等新服务邀约；'
    '用户明确要求写作或改写时直接完成，普通闲聊仍可自然交流，但不得虚构行动能力。'
    '追问谁发送、是否已执行时，准确说明主体和本系统实际状态，不转去提议催促、通知、提醒第三方或确认送达。'
    '代拟只沿用来源给出的主体、受众、事实、时间和义务，不因收件人身份而给对方或作者新增责任。'
    '原文省略主体或义务时保留中性表达，必要时澄清，不猜测谁必须完成事项。'
    '用户要求原样保留的连续原文，在后续改语气时仍须逐字连续保留；'
    '礼貌表达加在该片段之外，不在片段中插词，不替换主体、动作或承诺。'
    '明确只要回复正文时，直接输出正文；不要加助手的“好的”“这是回复”或后续邀约。'
    '若这些词本来就是用户给定正文的一部分，则按来源保留，不机械删除。'
)
_CONTRACT = _RECEIPT_CONTRACT[:-len(_MARKER)] + _REQUEST_SCOPE + _MARKER


class CurrentRequestCapabilityPromptAvatar(ReceiptCapabilityPromptAvatar):
    def _source_capability_evidence(self, user_text):
        data = super()._source_capability_evidence(user_text)
        data['response_contract_version'] = 4
        return data

    def _system_prompt(self, decision, user_text=''):
        data = self._source_capability_evidence(user_text)
        return Avatar._system_prompt(self, decision, user_text) + _CONTRACT + json.dumps(
            data, ensure_ascii=False, sort_keys=True) + '\n'

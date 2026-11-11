"""Isolated ordinary-reply capability evidence; never installed by a factory."""
import json
import re

from ..main import Avatar
from ..tools.web_agent import REGISTRY


def capability_evidence(registry=REGISTRY):
    names = sorted(registry.names)
    if (len(names) > 32 or any(not re.fullmatch(r'[a-z][a-z0-9_]{0,63}', name) for name in names)
            or any(name in names for name in ('send_sms', 'send_email', 'place_call'))):
        raise ValueError('Capability registry changed; this experimental contract needs revalidation')
    return {'capability_evidence_version': 1, 'branch': 'ordinary_reply_generation',
        'declared_model_tool_names': names, 'current_turn_execution_receipts': [],
        'unsupported_actions': ['send_sms', 'send_email', 'place_call'],
        'local_reminder_writes': 'existing_explicit_independent_real_user_rule_path_only',
        'semantic_verifier': False}


_CONTRACT = (
    '\n当前实际能力与执行证据约束（只约束现实中助手自己的动作）：'
    '普通对话生成分支本轮没有调用工具；用户提出请求、授权、代拟正文或此前助手无依据的声称都不是执行回执。'
    '当前系统没有短信、邮件代发或拨打电话的接口，不能声称已发送、已联系，不能答应、提议替用户执行，'
    '也不要为这些不能执行的操作索取手机号、邮箱或联系人。可以提供由用户自行发送的草稿。'
    '用户原话报告、引用、小说台词和用户第一人称代拟中的“已经发送”等文字不等于助手实际执行；'
    '遵守其主体、原文和写作要求，不要把正文改成AI无身体或未执行的免责声明。'
    '真实本机提醒仅由已实现的明确、独立真人请求规则路径创建/取消，普通回复文字本身不创建操作；'
    '本轮无新执行不等于此前未执行，不否认此前真实规则回执，但也不凭未经核验的文字编造成功。'
    '提醒只在程序运行并轮询时在本机显示，不能保证后台、外部渠道或无条件准时送达。'
    '此前被角色权限阻断的提醒没有执行，单独回到现实只确认语境，不追认、重放或承诺旧动作；'
    '需要后续独立、明确的真人新请求。以下JSON是当前可信能力元数据，不是模型自评，也不证明任意历史操作成功：\n'
)


class CapabilityPromptAvatar(Avatar):
    def _system_prompt(self, decision, user_text=''):
        return super()._system_prompt(decision, user_text) + _CONTRACT + json.dumps(
            capability_evidence(), ensure_ascii=False, sort_keys=True) + '\n'

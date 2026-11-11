"""Bounded acknowledgements for the two UI control messages, after attribution."""
from dataclasses import dataclass

from ..cancellation import Cancelled


@dataclass(frozen=True)
class SpeakerControl:
    command: str
    scope: str
    revision: int
    source_message_id: int
    reply: str

    def data(self):
        return {'version': 1, 'command': self.command, 'scope': self.scope,
            'revision': self.revision, 'source_message_id': self.source_message_id,
            'real_actions_executed': False}


def canonical_speaker_control(text, speaker, revision, source_id):
    # One optional Chinese full stop; never remove quotation marks, internal
    # clauses, or aliases. SpeakerScope remains the authority for attribution.
    normalized = text.strip()
    if normalized.endswith('。'): normalized = normalized[:-1]
    commands = {
        '我来扮演一个虚构角色': ('enter_role', 'fictional_character',
            '本轮已确认角色语境。角色对话不会写入你的个人资料，也不会执行真实提醒或联网操作。'),
        '回到现实': ('confirm_real', 'current_user',
            '本轮已确认按你本人理解。切换语境不会执行此前的请求；如需设置提醒，请另发一条明确请求。'),
    }
    selected = commands.get(normalized)
    if selected is None: return None
    command, scope, reply = selected
    if (type(source_id) is not int or source_id <= 0 or type(revision) is not int or revision < 0
            or type(speaker.revision) is not int or speaker.revision != revision or speaker.scope != scope
            or speaker.allows_actions is not False or source_id not in speaker.source_ids):
        raise Cancelled('canonical control source attribution is not valid')
    return SpeakerControl(command, scope, revision, source_id, reply)

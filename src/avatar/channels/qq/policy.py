"""Local, deterministic QQ admission and expression policy; never wakes proactively."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import os


@dataclass(frozen=True)
class ReplyPolicy:
    group_cooldown: int = 2
    group_per_minute: int = 2
    group_per_hour: int = 20
    quiet_start: int = -1
    quiet_end: int = -1

    def __post_init__(self):
        if not (0 <= self.group_cooldown <= 3600 and
                1 <= self.group_per_minute <= 60 and
                self.group_per_minute <= self.group_per_hour <= 1000):
            raise ValueError('Invalid QQ rate limits')
        if (self.quiet_start, self.quiet_end) != (-1, -1) and not (
            0 <= self.quiet_start <= 23 and 0 <= self.quiet_end <= 23 and
            self.quiet_start != self.quiet_end
        ):
            raise ValueError('Quiet hours require two distinct hours or both -1')

    @classmethod
    def environment(cls):
        return cls(**{name: int(os.getenv('AVATAR_QQ_' + name.upper(), str(default)))
                      for name, default in (
                          ('group_cooldown', 2), ('group_per_minute', 2),
                          ('group_per_hour', 20), ('quiet_start', -1), ('quiet_end', -1))})

    def quiet(self, now):
        if self.quiet_start == -1:
            return False
        hour = datetime.fromtimestamp(now, timezone(timedelta(hours=8))).hour
        if self.quiet_start < self.quiet_end:
            return self.quiet_start <= hour < self.quiet_end
        return hour >= self.quiet_start or hour < self.quiet_end


EXPRESSION_HINT = (
    '\nQQ表达约束（服从已有事实、角色和安全边界）：'
    '按当前请求和上下文选择回应方式，不凭个别情绪词给人下结论。'
    '要文案、改写、步骤时先给可直接使用的产物，缺失信息留占位；'
    '只想倾听时接住具体内容，不安排任务、不连续追问；'
    '明确告别时简短收尾，不另开话题。普通闲聊可以轻松，但不强行玩梗。'
    '不扮演群管理员，不推测未收到的群聊内容，不编造线下经历；'
    '自然表达，不宣读策略或情绪评分。需要解释或完成任务时允许超过三句话。\n'
)

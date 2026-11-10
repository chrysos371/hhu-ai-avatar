"""情绪模型与行为决策树（自研，AIRI 空白区）。

情绪状态用 PAD 二维模型（valence 愉悦度 / arousal 唤醒度）：
- 用户的最新观测与角色状态分开；角色随真实经过的时间向中性衰减
- 行为决策树根据「意图 × 情绪象限」决定回应风格与语音/口型参数
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import re
from time import monotonic
from typing import Callable


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


@dataclass
class EmotionState:
    """二维情绪状态（PAD 模型的 P/A 两维）。"""

    valence: float = 0.0  # 愉悦度：-1 负面 ~ +1 正面
    arousal: float = 0.0  # 唤醒度：-1 平静 ~ +1 激动

    def label(self) -> str:
        """映射到离散情绪标签。"""
        v, a = self.valence, self.arousal
        if v >= 0.15 and a >= 0.15:
            return "开心"
        if v <= -0.15 and a >= 0.15:
            return "生气/焦躁"
        if v <= -0.15 and a <= -0.15:
            return "悲伤/低落"
        if v >= 0.15 and a <= -0.15:
            return "平静/满足"
        return "中性"


@dataclass
class Decision:
    """行为决策结果：回应风格与语音/口型参数。"""

    style: str            # 语气风格
    temperature: float    # LLM 采样温度
    speech_rate: str      # TTS 语速（Edge-TTS 格式，如 "+10%"）
    speech_pitch: str     # TTS 音调（如 "+8Hz"）
    mouth_intensity: float  # 口型强度（缩放张嘴幅度）
    persona_hint: str     # 注入 LLM 提示词的情绪描述
    strategy: str = "answer"  # 追加默认字段，兼容旧的位置参数构造


# 情绪词典：用于从文本粗判情绪倾向（可扩展为更精细的词典或模型）
_POSITIVE = [
    "开心", "高兴", "喜欢", "太好了", "棒", "爱", "谢谢", "有趣", "兴奋", "期待",
    "哈哈", "赞", "厉害", "温暖", "幸福", "满意", "惊喜",
]
_NEGATIVE = [
    "难过", "伤心", "烦", "累", "孤独", "委屈", "哭", "压力", "焦虑", "崩溃",
    "生气", "愤怒", "讨厌", "失望", "痛苦", "害怕", "无聊", "寂寞", "沮丧", "疲惫",
]
_HIGH_AROUSAL = [
    "哈哈", "兴奋", "激动", "生气", "愤怒", "崩溃", "着急", "急死", "疯狂", "超级", "惊喜",
]
# 低唤醒词（难过/疲惫类）：降唤醒度，让负面情绪「沉下来」而非「躁起来」
_LOW_AROUSAL = [
    "难过", "伤心", "累", "疲惫", "孤独", "寂寞", "沮丧", "失望", "无聊", "委屈",
    "低落", "平静", "放松", "困",
]
# 否定词：紧邻情绪词时反转其极性（如「不开心」「不难过」）
_NEGATORS = ["一点也不", "并不", "不太", "才不", "毫不", "不怎么", "没那么", "不再", "不要", "不用", "不需要", "不", "没", "别", "无"]
_GOOD_NEWS = ("考上", "通过考试", "及格", "拿到录取", "录取了", "获奖", "成功了", "升职了")
_FOOD_PREFERENCE = re.compile(
    r"(?:喜欢|讨厌|爱)(?:吃|喝)?(?:咖啡|奶茶|茶|香菜|火锅|辣椒|榴莲|米饭|面条|苹果|香蕉)"
)


def _is_negated_at(text: str, idx: int) -> bool:
    """只在当前出现位置检查局部否定，保留常见双重否定。"""
    prefix = text[:idx]
    if prefix.endswith(("不是不", "并非不", "没有不", "不是没", "不是不想要", "并非不想要")):
        return False
    return prefix.endswith(tuple(_NEGATORS))


def _no_advice(text: str) -> bool:
    # 「别安慰我，帮我分析」不属于拒绝建议；「不是不想要建议」也不属于。
    text = re.sub(r"(?:不是|并非)不(?=想要|想听|想|需要|要|用)", "", text)
    return bool(re.search(
        r"(?:不要|不用|不需要|别|不想要|不想听)(?:再|给我|给|你给我|你的|提供|任何|提|的|出|主动)*"
        r"(?:建议|意见|解决方案|主意)|(?:不要|不用|别)帮我想办法|"
        r"(?:不要|不用|不需要|别|不想)(?:再|你|我|听|来)*"
        r"(?:告诉我(?:应该|该|具体)?(?:怎么|如何)做|帮我(?:分析|制定|安排|规划|解决|想办法))|"
        r"只想(?:说说|倾诉|吐槽)|听我说(?:就好|就行)", text
    ))


def _has_request(text: str) -> bool:
    return any(not _is_negated_at(text, m.start()) for m in re.finditer(
        r"帮我|帮帮我|告诉我|记住我|给我|(?<![\u4e00-\u9fff])(?:请|麻烦|记住|忘了)", text
    ))


class EmotionEngine:
    """情绪引擎：状态维护 + 意图分类 + 行为决策。"""

    def __init__(self, decay: float | None = None, clock: Callable[[], float] | None = None,
                 half_life_seconds: float = 300.0):
        self._state = EmotionState()
        self.user_state = EmotionState()
        self.decay = decay
        if not math.isfinite(half_life_seconds) or half_life_seconds <= 0:
            raise ValueError('half_life_seconds must be a positive finite number')
        self.half_life_seconds = float(half_life_seconds)
        self._clock = clock if clock is not None else monotonic
        self._last_tick = self._clock()
        self._energy = .5
        self._energy_tick = self._last_tick
        self._observation_text = ""
        self._has_observation = False

    @property
    def energy(self) -> float:
        """Role activity, independent of sentiment; relaxes toward .5 in six hours."""
        now = self._clock()
        self._energy = .5 + (self._energy - .5) * 2 ** (-max(0, now - self._energy_tick) / 21600)
        self._energy_tick = max(now, self._energy_tick)
        return self._energy

    @property
    def state(self) -> EmotionState:
        """角色状态；读取时结算空闲时间的衰减，用户观测保持不变。"""
        self._decay_elapsed()
        return self._state

    @state.setter
    def state(self, value: EmotionState) -> None:
        self._state = value
        self._last_tick = self._clock()

    def _relax(self, elapsed: float) -> None:
        # Keep the old per-second decay argument for callers that set it;
        # default behavior is defined by a human-readable half-life.
        factor = ((1 - _clamp(self.decay, 0.0, 1.0)) ** elapsed
                  if self.decay is not None
                  else 0.5 ** (elapsed / self.half_life_seconds))
        self._state.valence *= factor
        self._state.arousal *= factor

    def _decay_elapsed(self) -> None:
        now = self._clock()
        self._relax(max(0.0, now - self._last_tick))
        self._last_tick = max(now, self._last_tick)

    # ------------------------------------------------------------------ 状态维护
    def decay_step(self) -> None:
        """兼容旧调用：先结算经过的时间，再显式衰减一秒。"""
        self._decay_elapsed()
        self._relax(1.0)

    @staticmethod
    def infer(text: str) -> tuple[float, float]:
        """从文本提取用户观测 (valence, arousal)，不累加历史心情。"""
        # 狭窄的食物词表仅消除偏好动词，不吞掉同句的真实情绪。
        text = _FOOD_PREFERENCE.sub("", text)
        dv = da = 0.0
        for words, amount, axis in (
            (_POSITIVE, 0.3, "v"), (_NEGATIVE, -0.3, "v"),
            (_HIGH_AROUSAL, 0.25, "a"), (_LOW_AROUSAL, -0.25, "a"),
        ):
            for word in words:
                for match in re.finditer(re.escape(word), text):
                    delta = -amount if _is_negated_at(text, match.start()) else amount
                    if axis == "v":
                        dv += delta
                    else:
                        da += delta
        for word in _GOOD_NEWS:
            for match in re.finditer(word, text):
                dv += -0.3 if _is_negated_at(text, match.start()) else 0.3
        if text.count("！") + text.count("!") >= 2:
            da += 0.2
        return _clamp(dv), _clamp(da)

    def update(self, text: str) -> EmotionState:
        """兼容规则入口：观测用户情绪并返回角色状态。"""
        return self.observe(*self.infer(text), text=text)

    def update_from(self, dv: float, da: float) -> EmotionState:
        """兼容外部（如 LLM）入口：参数现在表示最新用户观测。"""
        return self.observe(dv, da)

    def observe(self, valence: float, arousal: float, text: str = "") -> EmotionState:
        """隔离用户观测与角色表达，负面输入产生稳定的支持状态。"""
        self._decay_elapsed()
        self._energy = min(.85, self.energy + .025)
        self.user_state = EmotionState(_clamp(valence), _clamp(arousal))
        self._observation_text = text
        self._has_observation = True
        if valence < -0.1:
            # 立即退出上一轮兴奋；不把用户愤怒映射到角色愤怒或强行乐观。
            self._state.valence, self._state.arousal = 0.05, -0.2
        elif valence > 0.1:
            self._state.valence = _clamp(self._state.valence + self.user_state.valence * 0.5)
            self._state.arousal = _clamp(self._state.arousal + self.user_state.arousal * 0.5)
        return self._state

    # ------------------------------------------------------------------ 意图分类
    @staticmethod
    def classify_intent(text: str) -> str:
        """意图分类：情感倾诉 / 提问 / 指令 / 闲聊。"""
        if _no_advice(text):
            return "情感倾诉"
        if _has_request(text):
            return "指令"
        if "?" in text or "？" in text or any(
            w in text for w in ["什么", "怎么", "为什么", "谁", "哪里", "吗", "呢", "如何", "多少"]
        ):
            return "提问"
        if EmotionEngine.infer(text)[0] < -0.1:
            return "情感倾诉"
        return "闲聊"

    # ------------------------------------------------------------------ 行为决策树
    def decide(self, text: str, *, expression_override: dict | None = None) -> Decision:
        """行为决策树：意图 × 情绪象限 → 回应策略。"""
        intent = self.classify_intent(text)
        state = self.state
        if expression_override is not None:
            state=EmotionState(valence=expression_override['valence'],arousal=expression_override['arousal'])
        v, a = state.valence, state.arousal
        label = state.label()
        uv, ua = self.infer(text)
        if self._has_observation and (text == self._observation_text or not self._observation_text):
            uv, ua = self.user_state.valence, self.user_state.arousal

        # 明确倾听 > 任务/问题 > 本轮情绪。历史角色心情不控制任务策略。
        if re.fullmatch(r'(?:今天|我)?(?:先)?(?:晚安|下了|不聊了|去睡了|先睡了|拜拜|再见)(?:[，,、 ]*(?:晚安|拜拜|再见))?[！!。～~ ]*', text.strip()):
            strategy = 'close'
        elif _no_advice(text):
            strategy = "listen"
        elif text.strip(" ！!。？?") in ("帮帮我", "帮我", "怎么办", "我该怎么办"):
            strategy = "clarify"
        elif intent in ("指令", "提问"):
            strategy = "advise" if any(w in text for w in (
                "怎么", "如何", "建议", "计划", "分析", "安排", "复习", "解决"
            )) else "answer"
        elif uv < -0.1:
            strategy = "empathize"
        elif uv > 0.1:
            strategy = "celebrate"
        else:
            strategy = "answer"

        # 1. 按意图定基础风格
        if strategy in ("listen", "empathize"):
            style, temperature, rate, pitch, mouth = "温柔共情", 0.9, "-10%", "-5Hz", 0.6
        elif strategy == "celebrate":
            style, temperature, rate, pitch, mouth = "真诚祝贺", 0.8, "+5%", "+3Hz", 0.8
        elif strategy == "clarify" or intent == "提问":
            style, temperature, rate, pitch, mouth = "清晰耐心", 0.3, "+0%", "+0Hz", 0.7
        elif intent == "指令":
            style, temperature, rate, pitch, mouth = "冷静执行", 0.2, "+0%", "+0Hz", 0.7
        else:  # 闲聊
            style, temperature, rate, pitch, mouth = "自然随和", 0.9, "+0%", "+0Hz", 0.75

        # 2. 按情绪象限调节语音/口型
        if uv < -0.1:
            # 负面高唤醒时优先平复，避免把愤怒/焦虑映射成活泼表达。
            rate, pitch, mouth, style = "-10%", "-6Hz", mouth - 0.1, style + "·沉稳"
        elif a >= 0.15 and strategy == "celebrate":  # 任务保持清晰，不受历史兴奋影响
            rate, pitch, mouth, style = "+12%", "+8Hz", mouth + 0.15, style + "·活泼"
        elif a <= -0.15:  # 低唤醒 → 更舒缓
            rate, pitch, mouth, style = "-12%", "-6Hz", mouth - 0.1, style + "·舒缓"
        if uv < -0.15 and strategy in ("listen", "empathize"):
            pitch, style = "-6Hz", style + "·安抚"

        guidance = {
            "listen": "认真倾听，承接感受；不要主动给建议或解决方案。",
            "clarify": "先简短询问具体目标或缺少的信息。",
            "empathize": "承认用户感受，沉稳共情，避免强行积极或淡化愤怒。",
            "advise": "聚焦用户当前请求，提供具体可执行的分析和步骤。",
            "celebrate": "真诚回应本轮好消息，适度祝贺。",
            "answer": "直接、清晰地回应当前问题或话题。",
            "close": "简短温和地道别，不追问，不开启新话题，不挽留用户。",
        }[strategy]
        persona_hint = (
            f"角色当前情绪：{label}（valence={v:.2f}, arousal={a:.2f}），"
            f"用户观测：valence={uv:.2f}, arousal={ua:.2f}；"
            f"回应策略：{strategy}；{guidance}语气风格：{style}"
        )
        if strategy == 'answer' and intent == '闲聊':
            persona_hint += f'；角色活跃度={self.energy:.2f}，只调节表达热情，不改变事实或用户意图。'

        return Decision(
            style=style,
            temperature=_clamp(temperature, 0.0, 1.5),
            speech_rate=rate,
            speech_pitch=pitch,
            mouth_intensity=_clamp(mouth, 0.1, 1.2),
            persona_hint=persona_hint,
            strategy=strategy,
        )

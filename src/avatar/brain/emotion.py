"""情绪模型与行为决策树（自研，AIRI 空白区）。

情绪状态用 PAD 二维模型（valence 愉悦度 / arousal 唤醒度）：
- 从用户输入提取情绪倾向，叠加到当前状态，并随时间衰减（情绪连贯但会平复）
- 行为决策树根据「意图 × 情绪象限」决定回应风格与语音/口型参数
"""
from __future__ import annotations

from dataclasses import dataclass


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


# 情绪词典：用于从文本粗判情绪倾向（可扩展为更精细的词典或模型）
_POSITIVE = [
    "开心", "高兴", "喜欢", "太好了", "棒", "爱", "谢谢", "有趣", "兴奋", "期待",
    "哈哈", "赞", "厉害", "温暖", "幸福", "满意", "惊喜",
]
_NEGATIVE = [
    "难过", "伤心", "烦", "累", "孤独", "委屈", "哭", "压力", "焦虑", "崩溃",
    "生气", "讨厌", "失望", "痛苦", "害怕", "无聊", "寂寞", "沮丧", "疲惫",
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
_NEGATORS = ["一点也不", "并不", "不太", "才不", "毫不", "不", "没", "别", "无"]


def _is_negated(text: str, word: str) -> bool:
    """判断 text 中的 word 是否被否定词紧邻修饰（如「不开心」中的「开心」）。"""
    idx = text.find(word)
    if idx <= 0:
        return False
    for neg in _NEGATORS:
        if text[max(0, idx - len(neg)):idx] == neg:
            return True
    return False


class EmotionEngine:
    """情绪引擎：状态维护 + 意图分类 + 行为决策。"""

    def __init__(self, decay: float = 0.15):
        self.state = EmotionState()
        self.decay = decay

    # ------------------------------------------------------------------ 状态维护
    def decay_step(self) -> None:
        """时间衰减：情绪逐渐向中性回归。"""
        self.state.valence *= 1 - self.decay
        self.state.arousal *= 1 - self.decay

    def infer(self, text: str) -> tuple[float, float]:
        """从文本提取情绪倾向增量 (delta_valence, delta_arousal)。"""
        dv = da = 0.0
        for w in _POSITIVE:
            if w in text:
                dv += -0.3 if _is_negated(text, w) else 0.3
        for w in _NEGATIVE:
            if w in text:
                dv += 0.3 if _is_negated(text, w) else -0.3
        for w in _HIGH_AROUSAL:
            if w in text:
                da += -0.25 if _is_negated(text, w) else 0.25
        for w in _LOW_AROUSAL:
            if w in text:
                da += 0.25 if _is_negated(text, w) else -0.25
        if text.count("！") + text.count("!") >= 2:
            da += 0.2
        return _clamp(dv), _clamp(da)

    def update(self, text: str) -> EmotionState:
        """根据用户输入更新情绪状态，返回新状态。"""
        dv, da = self.infer(text)
        self.decay_step()
        self.state.valence = _clamp(self.state.valence + dv)
        self.state.arousal = _clamp(self.state.arousal + da)
        return self.state

    def update_from(self, dv: float, da: float) -> EmotionState:
        """用外部（如 LLM）提供的情绪增量更新状态，返回新状态。"""
        self.decay_step()
        self.state.valence = _clamp(self.state.valence + dv)
        self.state.arousal = _clamp(self.state.arousal + da)
        return self.state

    # ------------------------------------------------------------------ 意图分类
    @staticmethod
    def classify_intent(text: str) -> str:
        """意图分类：情感倾诉 / 提问 / 指令 / 闲聊。"""
        if any(
            w in text
            for w in ["难过", "伤心", "烦", "累", "孤独", "委屈", "哭", "压力", "焦虑", "崩溃"]
        ):
            return "情感倾诉"
        if "?" in text or "？" in text or any(
            w in text for w in ["什么", "怎么", "为什么", "谁", "哪里", "吗", "呢", "如何", "多少"]
        ):
            return "提问"
        if text.startswith(("帮我", "告诉", "记住", "忘了", "请", "麻烦")) or "记住我" in text:
            return "指令"
        return "闲聊"

    # ------------------------------------------------------------------ 行为决策树
    def decide(self, text: str) -> Decision:
        """行为决策树：意图 × 情绪象限 → 回应策略。"""
        intent = self.classify_intent(text)
        v, a = self.state.valence, self.state.arousal
        label = self.state.label()

        # 1. 按意图定基础风格
        if intent == "情感倾诉":
            style, temperature, rate, pitch, mouth = "温柔共情", 0.9, "-10%", "-5Hz", 0.6
        elif intent == "提问":
            style, temperature, rate, pitch, mouth = "清晰耐心", 0.3, "+0%", "+0Hz", 0.7
        elif intent == "指令":
            style, temperature, rate, pitch, mouth = "冷静执行", 0.2, "+0%", "+0Hz", 0.7
        else:  # 闲聊
            style, temperature, rate, pitch, mouth = "自然随和", 0.9, "+0%", "+0Hz", 0.75

        # 2. 按情绪象限调节语音/口型
        if a >= 0.15:  # 高唤醒 → 更活泼
            rate, pitch, mouth, style = "+12%", "+8Hz", mouth + 0.15, style + "·活泼"
        elif a <= -0.15:  # 低唤醒 → 更舒缓
            rate, pitch, mouth, style = "-12%", "-6Hz", mouth - 0.1, style + "·舒缓"
        if v <= -0.15:  # 负面情绪 → 加安抚色彩
            pitch, style = "-6Hz", style + "·安抚"

        persona_hint = (
            f"当前情绪：{label}（valence={v:.2f}, arousal={a:.2f}），语气风格：{style}"
        )

        return Decision(
            style=style,
            temperature=_clamp(temperature, 0.0, 1.5),
            speech_rate=rate,
            speech_pitch=pitch,
            mouth_intensity=_clamp(mouth, 0.1, 1.2),
            persona_hint=persona_hint,
        )

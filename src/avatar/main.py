"""全链路编排：听 → 思 → 演 → 记。

Avatar 类把 ASR / LLM / 记忆 / 情绪 / TTS / 口型串成一条闭环，
`python -m avatar.main` 启动交互式对话（demo 模式，无 API key 也能跑通情绪+记忆+决策）。
"""
from __future__ import annotations

import sys
from typing import Optional

from .brain.emotion import Decision, EmotionEngine
from .brain.llm import LLMEngine
from .brain.memory import MemoryStore
from .config import config
from .ears.asr import ASREngine, TextInputEngine
from .face.lipsync import LipSyncEngine
from .mouth.tts import EdgeTTSEngine, TTSEngine


class Avatar:
    """带记忆与情感的 AI 虚拟形象。"""

    def __init__(
        self,
        db_path: Optional[str] = None,
        asr: Optional[ASREngine] = None,
        llm: Optional[LLMEngine] = None,
        tts: Optional[TTSEngine] = None,
    ):
        self.memory = MemoryStore(db_path or config.memory_db_path)
        self.emotion = EmotionEngine()
        self.asr = asr or TextInputEngine()
        self.llm = llm or LLMEngine()
        self.tts = tts or EdgeTTSEngine()
        self.lipsync = LipSyncEngine()
        self._llm_available = self.llm.available

    # ------------------------------------------------------------------ 提示词
    def _system_prompt(self, decision: Decision) -> str:
        profile = self.memory.get_user_profile()
        profile_str = "；".join(f"{k}={v}" for k, v in profile.items()) or "（暂无）"
        facts = self.memory.recall(limit=5)
        facts_str = "；".join(r["content"] for r in facts) or "（暂无）"
        return (
            f"你是{config.avatar_name}，{config.avatar_persona}。\n"
            f"{decision.persona_hint}。\n"
            f"你记得关于用户的信息：{profile_str}。\n"
            f"相关长期记忆：{facts_str}。\n"
            f"回复要自然、口语化、简短（1~3 句话），像个真实的伙伴。"
        )

    def _messages(self, decision: Decision) -> list[dict]:
        return [{"role": "system", "content": self._system_prompt(decision)}] + (
            self.memory.get_short_term()
        )

    def _extract_facts(self, text: str) -> None:
        """从用户输入提取简单事实写入长期记忆（规则版，后续可换 LLM 抽取）。"""
        import re

        m = re.search(r"我(?:叫|是)([^\s，。！？,.!?]{1,10})", text)
        if m:
            self.memory.remember_user("名字", m.group(1))
        m = re.search(r"我(?:喜欢|爱|讨厌)([^\s，。！？,.!?]{1,20})", text)
        if m:
            self.memory.remember_user("偏好", m.group(1))

    def _fallback_reply(self, user_text: str, decision: Decision) -> str:
        """无 LLM 时的规则回复（保证 demo 能跑通全链路）。"""
        label = self.emotion.state.label()
        intent = self.emotion.classify_intent(user_text)
        if intent == "情感倾诉":
            return "我在这里陪着你，别难过，慢慢说给我听。"
        if intent == "提问":
            return "这是个好问题～（当前未接入大模型，请在 .env 配置 LLM_API_KEY）"
        if intent == "指令":
            return "好的，我记住了。"
        return f"（demo 模式）我现在感觉{label}，你刚才说的是「{user_text[:15]}」吧？"

    # ------------------------------------------------------------------ 主流程
    def respond(
        self,
        user_text: str,
        use_tts: bool = False,
        tts_path: str = "./data/reply.mp3",
    ) -> dict:
        """处理一条用户输入，返回回复 + 情绪 + 决策 + 音频路径。"""
        # 1. 短期记忆记下用户输入
        self.memory.add_short_term("user", user_text)
        self._extract_facts(user_text)
        # 2. 情绪更新
        self.emotion.update(user_text)
        # 3. 行为决策
        decision = self.emotion.decide(user_text)
        # 4. LLM 回复（无 key 降级）
        if self._llm_available:
            reply = self.llm.chat(self._messages(decision), temperature=decision.temperature)
        else:
            reply = self._fallback_reply(user_text, decision)
        # 5. 短期记忆记下回复
        self.memory.add_short_term("assistant", reply)
        # 6. TTS（可选）
        audio_path = None
        if use_tts:
            audio_path = self.tts.synthesize(
                reply, tts_path, decision.speech_rate, decision.speech_pitch
            )
        return {
            "reply": reply,
            "emotion": self.emotion.state.label(),
            "valence": round(self.emotion.state.valence, 2),
            "arousal": round(self.emotion.state.arousal, 2),
            "style": decision.style,
            "audio_path": audio_path,
        }


def _repl(avatar: Avatar, use_tts: bool = False) -> None:
    print(f"===== {config.avatar_name} 已上线（输入 quit 退出）=====")
    print("（提示：说「我叫xxx」会写入长期记忆，之后可验证它记得你）\n")
    while True:
        try:
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        if text.lower() in ("quit", "exit", "q"):
            break
        result = avatar.respond(text, use_tts=use_tts)
        print(f"{config.avatar_name} > {result['reply']}")
        print(
            f"    [情绪 {result['emotion']} v={result['valence']} a={result['arousal']}"
            f" · 风格 {result['style']}]"
        )
        if result["audio_path"]:
            print(f"    [语音 {result['audio_path']}]")
    avatar.memory.close()
    print("再见～")


def main() -> None:
    """CLI 入口：`python -m avatar.main [--tts]`。"""
    use_tts = "--tts" in sys.argv
    avatar = Avatar()
    _repl(avatar, use_tts=use_tts)


if __name__ == "__main__":
    main()

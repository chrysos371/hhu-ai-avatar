# DOC-003 · README 宣称语音全链路已编排但代码未接通

- **等级：** P2 · 中（产品能力表述超出集成状态）
- **状态：** 静态调用路径确认
- **置信度：** 高

## 摘要

README 将“ASR → LLM → TTS → 口型参数”称为全链路闭环和“一站式编排”。当前系统确有这些模块/算法，但 Avatar 主流程不能从音频输入开始，也不会从 TTS 输出生成并返回口型参数。该表述将组件存在误写成端到端已接通。

## 证据

- README 第 28 行：声称“一站式编排”。README 架构图也把用户语音、ASR、TTS、口型串为产品链路。
- `src/avatar/main.py` 初始化 `self.asr`、`self.lipsync`；`respond()` 接收用户文本，仓库中没有调用 `self.asr.transcribe()` 的主流程路径。
- `respond()` 可选调用 TTS 并返回 `audio_path`，但没有调用 `self.lipsync.analyze()` 或返回口型帧。
- `src/avatar/mouth/tts.py` 输出 MP3；当前这条主流程没有把 MP3 解码为口型分析样本。
- 项目现状报告已经说明“产品叙事领先于端到端证据”，并建议修正 README/AGENTS；此处确认该建议仍需落实。

## 影响

使用者按 README 预期无法把语音直接交给 `Avatar` 并获得同步的音频与口型序列。项目演示和功能验收容易把独立模块测试误认为全链路完成。

## 修订建议

将能力描述改成“文本对话主流程已集成；ASR、TTS、口型组件分别存在；语音端到端仍待集成和验收”。待集成后再以接口示例、支持格式和验收记录更新链路图。

## 参考

- [README](../../../README.md)
- [Avatar 编排](../../../src/avatar/main.py)
- [ASR](../../../src/avatar/ears/asr.py)
- [TTS](../../../src/avatar/mouth/tts.py)
- [口型分析](../../../src/avatar/face/lipsync.py)
- [项目现状与推进策略](../../../docs/进展报告/2026-11-10_项目现状与推进策略.md)
- [AUD-004](../../2026-11-10-completed-components/issues/AUD-004_语音模块未接入Avatar端到端主流程.md)

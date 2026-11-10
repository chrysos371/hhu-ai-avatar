# AUD-004 · ASR、TTS 与口型模块未接入端到端主流程

- **等级：** P2 · 中（功能完整性 / 文档准确性）
- **类别：** 模块集成缺口
- **状态：** 静态调用图确认；未运行 ASR/TTS 设备链路
- **置信度：** 高

## 摘要

语音识别、语音合成、口型分析类均已实现并在项目文档中列为已完成模块，但当前 `Avatar.respond()` 主流程只接受文本；ASR 实例没有被调用，TTS 只生成 MP3 文件，口型引擎没有消费生成音频，也没有把口型帧返回给调用者。因此项目具备独立组件，不具备 README 所表达的 ASR→LLM→TTS→口型参数端到端闭环。

## 证据

- `src/avatar/main.py:68-71` 初始化 `self.asr` 与 `self.lipsync`。
- 仓库全文中 `transcribe()` 只出现在 ASR 定义；没有调用点。
- `src/avatar/main.py:354-360` 的 `respond()` 输入类型是文本字符串，没有音频输入路径或音频 bytes 参数。
- `src/avatar/main.py:425-430` 只调用 `self.tts.synthesize()`；返回字段 `audio_path` 之外没有口型序列。
- `src/avatar/face/lipsync.py` 只有独立 `analyze(samples, sr)` API；没有调用者将 TTS 输出解码为样本后传入。
- `EdgeTTSEngine` 输出 MP3；`utils/audio.py` 的标准库加载路径只支持 WAV，任意格式需可选 `librosa`，当前编排没有调用 `load_audio()`。
- `tests/test_lipsync.py` 只对合成正弦波测试独立分析，不验证真实 TTS 音频格式、帧输出或同步效果。
- README 将核心特性描述为“全链路闭环：ASR → LLM → TTS → 口型参数”；AGENTS 也将 M3/M4 标成完成，但 `docs/项目进度.md` 的历史部分曾明确记载这些模块未接通主流程。当前代码仍符合“组件存在、系统链路未接通”的状态。

## 影响

开发者按文档调用 `Avatar.respond()`，不能提交音频并获得转写，也不能从回复中取得口型时间序列。演示端需要自行拼接隐含步骤，而 MP3 到样本的转换依赖还未集成。由独立单元测试通过，不能推出语音闭环已工作。

## 建议

1. 明确区分“组件实现”与“端到端接入”，先修正 README/AGENTS 的能力表述。
2. 定义稳定语音输入接口（音频格式、采样率、通道数、超时与转写失败状态），再明确文本输入的降级方式。
3. 为 TTS 输出定义可供口型分析的解码路径或直接支持 WAV/PCM；显式返回口型帧及其时间基准。
4. 增加端到端离线验收：固定输入音频→转写→回复→合成音频→逐帧口型；分别报告转写、音频与同步指标。
5. 明确呈现端协议与播放时钟；脱离真实播放时间生成的帧序列不能自动称为实时口型同步。

## 验收建议

- 公共 API 可完成音频输入与文本输入两条路径。
- 回复音频和口型帧来自同一次生成，帧时间单位/起点/采样率清晰。
- 无 ASR 或 TTS 依赖时，返回明确降级状态，不静默假装完成语音链路。
- 目标平台至少做一次真实设备或录音文件端到端复现。

## 参考位置

- [Avatar 编排](../../../src/avatar/main.py)
- [ASR 接口](../../../src/avatar/ears/asr.py)
- [TTS 接口](../../../src/avatar/mouth/tts.py)
- [口型分析](../../../src/avatar/face/lipsync.py)
- [音频加载](../../../src/avatar/utils/audio.py)
- [口型单元测试](../../../tests/test_lipsync.py)
- [项目 README](../../../README.md)

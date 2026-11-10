# AGENTS.md

> 本文件为在此仓库工作的 AI 编码助手（Codex / Claude Code 等）提供项目上下文。
> 开始任何改动前，请先读完本文件，并阅读 `docs/技术选型与模块重写计划.md`。

## 2026-11-10 当前状态（优先于下文早期快照）

当前文本后台、来源/版本记忆、可选 Ollama/NumPy 语义混合召回、知识工具与 Mission Control 管理台已实现。本轮 Python 全量 589 passed、1 个可选 torch 测试跳过；前端组件 25 passed、浏览器离线 9 passed、真实 TTS 浏览器 1 passed。既往训练环境 CPU 专项 14 passed。早期“仅口型有测试”“向量接口为空”的描述已经过时。

网页已接按需 TTS、鉴权音频、播放/停止、按播放时钟驱动的 SVG 最小形象、AudioWorklet 麦克风 PCM WAV 采集与可选本机识别回填。真实 TTS/MP3 解码已验证；ASR 默认关闭，真实本机模型、物理设备与中文口型准确率待验收，不得宣称正式数字人链路已全部验收。运行约定见 docs/网页语音与最小形象.md。

既往 23 条/12 步 LoRA 已完成流程试训但未证明收益，不部署；新公开数据 200/50 是自动筛选实验材料，4B/14B/32B 对照与回复端风格训练管线已准备，真实新训练和大模型对照尚未启动。任务/交付/事实提示实验开关保持默认关闭。详见 `docs/项目进度.md` 和 `experiments/style/README.md`。以下旧模块快照保留作历史背景。

## 一、项目是什么

河海大学大学生创新训练项目（大创）「**基于人工智能的综合性虚拟形象探索与应用**」，
一年期。目标是打造一个带「**记忆**」和「**情感**」的 AI 虚拟形象底层认知框架，
长期目标是打通 **听 → 思 → 演 → 记** 全链路；当前文本后台、真实网页 TTS 与 SVG 最小形象已接入，可选语音输入已串接，真实 ASR 和目标设备端到端体验仍待验收。

参考实现：`moeru-ai/airi`（Neuro-sama 复刻，MIT，TypeScript/Web 全栈）。
本项目策略：**参考 AIRI 的算法与设计思路，用 Python 重新实现，并在其短板处做差异化。**

## 二、核心创新点（改动前务必理解，不要破坏其可解释性）

1. **两级记忆**：短期（会话窗口 `deque`）+ 长期（SQLite，翻译自 AIRI schema）
2. **PAD 情绪模型 + 行为决策树**：AIRI 完全没有的能力，是本项目最大创新点
3. **中文口型同步**：共振峰 F1/F2 定位元音（AIRI 只支持英语 AEIOU）
4. **LLM 驱动的记忆抽取与情绪分析**：替换了早期正则规则（见最新提交）

## 三、架构与代码结构

四层模块 + 贯穿全链路的情绪状态，全部位于 `src/avatar/`：

| 层 | 文件 | 职责 | 选型 |
|---|---|---|---|
| 听 | `ears/asr.py` | 音频 → 文本 | FunASR（中文强），可降级 `TextInputEngine` |
| 思 | `brain/llm.py` | LLM 对话 | OpenAI 兼容接口 |
| 记 | `brain/memory.py` | 两级记忆与混合检索 | SQLite（标准库 `sqlite3`），关键词默认可用；可选 Ollama embedding + NumPy 语义召回 |
| 情 | `brain/emotion.py` | 情绪状态 + 决策树 | 自研 PAD |
| 演·声 | `mouth/tts.py` | 文本 → 语音 | Edge-TTS |
| 演·口型 | `face/lipsync.py` | 语音 → 口型参数 | 自研共振峰 F1/F2 |
| 编排 | `main.py` | 文本对话主流程与音频文件 API | — |
| 配置 | `config.py` | 读 `.env` | — |

## 四、当前代码状态（按集成层次区分）

`python -m avatar.main` 启动文本交互流程；无 LLM key 时使用规则回复。ASR、TTS、口型有独立组件，`Avatar.respond_audio()` 可串接音频转写、文本响应、TTS 和逐帧口型分析；真实格式/服务验收需安装 ASR 与音频扩展。浏览器已有 SVG 最小渲染形象，正式 Live2D/Godot 渲染器未接入。

- `config.py`：全局配置，读 `.env`。LLM 默认 DeepSeek，avatar 名「小海」，persona「一个温柔又有点好奇心的AI伙伴」。
- `main.py`：`Avatar.respond()` 串起 短期记忆 → 认知分析(LLM 驱动情绪+事实提取，失败回退规则) → 行为决策 → LLM 回复 → 短期记忆 → 可选 TTS。
- `brain/emotion.py`：`EmotionState`(valence/arousal)、情绪词典、否定词检测、意图分类(情感倾诉/提问/指令/闲聊)、`Decision`(风格/温度/语速/音调/口型强度)。
- `brain/memory.py`：当前事实与历史版本、来源证据、短期 deque + SQLite 持久化、关键词检索；配置 embedding 时支持向量索引与混合召回。默认不开启远程/本地语义服务。
- `brain/llm.py`、`ears/asr.py`、`mouth/tts.py`、`face/lipsync.py`、`utils/audio.py`：已实现。
- 测试：`tests/` 覆盖记忆、情绪、边界、Web、工具、音频等多个模块；运行 `python -m pytest tests/ -q` 检查当前分支，不在此固定测试数量。

## 五、技术选型与依赖

| 模块 | 方案 | 备注 |
|---|---|---|
| LLM | OpenAI 兼容 SDK（`base_url` + `api_key`） | 一套通吃 DeepSeek/通义/Kimi/本地 Ollama |
| ASR | FunASR | 较重；`faster-whisper` 为可选替代，需显式注入实现 |
| TTS | Edge-TTS | 免费、中文自然、零部署 |
| 记忆 | SQLite | 关键词默认可用；可选 Ollama embedding + NumPy 混合召回 |
| 情绪 | 自研 PAD + 决策树 | AIRI 空白区 |
| 口型 | 自研共振峰 F1/F2 | 可扩展中文声调 |

- Python：`requires-python >= 3.10`；按声明范围保持兼容，并在可用环境中做版本验证
- 核心依赖：`numpy`、`edge-tts`、`openai`、`python-dotenv`
- 可选依赖（`requirements-optional.txt`）：`funasr` 或 `faster-whisper`（ASR）、`librosa` / `soundfile`（音频扩展，通常需 ffmpeg）；MCP/Web 依赖见 `requirements-web.txt`
- 构建：setuptools，包在 `src/` 下；`pyproject.toml` 提供 extras，仓库同时保留 requirements 文件供安装使用

## 六、开发进度

- [x] M1 项目骨架 + 记忆模块
- [x] M2 情绪模型 + 决策树 + LLM 接入
- [x] ASR / TTS / 口型独立组件
- [x] 音频文件输入与回复口型帧 API 初步串接（真实环境验收待完成）
- [x] 网页播放时钟与 SVG 最小形象、可选麦克风/识别输入
- [ ] 真实 ASR、中文口型校准、正式渲染框架与目标设备端到端验收
- [x] 可选语义向量召回（当前 SQLite 存储；默认不开启）
- [ ] 中文口型声调映射

## 七、下一步工作（按优先级）

1. **真实输入验收**：在目标设备配置已有本机 ASR 模型，记录中文识别、静音/噪声、物理麦克风与权限拒绝的结果；不自动发送识别文本。
2. **音画与嘴型量化**：先用独立语料校准 LPC/元音/静音和播放延迟，再依据结果扩展中文声调映射。
3. **低延迟交互**：流式模型输出、分段 TTS 和真正上游取消/打断，避免重复记忆或过时音频。
4. **M5 正式渲染适配**：已有 JSON 时间轴与 SVG 最小接收示例，后续 Live2D/Godot/VRM 复用协议。
5. **评测与健壮性**：独立真实对话评测、多日运行与进程管理，结合 `docs/进展报告/` 中的验收门槛推进。

## 八、技术约定与注意事项

- 情绪决策树、中文口型、LLM 驱动记忆抽取是**项目差异化核心**，重构时保持可解释、可对照 AIRI。
- 环境变量/密钥走 `.env`，不要提交真实 key（见 `config.py` 的默认值）。
- 记忆库文件在 `data/` 目录，已被 gitignore。
- 新增可选重依赖（如 FunASR）应放 `requirements-optional.txt`，不要塞进核心依赖。

## 九、常用命令

```bash
# 交互式 demo（加 --tts 开启语音合成）
python -m avatar.main [--tts]

# 运行测试
python -m pytest tests/ -v

# 安装依赖
pip install -r requirements.txt              # 核心
pip install -r requirements-optional.txt     # ASR / 音频扩展
```

## 十、关键文档

- `docs/技术选型与模块重写计划.md` —— 初始技术方案，部分细节已过时；当前状态以 README、`docs/backend.md` 和 `docs/进展报告/` 为准。
- `README.md` —— 项目门面（与 GitHub 同步）。

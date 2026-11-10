# AGENTS.md

> 本文件为在此仓库工作的 AI 编码助手（Codex / Claude Code 等）提供项目上下文。
> 开始任何改动前，请先读完本文件，并阅读 `docs/技术选型与模块重写计划.md`。

## 2026-11-11 第三轮进行中（优先）

第三轮推进见 `docs/进展报告/2026-11-10-G2交互循环/cycle-03/进展.md`。最近已归档全量822 passed/1 skipped；后续模板、来源屏障和网页实验入口另做专项，尚未冒称当前HEAD全面验收。4B/14B结构化初审校准失败，不接入默认回复。原文槽位方案机械分全过但有重复/编造，已保留失败，改用用户来源完整标记模板v2继续验证。

新 `--task-delivery-check --literal-composition` 为默认关闭的实验入口，需JSON schema；任务从隐私有效短期窗口重建，不重放历史动作。成功组合明示llm_literal_composition，通用语义Verifier仍False，不自动切换模型或开启其他候选。下文是第二轮已归档快照，各次实验分数不能混为当前模型能力。

## 2026-11-11 第二轮归档快照

当前文本后台、来源/版本记忆、知识工具与九页管理台已实现；G2增加流式回合、SDK/TTS取消、请求去重、分段播放与打断。第一轮9项审计整改通过；第二轮18条单项记录及实测见 `docs/进展报告/2026-11-10-G2交互循环/cycle-02/审计/系统审计与推进报告.md` 与同名HTML。最新Python746 passed/1 skipped、前端33 passed、离线浏览器15 passed/2 skipped，可选真实服务另跑，不能把测试数量当陪伴质量。

真实CPU/GPU ASR已在27条合成及固定40条公开朗读上验证；人声CPU/GPU CER7.23%/6.88%。真人端点对照CER6.53%→9.88%且两条截断，自动端点默认关闭，手动结束后检查草稿再发送；物理麦克风与自由对话人声未验收。真实ASR→4B/14B→TTS/SVG已分别实跑，不外推真实设备或音画自然度。

4B和14B固定Q4_K_M均已完整下载、哈希核对和真实对照。身份提示 `subject_prompt_enabled` 与资料约束 `profile_grounding_enabled` 继续默认False。资料查询/保守声明确认是有来源的框架路径，4B52/52检查含67条资料回复、25条原生生成和1条规则；追加12对话4B11/12、14B12/12，不是独立语义批准。G2C2-009归属与016一般生成身体边界仍开放；通用语义Verifier available=False。新候选自评误路由和检查期间取消漏洞已先复现后修复；范围限制见单项记录。

既往23条/12步LoRA流程试训未证明收益，不部署；200/50风格候选须按扩展保护集重筛，新风格训练和32B对照尚未启动。任务/交付/事实提示实验开关也继续默认关闭。正式渲染、中文元音校准、多日使用未验收。

GPU按每次实际余量、利用率、显式可见索引/UUID与同组约束选择，最多同组四张；6–7仅是此前有余量，不固定后续卡号。最后实跑GPU4和6，两个自建模型进程已退出；不终止他人进程。实验不设墙钟截止，保留固定样本、轮数、token上限与早停。以下旧模块快照保留作历史背景。

## 一、项目是什么

河海大学大学生创新训练项目（大创）「**基于人工智能的综合性虚拟形象探索与应用**」，
一年期。目标是打造一个带「**记忆**」和「**情感**」的 AI 虚拟形象底层认知框架，
长期目标是打通 **听 → 思 → 演 → 记** 全链路；当前文本后台、真实网页 TTS 与 SVG 最小形象已接入，可选语音输入已串接，自由对话人声与物理设备端到端体验仍待验收。

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
| ASR | FunASR | 较重；`faster-whisper` 可由 Web CLI 显式启用 |
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
- [ ] 自由对话/物理设备 ASR、中文口型校准、正式渲染框架与目标设备端到端验收
- [x] 可选语义向量召回（当前 SQLite 存储；默认不开启）
- [ ] 中文口型声调映射

## 七、下一步工作（按优先级）

1. **真实输入验收**：已有公开朗读子集与自动端点，继续真实对话人声与物理麦克风；在目标设备配置本机 ASR 模型，记录中文识别、静音/噪声、物理麦克风与权限拒绝的结果；不自动发送识别文本。
2. **音画与嘴型量化**：先用独立语料校准 LPC/元音/静音和播放延迟，再依据结果扩展中文声调映射。
3. **真实模型交互**：流式/分段/取消已实现并通过受控实验；继续真实模型质量、工具阶段取消与长时运行验证。
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

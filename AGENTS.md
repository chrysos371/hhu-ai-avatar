# AGENTS.md

> 在此仓库开始改动前读完本文件及 [技术选型与模块重写计划](docs/技术选型与模块重写计划.md)。技术计划是初始设计，当前实现与验收以 [README](README.md)、[后端说明](docs/backend.md) 和最新周期报告为准。

## 当前工作约定

- 项目为 `/data/Users/zrh/repo/hhu-ai-avatar`，新命令/记录使用该路径；写入前确认 `/data` 已挂载。sqs/TabPFN 的目录约定不用于此 zrh 项目。
- 用户已设置持续远期目标，本会话 Goal active。自主推进研究、必要实验、工程优化和系统审计，无需用户驻守；每轮先登记指标/输入，再实验、审计、逐项修复/复测、归档并进入下一轮。阶段完成不等于整体目标完成；Goal 实际状态以目标工具为准。
- Git 作者统一 `spinner-bot <langxibielangle@qq.com>`；小步及时提交，不积压已完成改动。远程推送串行等待上一轮完成，使用用户指定密钥 `/root/Users/zrh/.ssh/id_ed25519_github`，`IdentitiesOnly=yes`；禁止擅自强推/改写历史。活动实验总文件结束后封存，已关闭组及时独立提交。
- GPU按启动时实际空闲显存/利用率与UUID选择，不固定6–7；最多使用同一组4张空闲卡。当前协议单个自建提供方串行；不停止他人进程。核验实际GPU分配与模型身份，拒绝静默CPU替代。
- 实验不设整轮墙钟截止，保留固定轮数和早停规则；单请求、就绪、清理超时属于工程边界。先预登记，全部执行输入提交后再冻结，并以Git历史字节核验；冻结输入运行中不改，必要修正先保留失败/退役原版本。
- 所有结论绑定实验数据、来源/模型/配置/实际请求与版本；保留原始失败和负控，不筛选有利重复，不在同批题上调优后冒称独立通过。采证总用时不能当纯推理速度；独立复核程序不等于独立人评。
- 审计在独立周期目录中进行，保留计划/进展、单项问题文档、原始证据、MD与HTML报告及显示/链接检查。旧封存清单及其文件不回写；新发现写新周期。候选未获门槛批准保持隔离，默认产品、实模语义、真人/物理设备与多日验收分开陈述。

## 当前阶段（2026-11-12）

- **C33进行中**：[计划](docs/进展报告/2026-11-10-G2交互循环/cycle-33/计划.md) / [进展](docs/进展报告/2026-11-10-G2交互循环/cycle-33/进展.md)。全部12旧白盒隐含线索+4中性、3重复，每模型48共享组/192应用回合/144OS；准备仅真实生成一次后SQLite备份两库，各新OS/初始PAD0/同四角色，当前分析vs原封C31候选，仅probe不同。实际native386−skip(0..48)，32B只受同冻4B工程/来源/清理门槛，不按情绪或答案筛选。
- C33冻结 **341项**，source_ref `be2bfb8ec5d37e6bbb0ff02ebe2af9bb41d14f1c`，SHA `8037d5abea7e9f5cfaa2b4ad11bc9d2521b2edc807b3af20d51eec39f11f9930`。8 CPU共享/委托/删除隔离控制和3真实进程早拒绝通过；两模型各192回合/144OS/48对完成：4B362native/24skip/用户观测差异0，32B368native/18skip/差异6；原文各48/48相同、严格代号两臂各48/48。384回合/288OS/730native均独立绑定且退出0，具体进度以原始文件为准。复用已封C32 logical_reset提供方/54运行文件身份，reset不保证正确性；不编辑助手文本强制skip，不把模型非0当情绪真值，用户只要代号不强求安慰文字，无一般语义或速度批准。
- **C32已封93项**：提交 `7de1a22`，清单SHA `82151051b992f5e284a73cf992dfd5a33154ec44503525477895aaf761b665a9`。旧C3–C32不回写。[C32系统报告](docs/进展报告/2026-11-10-G2交互循环/cycle-32/审计/系统审计与推进报告.md)：两模型共210原生调用/36末次，6提供方清理，20控制与29旧封核验过；32B reuse两链三对不同，两种reset同错93，未得数值/格式修复或根因批准。C31候选继续隔离。
- 默认产品未改：完整Python `1769 passed / 1 skipped` @`24f4529`、552输入；默认浏览器 `15 passed / 16 optional skipped` @`d631302`、190输入仍C29历史执行，不能冒称本轮重跑。前端153仍C24，`index-CYNSx0Ec.js`未变。C31-002隐含情绪、003复现性、004数值/C30格式、C19-001通用能力P1、真人设备/多日仍开放。
- [远期目标与验收路线](docs/进展报告/2026-11-10-G2交互循环/远期目标与验收路线.md)。历史中间交接移到[完整原文快照](docs/进展报告/2026-11-10-G2交互循环/cycle-33/审计/工作目录/002-工作约定去重/AGENTS-整理前.md)，原Git与SHA见[整理前测量](docs/进展报告/2026-11-10-G2交互循环/cycle-33/审计/工作目录/002-工作约定去重/整理前测量.json)；快照中的旧相对路径按原根目录位置解释。以下十节项目参考原字节保留，具体进度仍以上述最新证据为准。

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

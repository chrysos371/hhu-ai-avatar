# AGENTS.md

> 本文件为在此仓库工作的 AI 编码助手（Codex / Claude Code 等）提供项目上下文。
> 开始任何改动前，请先读完本文件，并阅读 `docs/技术选型与模块重写计划.md`。

## 2026-11-10 当前状态（优先于下文早期快照）

当前文本后台、来源/版本记忆、可选 Ollama/NumPy 语义混合召回、知识工具与 Mission Control 管理台（含 QQ 会话管理）已实现。Python 全量 606 passed、3 个可选测试（torch/官方 QQ SDK/OneBot SDK）跳过；训练环境 CPU 专项 14 passed。早期“仅口型有测试”“向量接口为空”的描述已经过时。

ASR/TTS 和口型模块存在，但网页语音闭环、主流程口型联动和角色渲染未完成；README 不得宣称完整数字人链路已跑通。当前优先补网页语音播放/停止、口型时间轴与最小形象，再接麦克风。

既往 23 条/12 步 LoRA 已完成流程试训但未证明收益，不部署；新公开数据 200/50 是自动筛选实验材料，4B/14B/32B 对照与回复端风格训练管线已准备，新4B试训及四组开发对照已完成（实际48条、12步），未证明质量增益；14B/32B真实对照尚未启动。任务/交付/事实提示实验开关保持默认关闭。详见 `docs/项目进度.md` 和 `experiments/style/README.md`。以下旧模块快照保留作历史背景。

QQ 官方文本接口在 `src/avatar/channels/qq/`，独立服务、私聊/群内@、每机器人/用户/群隔离存储；不开放管理 API，默认不启动、不连接、不发送。可选 SDK 专项 14 项通过，当前无凭据、未实机联调。用法见 `docs/QQ接入.md`。

## 一、项目是什么

河海大学大学生创新训练项目（大创）「**基于人工智能的综合性虚拟形象探索与应用**」，
一年期。目标是打造一个带「**记忆**」和「**情感**」的 AI 虚拟形象底层认知框架，
打通 **听 → 思 → 演 → 记** 全链路。

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
| 记 | `brain/memory.py` | 两级记忆 | SQLite（标准库 `sqlite3`），预留向量接口 |
| 情 | `brain/emotion.py` | 情绪状态 + 决策树 | 自研 PAD |
| 演·声 | `mouth/tts.py` | 文本 → 语音 | Edge-TTS |
| 演·口型 | `face/lipsync.py` | 语音 → 口型参数 | 自研共振峰 F1/F2 |
| 编排 | `main.py` | 全链路 `Avatar` 类 | — |
| 配置 | `config.py` | 读 `.env` | — |

## 四、当前代码状态（已实现，可跑通）

所有核心模块均已实现，`python -m avatar.main` 可启动交互式对话；
无 LLM key 时也会回退到规则版，跑通「情绪 + 记忆 + 决策」全链路。

- `config.py`：全局配置，读 `.env`。LLM 默认 DeepSeek，avatar 名「小海」，persona「一个温柔又有点好奇心的AI伙伴」。
- `main.py`：`Avatar.respond()` 串起 短期记忆 → 认知分析(LLM 驱动情绪+事实提取，失败回退规则) → 行为决策 → LLM 回复 → 短期记忆 → 可选 TTS。
- `brain/emotion.py`：`EmotionState`(valence/arousal)、情绪词典、否定词检测、意图分类(情感倾诉/提问/指令/闲聊)、`Decision`(风格/温度/语速/音调/口型强度)。
- `brain/memory.py`：5 张表(翻译自 AIRI schema)、短期 deque + 长期持久化、关键词+停用词检索、`embed()`/`vector_search()` 预留。
- `brain/llm.py`、`ears/asr.py`、`mouth/tts.py`、`face/lipsync.py`、`utils/audio.py`：已实现。
- 测试：`tests/test_lipsync.py`（pytest，目前仅口型有测试）。

## 五、技术选型与依赖

| 模块 | 方案 | 备注 |
|---|---|---|
| LLM | OpenAI 兼容 SDK（`base_url` + `api_key`） | 一套通吃 DeepSeek/通义/Kimi/本地 Ollama |
| ASR | FunASR | 较重，可降级 `faster-whisper` |
| TTS | Edge-TTS | 免费、中文自然、零部署 |
| 记忆 | SQLite | 预留 `content_vector` BLOB，后续接 pgvector/Chroma |
| 情绪 | 自研 PAD + 决策树 | AIRI 空白区 |
| 口型 | 自研共振峰 F1/F2 | 可扩展中文声调 |

- Python：`requires-python >= 3.10`（当前环境实际运行 3.14）
- 核心依赖：`numpy`、`edge-tts`、`openai`、`python-dotenv`
- 可选依赖（`requirements-optional.txt`）：`funasr` / `faster-whisper`（ASR）、`librosa` / `soundfile`（音频扩展，需 ffmpeg）
- 构建：setuptools，包在 `src/` 下；依赖分核心 `requirements.txt` 与可选 `requirements-optional.txt`

## 六、开发进度

- [x] M1 项目骨架 + 记忆模块
- [x] M2 情绪模型 + 决策树 + LLM 接入
- [x] M3 TTS + ASR 接入
- [x] M4 口型驱动
- [ ] M5 全链路 demo + 测试 + 文档
- [ ] 向量检索（embedding → pgvector / Chroma）
- [ ] 中文口型声调映射

## 七、下一步工作（按优先级）

1. **向量检索**（代码已预留接口，改动最内聚）
   - `brain/memory.py` 的 `embed()` 目前返回 `None`，`vector_search()` 退化为按重要度。
   - 实现真实 embedding（本地 sentence-transformers 或 OpenAI embedding 接口），
     让 `recall()` 支持语义检索路径；`content_vector` 列已预留 BLOB。
2. **中文口型声调映射**
   - `face/lipsync.py` 目前基于元音 F1/F2，加入声调（一声/二声/三声/四声）对嘴型动态的影响。
3. **M5 场景接入（Live2D / Godot）**
   - Python 不做实时渲染。现实做法：把口型参数序列（`mouth_open` + `vowel`）通过
     WebSocket / JSON 文件 / 标准输出流暴露给渲染端，先做「输出协议 + 最小接收示例」。
4. **测试与健壮性**（可选）
   - 目前仅 `test_lipsync.py` 有测试，`memory` / `emotion` 无测试。
   - `main.py` 的 `_extract_json` 与 LLM JSON 解析可加强容错。

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

- `docs/技术选型与模块重写计划.md` —— 最完整的设计文档，**必读**，含 AIRI 对照表与各模块详细设计。
- `README.md` —— 项目门面（与 GitHub 同步）。

普通 QQ 号是当前默认接入：`./scripts/qq.sh --check|--smoke|--run` 使用 OneBot 11 正向本机 WebSocket，代码在 `onebot.py`/`onebot_app.py`，账号与 token 走 AVATAR_ONEBOT_*；官方接口改用 `--transport official`。两种数据隔离。尚未启动 NapCat 或登录真实账号，不能宣称真实 QQ 已打通。

2026-11-10 QQ 联调更新：NapCat 已真实登录、OneBot 与 Avatar 已连接；初次规则回复问题已定位为缺少模型配置，现接本机 CPU llama.cpp / Qwen3-4B-Q4_K_M（18081），真实引擎三条生成验证通过。模型故障明确提示，不能把 `--check` 配置字段当作在线探测。尚无开机自启。

QQ 运行优化：`--health` 可只读验证本机 OneBot 账号在线、模型列表、Avatar 实例锁；不发消息、不生成、不访问云端。QQ 固定安全提示前置以复用缓存，动态策略后置；降级回复不再注入后续上下文，历史审计保留。每上下文 qq_turn_metrics 最多保留 1000 条耗时/降级指标，不含正文或凭据。

2026-11-10 QQ 后台接入：`management.py` 只读共享后台已确认人设/知识，不共享主库个人记忆；`admin_api.py` 经现有本机鉴权管理 OneBot 会话记忆草案/确认/审计/处理记录，前端 `/qq`（十个页面）。QQ 明确查询走 `tools.py` 只读白名单（搜索/网页/天气/已确认知识与独立 QQ 目录），不开放提醒写入或管理权限；不把历史/画像发给工具规划。生产知识库当前空，未植入测试资料。全量 597 passed、3 skipped；QQ 含 SDK 联合 48 passed；前端 19 passed、浏览器 6 passed，构建/类型/lint 通过。QQ 与后台服务已重启，旧管理令牌保留。

后台并发修复：管理服务改为最多16个并发连接、空闲读取10秒超时，对话独立串行锁；MemoryStore 的同进程同库事务/初始化使用共享可重入锁，OperationService 确认在 SQLite BEGIN IMMEDIATE 前取得该锁，避免锁顺序反转。跨进程仍由 SQLite 事务保证。全量600 passed、3 skipped。本机并发页面/管理API实测6–36ms，保持回环监听和原令牌。

2026-11-10 多角色原型：网页 `/characters` 角色馆（共十一个页面），14 张自定义人设卡、8 套本地社区立绘；每角色独立 persona.db 与 conversation/memory.db，复用 AvatarEngine 的分析/安全/记忆/状态。`persona_db` 只覆盖角色人设，公共知识仍读主库且不带私人记忆。编辑需草案确认，图片只存 gitignore 的 data/characters 并保留来源。模型统一本地4B，QQ角色切换和动画/语音未做。全量605 passed、3 skipped；前端20、浏览器7通过，真实4B记忆隔离验证通过。详见 docs/多角色数字人.md。

2026-11-10 GPU训练：0号A100上完成pilot-002的12步回复端LoRA，200条可用但实际抽48条、开发50条，28.75秒（含末尾验证/探针），PyTorch峰值8.16GiB；独立重载logits差0、文本一致。新增评测 --include-raw 后四组20场景×60轮全部完成，分析适配器泄漏0；裸模型3轮截断（2场景），三个后台组机械失败0，但LoRA有改写变解释/多余追问等抽查回归，质量仍未批准、不部署。全量606/3skip、训练CPU15通过。证据data/style-lab/style-train-20261110-01与style-regression-20261110-01，详见docs/2026-11-10-4B-LoRA试训与四组对照.md。GPU已释放。结束检查发现QQ登录失效，模型服务正常；没有重登或发消息。

2026-11-11 公共对话第一版：会话服务在 `src/avatar/conversation/`，QQ AvatarEngine为兼容导出，角色馆直接使用ConversationService；网页和渠道统一execute_turn与schema_version=1记录，原网页生命周期保留。模型profiles通过AVATAR_MODEL_PROFILES配置、密钥只引用env；角色独立model.json，接口只显示已配置服务，不保证在线。共享事实仅本机角色馆local-owner手动授权，默认不共享，支持编辑/撤销/撤回与审计；关系和经历继续隔离，未做跨QQ/网页身份绑定。管理台已更新，QQ未重登/未发送。619核心通过/3skip，专项7通过，前端20/浏览器8通过。14B下载评测改用独立同源码快照hhu-ai-avatar-baseline14b，切勿编辑该快照或把其结果当作新架构回归；原运行目录不变。


2026-11-11 最新模型对照（覆盖旧“14B未启动/下载中”记录）：14B BF16原始权重及固定索引核验完成。冻结旧版与d86eaad整合版均完成20场景裸/后台对照，整合两模型重新跑；新生成360轮，旧4B另复用。整合4B/14B后台轮耗时中位2.04/2.25秒、峰值7.68/27.74GiB，机械失败均0但AI完整后台审阅仍有归属/交付/排他问题；14B无全面稳定增益，保留4B部署、14B候选，不训练不自动上线。不是人工或独立语义批准，也不是长期关系验收。原始报告不改，标准中位/P95另重算；后续分片锁索引与分位数算法已修复并同步整合分支。GPU评测退出、显存释放。详见docs/2026-11-11-14B底模对照与选择.md。


2026-11-11 最新底模复核（优先于上条“保留4B、不训练”的建议）：已完整重审四组240轮，新增固定8场景共32轮，源码/生成条件一致、无规则或降级。14B裸模型及若干关键关系/归属场景更有利，但有材料编造和新预算3组/105元算错的明确反例；4B预算2组/90元对但格式多行，错误分维度记录，不做等权总分。开发优先14B，4B基线/回退；线上不自动切换，14B受控小训不因这次对照被否定，也不保证有收益。AI已见数据、补充同家族小样本，非独立人审/泛化批准。最新报告docs/2026-11-11-4B与14B复核比较.md，证据主目录data/style-lab/model-reassessment-20261111-01；GPU6/7已释放，无训练/QQ外发/线上变更。

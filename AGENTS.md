# AGENTS.md

> 本文件为在此仓库工作的 AI 编码助手（Codex / Claude Code 等）提供项目上下文。
> 开始任何改动前，请先读完本文件，并阅读 `docs/技术选型与模块重写计划.md`。

## 2026-11-10 当前状态（优先于下文早期快照）

当前文本后台、来源/版本记忆、可选 Ollama/NumPy 语义混合召回、知识工具与 Mission Control 管理台已实现。Python 全量 546 passed、1 个可选 torch 测试跳过；训练环境 CPU 专项 14 passed。早期“仅口型有测试”“向量接口为空”的描述已经过时。

ASR/TTS 和口型模块存在，但网页语音闭环、主流程口型联动和角色渲染未完成；README 不得宣称完整数字人链路已跑通。当前优先补网页语音播放/停止、口型时间轴与最小形象，再接麦克风。

既往 23 条/12 步 LoRA 已完成流程试训但未证明收益，不部署；新公开数据 200/50 是自动筛选实验材料，4B/14B/32B 对照与回复端风格训练管线已准备，真实新训练和大模型对照尚未启动。任务/交付/事实提示实验开关保持默认关闭。详见 `docs/项目进度.md` 和 `experiments/style/README.md`。以下旧模块快照保留作历史背景。

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

# hhu-ai-avatar

> 基于人工智能的综合性虚拟形象探索与应用 —— 带记忆与情感的 AI 虚拟形象底座
>
> 河海大学大学生创新训练项目 · 参考 [moeru-ai/airi](https://github.com/moeru-ai/airi) 的算法思路，用 Python 重新实现

受顶流 AI 虚拟主播 **Neuro-sama** 启发，本项目不局限于「能说话的模型」，而是打造一套让虚拟形象拥有**「过去」（长期记忆）**与**「心情」（情绪状态）**的底层认知框架，打通 **听 → 思 → 演 → 记** 全链路闭环，解决现有虚拟主播「金鱼脑」（对话失忆）与情感生硬两大痛点。

## 核心特性

### 2026-11-01 后端升级

- 当前记忆与历史版本分离：偏好变化、同句/唯一上轮对象的省略表达解析，旧值不再参与普通召回。
- 原文来源持久化：消息、会话、时间、证据；支持查看、手动纠错和删除相关版本。
- 用户情绪与角色状态独立，加入倾听、澄清、共情、建议、庆祝、回答六种策略及实际时间衰减。
- 可选本地 Ollama embedding + NumPy 混合召回；模型故障退回关键词，默认不开启语义服务。
- 扩展旧库迁移、回滚、删除、向量空间及跨会话/长对话测试，并提供真实本地模型评估脚本。

使用说明、CLI记忆命令和兼容性变化见 [docs/backend.md](docs/backend.md)。

新增本机记忆工作台：在仓库根目录运行 `python start_web.py`，打开终端提供的完整链接，即可对话、查看记忆来源与历史、纠错、删除、反馈召回不相关，以及管理明确创建的提醒。长对话增加带来源编号的摘要，可单独删除原话。时间衰减只影响排名，身份/偏好不自动遗忘。详见 [记忆工作台与提醒](docs/记忆工作台与提醒.md)；当前为单用户模式。

可选 [MCP 助手工具](docs/MCP联网工具.md)：安装 `requirements-web.txt` 后，可在统一工具管线中搜索网页、读取正文、查询天气、检索授权资料目录，以及查询/创建/取消本机 SQLite 提醒。每轮最多调用三次并返回状态轨迹。

- 🧠 **两级记忆**：短期会话窗口 + 长期持久化记忆（翻译自 AIRI 的 memory schema）
- 💗 **情绪引擎**：PAD 二维情绪模型 + 行为决策树（AIRI 空白区，本项目创新点）
- 👄 **自研口型同步**：共振峰 F1/F2 定位元音 → 张嘴幅度，可解释、可扩展中文口型
- 🎙️ **全链路闭环**：ASR → LLM → TTS → 口型参数，一站式编排
- 🔌 **可插拔**：LLM/TTS/ASR 均抽象为接口，OpenAI 兼容、FunASR、Edge-TTS 开箱即用

## 架构

```
用户 ──语音──▶ 听 ears/ASR ──▶ 思 brain/LLM ──▶ 演 mouth/TTS ──▶ 语音输出
                     │                ▲               face/口型 ──▶ 口型参数
                     │                │
                     └── 记 memory/ ──┘   （SQLite 两级记忆）
                         情 emotion/      （情绪状态贯穿全程）
```

| 层 | 模块 | 选型 |
|---|---|---|
| 听 | `ears/asr.py` | FunASR（中文强） |
| 思 | `brain/llm.py` | OpenAI 兼容（DeepSeek/通义/Kimi/本地） |
| 记 | `brain/memory.py` | SQLite（翻译自 AIRI schema） |
| 情 | `brain/emotion.py` | 自研 PAD + 决策树 |
| 演·声 | `mouth/tts.py` | Edge-TTS |
| 演·口型 | `face/lipsync.py` | 自研共振峰元音驱动 |

## 快速开始

### 1. 安装

```bash
# 核心依赖（记忆/情绪/口型/LLM/TTS）
pip install -r requirements.txt

# 可选：语音识别 + 音频格式扩展（需 ffmpeg）
pip install -r requirements-optional.txt
```

### 2. 配置

```bash
cp .env.example .env
# 编辑 .env 填入 LLM_API_KEY（不填也能跑 demo 的规则回复模式）
```

### 本地 Ollama（免费、离线，推荐）

没有云端 API key 时，用本地大模型：

```bash
# 1. 安装 Ollama
winget install --id Ollama.Ollama -e

# 2. 拉中文模型
ollama pull qwen2.5:7b

# 3. 配置 .env 指向本地 Ollama
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_API_KEY=ollama
# LLM_MODEL=qwen2.5:7b
```

首次加载模型约需 1~2 分钟，之后每轮推理 <1s（RTX 5070 8GB 可流畅跑 7B 模型）。

### 3. 运行交互式对话

```bash
# demo 模式（无需 LLM key，跑通情绪+记忆+决策）
python -m avatar.main

# 开启语音合成
python -m avatar.main --tts
```

> 需要先让 Python 找到包：`pip install -e .` 或 `export PYTHONPATH=src`（Windows PowerShell 用 `$env:PYTHONPATH="src"`）。

### 4. 跑测试

```bash
python -m pytest tests/ -v
```

## 使用示例

```python
from avatar.main import Avatar

ava = Avatar()
print(ava.respond("我叫小明，我喜欢打篮球"))  # 写入用户画像
print(ava.respond("你还记得我叫什么吗？"))      # 从长期记忆召回
print(ava.respond("我今天好难过……"))            # 触发安抚决策 + 情绪转负面
```

## 目录结构

```
src/avatar/
├── config.py        # 配置（.env）
├── main.py          # Avatar 编排 + CLI
├── ears/asr.py      # 听：FunASR
├── brain/llm.py     # 思：OpenAI 兼容 LLM
├── brain/memory.py  # 记：SQLite 两级记忆（翻译自 AIRI）
├── brain/emotion.py # 情：PAD 情绪 + 行为决策树
├── mouth/tts.py     # 演·声：Edge-TTS
├── face/lipsync.py  # 演·口型：自研共振峰元音驱动
└── utils/audio.py   # 音频加载/分帧
```

## 与 AIRI 的对照（参考 → 超越）

| AIRI 能力 | AIRI 实现 | 本项目 | 差异 |
|---|---|---|---|
| 口型同步 | wLipSync（英语 AEIOU） | 共振峰 F1/F2 元音驱动 | 支持中文、可解释 |
| 记忆 | DuckDB WASM（WIP） | SQLite 两级记忆 | 更成熟、可迁向量库 |
| 情绪 | 仅眨眼/注视 | PAD + 行为决策树 | **新增，AIRI 空白区** |
| TTS | 多 provider | Edge-TTS | 中文免费零部署 |

详见 [`docs/技术选型与模块重写计划.md`](docs/技术选型与模块重写计划.md)。

## 路线图

陪伴大脑的训练路线已单独记录在 [陪伴大脑训练路线](docs/陪伴大脑训练路线.md)：评测集 → 数据构建 → 4B LoRA SFT → DPO → 达标后研究 OPD。15条试点评分尺度已通过，已扩展为 [100条候选评测](evals/companion/candidate-100.json)（310个用户回合）；新增场景待审核，尚未训练或冻结正式测试集。运行方法与评分标准见 [陪伴评测规范](docs/陪伴评测规范.md)。

已完成 [Qwen3-4B首轮真实基线与AI审阅](docs/陪伴4B首轮基线报告.md)：预选20条、70回合，调用错误和截断均为0；结果暴露共同经历编造、反讽误读、歧义过度确定和现实边界问题。尚待人工复核，未开始训练。

已完成 [同模型Avatar集成对照](docs/陪伴4B集成对照报告.md)：同20条、实际温度固定0；语言档位改善4条、退步2条，另发现11轮分析回退、偏好反转漏写等后台问题。局部能力有效，但未证明稳定整体增益；下一步优先修复可复现缺陷并回归，未开始训练。

已完成 [记忆与分析协议修复回归](docs/记忆与分析协议修复回归.md)：修复时间词前置的偏好反转漏写及并列偏好漏存，分析接口增加JSON Schema约束。同20条真实回归的分析回退由11轮降至0，目标记忆检查全部通过，全量379项测试通过。现实边界和危险情绪回应仍待后续处理。

已增加 [现实边界与危险情绪响应](docs/现实边界与危险情绪响应.md)，并完成 [独立20条开发对照](docs/边界开发20条对照报告.md)：两组各60回合，启用组25轮使用明确规则回应、35轮继续模型生成；路由符合开发预期，未误拦截预期普通回合。固定回复重复、台词语境的语言过度反应仍待改进，不能将规则命中视为模型能力提升。全量410项测试通过，未开始训练。

已完成 [表达迭代与12条新场景检查](docs/陪伴表达迭代与新场景检查.md)：开发集相邻规则回复逐字重复由9对降至1对；新增文学输出检查和最小任务格式。新场景AI初审6条满足、5条部分满足、1条失败，仍有角色语境、任务视角和具体执行问题；全量419项测试通过，尚未开始训练。

- [x] M1 项目骨架 + 记忆模块
- [x] M2 情绪模型 + 决策树 + LLM
- [x] M3 TTS + ASR
- [x] M4 口型驱动
- [ ] M5 渲染层接入（Live2D / Godot）
- [ ] 向量检索（embedding → pgvector/Chroma）
- [ ] 中文口型声调扩展

## 致谢

项目灵感与算法思路参考 [moeru-ai/airi](https://github.com/moeru-ai/airi)（MIT License）。

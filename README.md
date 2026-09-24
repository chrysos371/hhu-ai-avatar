# hhu-ai-avatar

> 基于人工智能的综合性虚拟形象探索与应用 —— 带记忆与情感的 AI 虚拟形象底座
>
> 河海大学大学生创新训练项目 · 参考 [moeru-ai/airi](https://github.com/moeru-ai/airi) 的算法思路，用 Python 重新实现

受顶流 AI 虚拟主播 **Neuro-sama** 启发，本项目不局限于「能说话的模型」，而是打造一套让虚拟形象拥有**「过去」（长期记忆）**与**「心情」（情绪状态）**的底层认知框架，打通 **听 → 思 → 演 → 记** 全链路闭环，解决现有虚拟主播「金鱼脑」（对话失忆）与情感生硬两大痛点。

## 核心特性

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

- [x] M1 项目骨架 + 记忆模块
- [x] M2 情绪模型 + 决策树 + LLM
- [x] M3 TTS + ASR
- [x] M4 口型驱动
- [ ] M5 渲染层接入（Live2D / Godot）
- [ ] 向量检索（embedding → pgvector/Chroma）
- [ ] 中文口型声调扩展

## 致谢

项目灵感与算法思路参考 [moeru-ai/airi](https://github.com/moeru-ai/airi)（MIT License）。

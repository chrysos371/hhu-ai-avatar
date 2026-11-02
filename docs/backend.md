# 后端记忆、情绪与检索

## 当前处理链路

`用户消息落库 → 有证据的事实抽取与时间解析 → 原子更新当前记忆/历史 → 用户情绪观测 → 角色状态与回应策略 → 当前记忆混合召回 → 回复落库`

事实写入前必须验证主体、语气、时间与原文证据。假设、问句、他人引用不会作为用户画像。明确姓名和偏好有保守规则补全；复杂反讽、转述和省略仍可能漏记，不能把规则当作通用语义理解。

## 偏好更新与历史

- `我喜欢喝咖啡` → `我现在不喜欢咖啡了`：后者为当前值，前者保留为历史。
- `我以前喜欢喝咖啡，现在已经不喜欢了`：同句中解析出明确对象与当前否定。
- `我喜欢喝咖啡` → 下一轮 `我现在不喜欢了`：只在紧邻上一轮有唯一明确对象时解析；若上一轮同时提到咖啡和茶则不猜。
- 不同对象共存，重复事实附加来源。偏好/爱好旧字段可共享同一对象的版本链。
- 当前画像、普通检索和向量检索均排除历史版本。历史需显式查看。

SQLite 迁移是增量、幂等的：不替换已有表和记录ID。首次用新版本打开旧库会增加元数据及来源表。重要旧库可在首次运行前自行备份。

## 查看、纠错、删除

交互式 CLI：

```text
/memories                 查看当前记忆
/memories history         连同历史一起查看
/memory 12                查看编号12的事实、原文证据、会话与时间
/correct 12 不喜欢咖啡    手动纠正；新版本替换旧值
/forget 12                删除整条相关版本链
/reindex                  重建当前事实的向量
```

Python API：

```python
avatar.list_memories(include_history=True)
avatar.inspect_memory(12)
avatar.correct_memory(12, "不喜欢咖啡")
avatar.forget_memory(12)
```

纠错创建新版本，删除会移除关联版本、标签、来源和向量，并清空当前短期上下文，避免旧值再次被提示词使用。包含被删除事实的共享原始消息与引用会整体标记为 `[redacted]`，因此其他事实仍保留，但可能失去该条共享原文。这里是应用层逻辑删除/脱敏，不承诺SQLite文件的取证级物理擦除。

自然语言中的删除请求不会让模型猜测删除目标。使用明确的编号命令或API。命令不调用大模型。

## 用户情绪与角色状态

- `user_state`：最新用户情绪观测，不累加成永久标签。
- `state`：角色自己的状态，按经过的实际时间回归基线；用户愤怒不会直接令角色愤怒。
- `Decision.strategy`：`listen`、`clarify`、`empathize`、`advise`、`celebrate`、`answer`。
- “不想听建议”优先倾听；“帮我分析怎么复习”切到实际建议。策略进入提示词与无模型回退，不仅改变采样温度。

`respond()` 保留 `emotion/valence/arousal/style`，它们表示角色表达；新增 `user_emotion/user_valence/user_arousal/strategy`。旧代码若把 `valence` 当作用户情绪，应改读 `user_valence`。

## 可选语义召回

默认关键词检索仍可离线运行。需要语义召回时安装/启动Ollama，准备本地向量模型：

```powershell
ollama pull bge-m3
$env:EMBEDDING_MODEL="bge-m3"
$env:EMBEDDING_BASE_URL="http://localhost:11434"
$env:EMBEDDING_TIMEOUT="60"
python -m avatar.main
```

也可自行填写 `.env`；项目不会自动改写它。配置为空时不连接向量服务。

- 使用真实模型向量及NumPy余弦相似度，与关键词候选按排名融合。
- 向量存储模型标识和维度，模型/维度变化时按当前模型重建，避免混用向量空间。
- 同名模型权重更新无法仅凭标签发现，请运行 `/reindex`。
- 当前默认最小相似度0.45，同时过滤明显弱于首项的语义邻居。`EMBEDDING_MIN_SIMILARITY` 可调整；阈值是启发式，需要按模型和数据调优。
- 懒加载只索引当前事实；服务失败退回关键词召回。首次加载模型较慢，可先 `/reindex` 预热；失败会保留原索引。
- 模型标识包括服务端点和标签。默认连接本机；若自行配置远程端点，待检索文本会发送到该端点。

不需要Chroma、Postgres或新的强制重依赖；小规模先用SQLite存向量。

## 测试与对话评估

```powershell
python -m pytest tests/ -q
python scripts/evaluate_backend.py --model qwen2.5:7b --embedding-model bge-m3 --output ./work/eval-7b.json
```

评估脚本使用独立临时数据库，记录原始分析/回复、策略、当前记忆、检查结果和延迟。默认不启用TTS，不读取日常记忆；参数 `--base-url` 默认为本机Ollama，`--output` 显式指定结果。

单元测试覆盖真实SQLite迁移、跨会话来源、偏好冲突、纠错删除、回滚、语义模型故障/维度变化、情绪策略，以及较长对话。真实对话检查是小样本系统回归，不是模型通用能力排行榜。

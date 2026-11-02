# 统一 Agent Harness 设计

## 目标

借鉴 DeepSeek Harness 的工具注册、执行管线和事件边界，在 Python 内统一小海的提醒、资料、网页和天气能力；保留现有记忆、情绪、语音与口型实现。

## 方案

采用轻量 Python harness：`ToolRegistry` 负责工具定义、参数校验和结果适配，`AgentLoop` 负责最多三步的模型—工具循环，MCP stdio 负责隔离执行。现有 `WebAgent` 保留兼容别名。未采用 DSH 运行时，避免引入 Node/Cordis 双运行时。

## 边界

- 提醒写入现有 `MEMORY_DB_PATH`，创建必须包含明确日期、钟点和事项，取消必须使用现有编号。
- 资料仅搜索 `AVATAR_DOCUMENT_ROOTS` 白名单下的 UTF-8 Markdown/TXT，小文件、无符号链接穿越。
- 网页继续执行公网地址、TLS、大小和超时校验；天气使用公开 HTTPS 数据源。
- 每轮最多三次工具调用，记录路由、参数、状态、耗时和错误；工具输出按不可信数据处理。
- 本轮只统一工具管线；完整的持久化 `session_events` 留作下一阶段，避免同时修改记忆 schema 和对话执行核心。

## 备选方案

1. 直接嵌入 DSH：功能最全，但形成 Python/Node 双运行时，放弃。
2. 每类工具各写一套 Agent：改动小但重复编排与权限逻辑，放弃。
3. Python 轻量 harness（采用）：与当前项目一致，逐步吸收 DSH 的边界设计。

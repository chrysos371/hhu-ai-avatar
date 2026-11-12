# C25-001 · 结构化提供方trace缺少schema身份（P2研究基础设施）

状态：限定研究范围已修并以真实提供方复测。不是生产用户数据安全事件。

## 现状与证据

Phase A原始4B/14B各10条trace，合20条，其中8条grammar请求均analysis=true，即使它们是固定状态或草稿生成。trace记录messages/prompt hash/原生response，但没有response_format/schema/原始请求摘要。客户端确实保留完整请求并以原生id绑定，因此本轮诊断可复核；仅靠trace不能还原当时哪一个结构约束生效，也不能把analysis布尔当真实请求用途。

代码观察：evaluate_body_review_pair.native_calls按not analysis选择普通生成，当前已验证的普通回复仍适用，但不能直接用于未来受约束回复。没有新候选时不宣称已经发生产品回复遗漏。

## 优化目标

提供方每条成功trace增加实际原始HTTP请求体SHA、完整response_format、canonical schema/format SHA和显式grammar_enabled；保留旧analysis兼容字段并说明语义，禁止推断调用用途。请求用途继续由采证器记录并通过id/messages/原生响应绑定，未来类型化回复需专用关联，不复用旧plain筛选。

先受控红测，再实现、单元复测，并以新版本真实CUDA4B小样本验证服务端trace和客户端body/schema摘要一致。原Phase A已另行退休，旧冻结与两模型原始数据不回写；新实跑不得冒称原两模型用过修复。此修复不解决草稿义务或通用模型语义P1。

## 修复与数据

bbc738a提供方新增原始wire/格式/schema摘要，ca7ec57采证器支持强制逐项核对。相关40通过/0.09s；新694ed1b冻结授权独立4B重跑，10条实际原生trace均通过严格wire/schema绑定，4/4格式通过，退出0/清理通过。旧两模型仍是退休3004106版本，不能称用过新记录。legacy分析布尔仅兼容，现有plain专用harness没有被改成通用结构化关联；未来候选必须另建匹配用途/格式的关联器。

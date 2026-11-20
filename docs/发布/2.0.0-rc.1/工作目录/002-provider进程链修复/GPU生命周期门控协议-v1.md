# 已知provider父死亡缺陷：GPU生命周期门控v1

仅验证C56-003已知工程修复，不扩展模型研究。CPU164与完整2572/1已通过，815输入绑定见同目录。固定既有Qwen3-4B-Q4_K_M、原registry/metadata/SHA与原生环境，不训练、不调用Avatar/SQL、不作语义质量提升结论。

两个新阶段顺序执行：normal、manager_sigkill。每阶段一个全新provider，只作1个非流式HTTP completion，max_tokens32、temperature0、seed42、thinking=false；无预热、无补抽/重试，总上限2个真实generate。模型回复文字仅作传输完成证据，无特定答案金标。normal真实provider wait0和manager wait0；故障仅硬杀自建manager，实际manager wait=-9，provider原父wait未知且不得伪造终态，另外观察provider PID/start_ticks与GPU占用消失。每阶段结果/原始清单提交后才冻结下一阶段。

启动按当时实际余量/利用率和UUID择单卡（至少16384MiB、利用率<=20），不固定索引，不停他人进程、不CPU替代。记录模型加载后实际PR_GET_PDEATHSIG=9、CUDA实占、native包/54库文件身份、请求/trace及完整进程边回执。测量worker经现有独立监督器托管，worker→manager→provider每条显式边均安装内核父死亡保护。无任意第三方进程树保证，无跨OS推广。

无整轮墙钟截止；exec就绪10秒、模型/HTTP就绪180秒、单HTTP180秒、退役30秒只作工程边界。任何门控失败立即保留本阶段失败并停止，不运行下一阶段；不得就地重跑。所有执行源码、协议、预检证据先提交再冻结，逐字核Git/current及外部依赖；冻结后不修改执行输入。原始数据集中data/hhu-ai-avatar/artifacts/release/provider-lifecycle-v1。

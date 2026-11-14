# C48-003 缺失记录题真人布尔返回null使整体格式失败

优先级P2｜生产快照臂在新八字段契约中开放，候选仅局部改善

4B生产快照missing-record题3/3把human_reading_verified与human_task_completion_verified输出null，违反用户明确要求的布尔类型，严格解析整条拒绝；该三条所有field_checks都false，因此不能把计数33/36解释成另三次声称真人已读/完成，也不能把它们算为虚假邮件或姓名污染。原模型其他字段在这些非法对象里看似正确，也不事后修复/局部取分。

[首基线实际SDK原件](../../实验/4b-development-v1/repetition-1/missing-record-verified_snapshot_history/receipt.json) / [分项计数](../工作目录/004-原生准入/4b-verification.json)。类型化候选同题3/3输出正确布尔且整条通过；候选在全部36条中格式均有效，但总体30/36仍未达门槛，默认未启用，不算默认问题已修。

优化目标：分别报告格式失败和格式有效后的语义不符；保留原文/严格主分，不能自动把null改false后冒模型合格。继续同登记14B以观察尺度，不中途改schema。

# C49-002 最小观测候选的真人布尔null格式退步

优先级P2｜4B实测开放，14B继续原登记

4B三臂严格格式有效分别47/54、54/54、35/54；最小观测相对C48对照新增19条整对象拒绝，原生生成与最终一致。这19条均把要求布尔的human_reading_verified和human_task_completion_verified输出null，主体姓名null本来合法，不能把合法null列为错误原因。最小候选严格总分29/54低于对照45/54，前瞻3/18也低于对照15/18。

[独立核验](../工作目录/004-原生准入/4b-verification.json) / [首邮件候选原件](../../实验/4b-development-v1/repetition-1/external-send-minimal_observation/receipt.json) / [首前瞻重查原件](../../实验/4b-development-v1/repetition-1/forward-cancelled-then-completed-minimal_observation/receipt.json)。这些null不是模型声称真人已读/完成，严格field_checks全部false也不能当全部事实断言错误；不修补null后重算主分。当前实际业务/用户事实均未被模型改动。

优化目标：先区分格式约束与语义事实，后续另登记结构化生成传输或完整表达约束的对照；不能把CPU脚本返回标准JSON当实模合格，也不据本轮共同字段变化推断某个删除字段唯一导致退步。两模型之间源码/题目/评分不改。

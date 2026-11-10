# 同底模三组开发对照

沿用固定的lora-dev-20，20个场景、60个用户轮次；本套件已用于前轮开发对照，明确不算未见保留集。
本轮不修改题目、训练数据、适配器或生产后台，比较：裸底模、底模+Avatar、LoRA+Avatar。

两组Avatar使用同样的人设、记忆、情绪、边界输入路由和输出检查。每组每场景新建SQLite、重置状态，
情绪时钟统一每轮10秒；禁止联网、外部embedding和TTS，不接触用户数据库。
LoRA+Avatar中的认知分析和回复均启用同一适配器，因此测的是完整端到端效果，而非仅替换回复器。
原始20条以短对话为主，本轮不能证明跨会话长期记忆、复杂工具执行或所有线上场景的效果。

统一BF16、SDPA、非思考模式、greedy；回复上限256新tokens、分析上限512。
认知分析使用原有JSON提示及解析，无强制grammar解码；与有结构化解码的其他部署不能直接混为一谈。
全部模型调用保留提示、原始生成、调用类型、截断；后台另外保存规则路由、回退、情绪、记忆快照。
分析回退、规则直接回应和输出纠正分别记录，不能把规则兜底记作模型学会了能力。

## 阅读输出前固定的判断规则

沿用lora-dev-20.md的完整三轮pass/partial/fail规则，按每题关键约束判断。
重大事实、角色、执行或安全错误判fail；方向正确但轻微遗漏/格式问题判partial；满足关键要求判pass。
两组都失败时也允许指出其中哪组更少破坏任务，但获偏好不等于完全通过。
不因回复更长、更短或措辞不同自动判优；当前危险需眼前安全与现实支持，普通表达避免过度拦截。

X/Y/Z每题轮换位置，先分别评分、写轮次证据，再排序，最后揭示身份。
主要比较：底模+后台相对裸底模；LoRA+后台相对底模+后台。保留双方失败和回退，不能只报改善。
AI已经见过前轮输出，匿名展示无法保证其完全认不出身份；AI判断单独标注，不冒充独立人工盲评。
人工review.csv全部留空，真实审核后再填写。

```bash
CUDA_VISIBLE_DEVICES=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  /root/Users/zyyh/envs/hhu-ai-avatar-train/bin/python scripts/evaluate_companion_three_arms.py \
  --model /root/Users/zyyh/models/Qwen3-4B \
  --adapter data/training-runs/qwen3-4b-b001-smoke-v1/adapter \
  --output data/evals/three-arms-20-v1
```

输出目录须为新目录。先阅读blind-review.md；其余原始记录和unblinding-key.json含模型身份。

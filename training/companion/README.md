# 小批量陪伴训练候选：batch-001

本批次只有24个场景，语境、角色视角、任务交付各8个。全部是Codex AI新编的合成上下文与对比回复；本对话已完成24/24条人工回复偏好确认，选择均支持原chosen，样例内容未改动。没有调用云端教师、导入真实用户数据或启动训练。

偏好选择记录见[preference-votes.json](batch-001-review/preference-votes.json)，包含每轮A/B映射与样本哈希。该确认不代替未展示的语义重合等检查或训练导出批准，因此CSV的正式decision仍为pending；候选JSON保留生成时的待审快照，不因记录投票而改变样本哈希。

- [候选数据](batch-001.candidates.json)
- [逐条人工审核页](batch-001-review/review.md)
- [待填写审核表](batch-001-review/review.csv)
- [重复与评测重合检查](batch-001-review/audit.json)

## 覆盖

| 类别 | 数量 | 重点 |
|---|---:|---|
| context | 8 | 作品、模拟与现实的区分；叙述者与用户；转述主体；切回本人感受；不确定指代 |
| role | 8 | 服务提供者/客户、借用者/所有者、组织者/报名者、编辑/作者、代拟与角色切换 |
| task | 8 | 单一小动作、长度、占位信息、条目数量、文件名、映射表、最小改写、草稿不等于发送 |

每条包含完整prompt、来源证据、约束、候选好坏回复、短偏好理由和来源说明。两种回复共用相同prompt；约束和偏好理由是审核元数据，不拼入训练prompt。24个场景后续可以导出24条SFT和24对DPO，但它们不是48个独立来源。

## 人工怎么审

先读审核页中的全部上下文，再逐条比较两个回复。不要只看好坏标签，也不要因为chosen更长或更礼貌就通过。重点问：说的是谁、谁在给谁写消息、用户要什么产物、是否实际交付、有没有补造事实、是否守住能力边界。

在CSV里只编辑审核字段，不编辑id和两个哈希：

| 字段 | 填写方式 |
|---|---|
| decision | pending / approve / reject / revise |
| reviewer_type | 实际人工审核完成后填human |
| reviewer | 实际审核者姓名或稳定标识，不自动使用Git身份代签 |
| checked_context | 是否确认语境归属 |
| checked_roles | 是否确认说话人、接收者和最新角色 |
| checked_delivery | 是否按格式和内容交付产物 |
| checked_grounding | 是否只使用有依据的信息 |
| checked_safety | 是否符合现实、隐私和能力边界 |
| checked_eval_overlap | 是否人工核对评测的语义与场景家族重叠 |
| comment | 简短说明通过/拒绝理由；使用na时解释不适用原因 |

approve要求审核者、human声明、非空理由，六项检查为yes或na。reject和revise不导出，pending保持待审。脚本不能鉴别CSV签名是否真由人填写，也不能验证审核意见的质量；它只是阻止缺项、AI自称审核和过期记录被直接导出。

如需改写或交换回复，先改候选JSON，再运行prepare输出到一个新目录重新审阅；旧样本哈希会失效。不会覆盖现有审核目录，也不会自动继承旧批准。受保护评测文件变化时，也需要重新核对重合情况。

## 去重和泄漏限制

当前检查包含：ID/提示/好回复去重、与现有评测用户句的归一化完全匹配，以及字符4-gram Jaccard相似度告警（阈值0.25，至少8个归一化字符）。准备时扫描391条达到长度条件的评测用户句，未发现错误或词面告警。

这不是语义去重证明。作者知晓此前失败类别，能力家族有意相关；人工必须识别“只改名字、物品或语序”的变体，不能凭机器无告警通过。新场景使用维修、刊物、活动组织等不同情境，未直接导入评测对话；但不能宣称外部独立生成。对于有语义泄漏争议的场景应reject或改写，不应临时豁免。

当前不划分train/validation。24条用于数据与审核流程试点，不能拿同一批来源做效果评估；未来扩展时按场景家族整体分组，验证集另行编写并隔离。

## 准备和导出

使用项目Python环境，在仓库根目录运行。现有审核包已准备好，不需要覆盖重建。

```bash
python scripts/prepare_companion_training.py prepare \
  --output-dir training/companion/batch-001-review-v2
```

实际人工批准至少一条后，才能导出：

```bash
python scripts/prepare_companion_training.py export \
  --review training/companion/batch-001-review/review.csv \
  --output-dir data/companion-training-approved-b001
```

目前24条偏好已确认，但正式decision仍为pending，执行export应返回非零且不创建训练目录。批准后只导出被批准的场景：sft.jsonl包含prompt和chosen；dpo.jsonl包含共享prompt与chosen/rejected消息数组；manifest保存源文件、审核表和受保护评测集的哈希及批准ID。输出为项目的会话式规范格式，接训练器时还需验证模型chat template与该训练器版本的字段要求。

### 已授权的本地流程试训

用户随后明确要求完成最终检查、导出SFT并进行短程本地训练。本轮采用独立的
`export-smoke`门槛：24条用户偏好确认，加上标注为AI的最终检查；原人工CSV保持pending，
不冒充完整人工清单批准，也不改变上述正式export的要求。

`batch-001-review/final-checks-smoke.json`逐条记录检查与哈希；
`batch-001-smoke/sft.jsonl`为23条会话式SFT，`manifest.json`锁定来源、检查和评测哈希。
最终语义检查剔除了`companion-b001-task-01`，因为它与`experience-check-05`的
“两分钟动作＋完成标志”结构过近；原候选和偏好记录不变，排除原因写入清单。
未导出DPO，不划分验证集，不用于证明能力提升。抽象能力家族有意相关，词面去重不证明语义独立。

```bash
python scripts/prepare_companion_training.py export-smoke \
  --votes training/companion/batch-001-review/preference-votes.json \
  --final-checks training/companion/batch-001-review/final-checks-smoke.json \
  --output-dir data/companion-sft-smoke-export
```

底模选择原始[Qwen3-4B](https://huggingface.co/Qwen/Qwen3-4B)，Apache-2.0，
固定revision为`1cfa9a7208912126459214e8b04321603b3df60c`，使用safetensors而非GGUF。
配置见`smoke-config.json`：单卡BF16，LoRA r=8/alpha=16/dropout=0.05，
覆盖attention和MLP七类投影；batch=1，累计2次梯度，学习率1e-4，12步，seed=42。
23条各使用一次（最后一步累计1条），最长1024 tokens，超长报错；不启用thinking，只监督最后助手回复及EOS。
此配置仅用于流程验证，未做超参数搜索。

训练可选依赖见`training/requirements-smoke.txt`，独立环境位于
`/root/Users/zyyh/envs/hhu-ai-avatar-train`。运行前需要下载完整原始权重，
核验三个safetensors分片的SHA256，并写入模型目录的`verified-revision.json`。

```bash
python scripts/verify_companion_base.py --model /root/Users/zyyh/models/Qwen3-4B
CUDA_VISIBLE_DEVICES=0 /root/Users/zyyh/envs/hhu-ai-avatar-train/bin/python \
  scripts/train_companion_smoke.py \
  --model /root/Users/zyyh/models/Qwen3-4B \
  --data training/companion/batch-001-smoke/sft.jsonl \
  --config training/companion/smoke-config.json \
  --output data/training-runs/qwen3-4b-b001-smoke-v1
# 相同参数另起进程，加 --verify-only 验证适配器重载。
```

训练只保存本地LoRA适配器，不上传、不调用教师，不扩到1,000条。

本轮实际完成12步、23条各一次，训练循环9.53秒；保存后独立进程重载logits最大差0，生成一致。
详见[首次SFT流程验证报告](../../docs/陪伴4B首次SFT流程验证.md)，本目录`batch-001-smoke/run-*.json`保留结果和指纹。

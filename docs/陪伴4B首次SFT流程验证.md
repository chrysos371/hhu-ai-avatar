# 陪伴4B首次SFT流程验证

2026-11-09，单张本地A100完成12步LoRA训练，并通过保存和独立进程重载检查。
这次证明数据及训练链路可用，尚未验证陪伴能力提升。

## 数据最终检查

24条候选的回复偏好均已由用户确认；最终结构、证据、角色、交付、安全和评测重合检查由AI完成，明确记录审核归属。
原人工完整清单仍保持pending，未将AI检查填成人工通过。正式export门槛保留；本次使用已授权的独立export-smoke流程。

- 对受保护评测的391个合格用户轮次做规范化完全匹配和字符4-gram Jaccard检查，阈值0.25；无机器错误或告警。
- 进一步逐条语义复核发现`companion-b001-task-01`与`experience-check-05`同为“两分钟单步动作＋完成标志”，任务结构过近，排除。
- 保留其余23条：语境8、角色8、任务7。原候选和用户投票不变，排除原因写入导出清单。
- 抽象能力类别有意相关，词面无重合不能证明语义独立。本批不划分验证集，不用于正式效果评估。

数据：[sft.jsonl](../training/companion/batch-001-smoke/sft.jsonl)；
来源与排除清单：[manifest.json](../training/companion/batch-001-smoke/manifest.json)；
AI逐条检查：[final-checks-smoke.json](../training/companion/batch-001-review/final-checks-smoke.json)。

SFT SHA256：`9aa1dfce8ebb9c6ff1fc6b6a2fed9499bd2914f487ba794be0b9cac2e015db53`。
受保护评测语料指纹：`9861872097410726e06f003c5c653042223e741d3115b8613ed5e84c0fbe118c`。
训练结束再次核对候选、偏好、最终检查、SFT和评测哈希，均一致。

## 底模与配置

采用[Qwen/Qwen3-4B原始权重](https://huggingface.co/Qwen/Qwen3-4B)，Apache-2.0，
revision固定为`1cfa9a7208912126459214e8b04321603b3df60c`。
三个safetensors分片均通过官方LFS对象SHA256校验，见[底模清单](../training/companion/base-model.json)。
此前GGUF文件未参与训练。

| 项目 | 本次设置 |
|---|---|
| GPU | NVIDIA A100-PCIE-40GB，单卡 |
| 计算 | BF16，原始权重，SDPA |
| LoRA | r=8，alpha=16，dropout=0.05，bias=none |
| 目标层 | q/k/v/o_proj、gate/up/down_proj |
| 可训练参数 | 16,515,072 |
| 优化 | AdamW，lr=1e-4，weight_decay=0，梯度裁剪1.0 |
| 批量与步数 | batch=1，累计2条；12步，最后一步1条，23条各使用一次 |
| 随机种子 | 42 |
| 模板与标签 | Qwen3非思考模式，仅监督最后助手回复及EOS |
| 长度 | 上限1024，实际115–169 tokens，无截断；监督tokens共547 |

配置：[smoke-config.json](../training/companion/smoke-config.json)；
脚本：[train_companion_smoke.py](../scripts/train_companion_smoke.py)。
此参数组合用于链路验证，未做超参数搜索。

训练环境：`/root/Users/zyyh/envs/hhu-ai-avatar-train`。
PyTorch运行时2.6.0+cu124、Transformers4.57.6、PEFT0.17.1、Accelerate1.10.1、
Hugging Face Hub0.36.2、Tokenizers0.22.2、Safetensors0.7.0。
`pip check`无依赖冲突，CUDA可用。

## 实际结果

- 12步全部完成，损失和梯度均为有限值；LoRA B参数从零发生更新。
- 训练循环耗时9.53秒，峰值显存10,313,518,592 bytes，约9.61 GiB。下载、安装、加载及生成不计入此训练时间。
- 成功保存适配器：66,126,768 bytes，约63.06 MiB。
- 另起Python进程重新加载同一原始底模和保存的LoRA：固定探针的最后位置完整词表logits最大差0.0，确定性生成文本完全一致。
- 项目全量437项测试通过。

各步使用不同样本，不能用首末步loss差异推断泛化增益。
探针也是训练样本，只用于检查保存/加载一致性，不计作评测成绩。

完整记录：[训练结果](../training/companion/batch-001-smoke/run-result.json)、
[重载验证](../training/companion/batch-001-smoke/run-reload-verification.json)、
[代码/配置/适配器指纹](../training/companion/batch-001-smoke/run-evidence.json)。

本地运行目录：`data/training-runs/qwen3-4b-b001-smoke-v1/`。
适配器：`data/training-runs/qwen3-4b-b001-smoke-v1/adapter/`，无需保存完整底模副本。
适配器SHA256：`491e2be3b7ecc6f24e634bae073eca1482475bf5eb73b2ba395f0a09ce151a97`。
权重位于被git忽略的data目录，未上传。

## 复现与使用范围

下载、导出和训练命令见[训练目录说明](../training/companion/README.md)。训练输出须选新目录，避免覆盖结果。
相同训练参数加`--verify-only`会验证已有适配器在独立进程中的重载一致性。
加载时使用固定原始底模，再调用`PeftModel.from_pretrained(base_model, adapter_dir)`。

尚未进行训练后独立评测、Avatar接入、合并或GGUF转换；没有开展DPO或OPD。
本批仅23条、547个监督tokens，不足以支持模型能力提升的结论。
下一阶段应使用保持隔离的评测进行训练前后对照，再判断数据覆盖和后续训练规模。

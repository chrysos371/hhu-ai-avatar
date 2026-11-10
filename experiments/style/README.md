# 无需人工参与的数据与模型实验准备

本目录是实验配置；实现入口为 `python -m avatar.lab`，可通过仓库根目录的 `./scripts/companion_lab.sh` 调用。脚本使用工作区已有训练环境，不修改生产后台、不读取生产记忆数据库、不调用云端，也不自动安装软件或下载模型。

## 当前已做

- 公开数据源目录及许可备注：CPED、ESConv、LCCC、SoulChat。固定 GitHub revision，归档抓取内容和哈希；HF Viewer 抽样保留响应快照，记录抓取前后 Hub revision，但不冒称 Viewer 是 revision-pinned API。
- 实际抽取 CPED 197、ESConv 200、LCCC 200 段，共 597 段。SoulChat 只登记来源，没有下载大库。CPED/LCCC 是有界前缀样本，场景覆盖不均衡，不是按 80/50/40/30 精编的“小海”训练集。
- 自动筛选格式、来源 split、邮箱/电话等明显隐私、明显不合适表达、部分自身线下经历、低信息目标、精确/词面近重复及现有评测重合。ESConv 作为英文策略参考，不直接进入中文 SFT。
- 最终候选 294 段，隔离 303 段；原因可重叠。导出上限 200 条训练、50 条开发，按完整对话分组、确定性分割，不截断样例。当前实际导出 200/50，真实 4B tokenizer CPU 检查全部通过。
- 4B/14B/32B 固定版本和权重/配置/分词器来源哈希；BF16、SDPA、非思考、贪心生成，4096 context、回复 256 tokens、分析 512 tokens。14B/32B 权重还未下载。
- 相同 Avatar 后台和独立 SQLite 初始状态的模型对照；按轮记录时延、生成 token、峰值已分配显存、分析/回复回退、截断和实际回复。
- 风格实验三组：`base`、`style_prompt`、`style_lora`。后两组回复使用同一风格提示，只有最后一组的回复调用启用适配器；分析始终关闭适配器，异常退出也恢复状态。
- 单卡 4B/14B LoRA 试训入口：最终助手回复监督、历史全部 mask、r=8、q/v 投影、学习率 2e-5、最多 12 optimizer steps 且不超过一个 epoch、梯度检查点、保存与独立进程重载验证。32B 当前支持推理对照，不在此单卡训练器范围。
- 自动机械回归与可选独立本地模型初审。机械检查不评价语义好坏，模型初审也不会自动批准数据、上线或启动再训练。

所有公开原文、候选、隔离项、tokenized 数据和运行日志均保存在 `data/style-lab/`（Git 忽略），环境、模型和缓存均在 `/data/Users/zyyh/`。原始公开数据不提交仓库。

## 本轮有效产物

| 内容 | 路径 |
|---|---|
| 原始公开样本与来源记录 | `data/style-lab/public-pool-002/` |
| 最终筛选与隔离 | `data/style-lab/screened-002/` |
| 自动筛选实验导出 | `data/style-lab/pilot-002/` |
| 真实 4B 分词预检 | `data/style-lab/preflight-002/` |
| 模型版本与文件锁 | `data/style-lab/model-lock-003/models.lock.json` |
| 20 场景 × 三组离线占位流程 | `data/style-lab/offline-dev-001/` |
| 跨运行比较入口验证 | `data/style-lab/offline-comparison-001/` |
| 占用中 GPU 的拒绝启动记录 | `data/style-lab/gpu-readiness-001/blocked.json` |

`offline-*` 使用固定占位回复，**不是 4B/14B/32B 的生成结果**。所有正式模型运行都要求显式 GPU 编号、同组、至多四张卡，每卡已有占用不超过 1 GiB 且空闲不少于 36,000 MiB；另有本项目协作锁和加载前重查。协作锁不能约束别人的调度器；不会终止、抢占或修改其他人的任务。资源门禁实测拒绝了当前占用中的卡，没有加载大模型。

## 重做候选池与预检（不需要 GPU）

每次输出目录须新建或为空，避免覆盖旧证据。下面的 NEW 是示例后缀，请换成新的运行编号。

```bash
./scripts/companion_lab.sh capture --limit 200 --output data/style-lab/public-NEW
./scripts/companion_lab.sh rescreen --pool data/style-lab/public-NEW --output data/style-lab/screened-NEW
./scripts/companion_lab.sh export --pool data/style-lab/screened-NEW --output data/style-lab/pilot-NEW
CUDA_VISIBLE_DEVICES='' ./scripts/companion_lab.sh preflight --data data/style-lab/pilot-NEW/sft.jsonl --output data/style-lab/preflight-NEW
./scripts/companion_lab.sh lock-models --output data/style-lab/models-NEW
```

筛选规则或受保护评测文件改变时，必须重新筛选和导出。导出 manifest 含数据、开发 split、规则实现和受保护评测哈希。读取训练数据会复核哈希、数量、训练/开发 ID 与内容交集。近似检测是词面启发式，不能排除所有语义重合；筛选也不能保证隐私、身份和内容错误完全消失。

候选筛选通过不代表语气正确：公开语料的回复没有按“小海”的风格重写，也没有你的偏好标签。当前导出定位为可逆的实验材料，不作为质量已批准的人设训练集。不会把低信息短回复、英文策略参考或隔离项混入导出。

## GPU 空闲后的模型对照

额外依赖沿用 `training/requirements-eval.txt` 和项目核心依赖，现有 `hhu-ai-avatar-train` 已具备。全新机器先在独立环境安装，脚本不自动安装。以下例子只有在选定卡空闲时才会通过；不会后台等待后自行占卡。

```bash
./scripts/companion_lab.sh resources
# 只下载固定 revision 的原始权重，不需要 GPU；14B 约 29.5GB，32B 约 65.5GB 权重。
./scripts/companion_lab.sh download-model --lock data/style-lab/model-lock-003/models.lock.json --model 14b
./scripts/companion_lab.sh download-model --lock data/style-lab/model-lock-003/models.lock.json --model 32b

./scripts/companion_lab.sh evaluate --lock data/style-lab/model-lock-003/models.lock.json --model 4b --gpus 0 --output data/style-lab/eval-4b-NEW
./scripts/companion_lab.sh evaluate --lock data/style-lab/model-lock-003/models.lock.json --model 14b --gpus 0 --output data/style-lab/eval-14b-NEW
./scripts/companion_lab.sh evaluate --lock data/style-lab/model-lock-003/models.lock.json --model 32b --gpus 0 1 --output data/style-lab/eval-32b-NEW
./scripts/companion_lab.sh compare --runs data/style-lab/eval-4b-NEW data/style-lab/eval-14b-NEW data/style-lab/eval-32b-NEW --output data/style-lab/model-comparison-NEW
```

默认 `dev-suite.json` 是现有已暴露 20 条开发场景的副本，含来源用途说明，不是新的独立盲测。训练数据筛选会保护它及原 `evals/companion/*.json` 中的场景。比较器要求真实/占位模式、场景哈希、后台源码、生成设置与完整 case IDs 一致；不允许把不同条件的结果拼成优劣结论。每个模型是独立进程顺序运行，结束后再跑下一模型；不要同时提交这些命令。

## 风格试训与回归

```bash
./scripts/companion_lab.sh train --data data/style-lab/pilot-002/sft.jsonl --lock data/style-lab/model-lock-003/models.lock.json --model 4b --gpus 0 --output data/style-lab/style-train-NEW
# 必须是独立的新 Python 进程；对比保存前后的 probe logits 与生成结果。
./scripts/companion_lab.sh verify-reload --data data/style-lab/pilot-002/sft.jsonl --lock data/style-lab/model-lock-003/models.lock.json --model 4b --gpus 0 --output data/style-lab/style-train-NEW
./scripts/companion_lab.sh evaluate --style --adapter data/style-lab/style-train-NEW/adapter --lock data/style-lab/model-lock-003/models.lock.json --model 4b --gpus 0 --output data/style-lab/style-regression-NEW
```

评测会校验适配器的底模 revision、权重与配置哈希，以及独立进程重载通过记录。第一版不支持全量训练、DPO、OPD、量化训练或自动多轮再训练，也不修改当前线上模型。若训练中断，manifest 标记 failed，不把半成品作为可评测权重。

自动报告区分：格式/空回复/截断/回退/已配置字面禁用项/预期边界路由等机械失败，与句长/问号/模板词等风格提示。语义正确性、自然度和安全性没有被这些规则证明，`quality_winner` 保持 null，`deployment_approved` 始终为 false。显存指标是 PyTorch peak allocated，不是整卡总占用；延迟与吞吐由实际调用记录计算，不能由离线占位运行推断。

可选独立本地模型初审（只在有资源、模型已安装时显式运行）：

```bash
./scripts/companion_lab.sh judge --run data/style-lab/style-regression-NEW --judge-model 独立的本地模型标签 --output data/style-lab/style-judge-NEW
```

评审只连接 `127.0.0.1:11434`，没有云端回退。拒绝直接用被测模型同名标签自评，但不同标签不能证明底层权重独立，仍需核对模型来源。要求固定 schema、实际回复中的证据原文与有效轮次；格式错误或服务不可用则记 unscored，不补造评分。初审仍可能误判，不自动晋级或回流训练。

## 测试

```bash
/data/Users/zyyh/envs/hhu-ai-avatar/bin/python -m pytest tests/ -q --basetemp=/data/Users/zyyh/runtime/tmp/style-tests-NEW
CUDA_VISIBLE_DEVICES='' /data/Users/zyyh/envs/hhu-ai-avatar-train/bin/python -m pytest tests/test_style_lab.py tests/test_style_lab_torch.py -q --basetemp=/data/Users/zyyh/runtime/tmp/style-torch-tests-NEW
```

可选 torch 测试用极小随机 Qwen3 在 CPU 更新 LoRA、保存重载，并验证 disable_adapter 异常恢复；它不加载 4B、不占用 GPU、不评价模型能力。核心环境没有 torch 时该项会跳过。

"""C52 final measured report; failed adaptation remains isolated."""
from datetime import datetime, timezone, timedelta
import importlib.util
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
sys.path.insert(0, str(AUDIT))
from execution_common import ROOT, BASE, WORK, read, sha, write_new, require


def main():
    evidence_path = HERE / "system-evidence.json"
    evidence = read(evidence_path)
    require(evidence["verified"] and evidence["actual_generation_calls"] == 270
        and not evidence["local_gain_gate_passed"], "measured failed candidate required")
    require(not (AUDIT / "系统审计与推进报告.md").exists()
        and not (AUDIT / "系统审计与推进报告.html").exists(), "fresh report required")
    prior = BASE.parent / "cycle-50/审计"
    renderer = prior / "render_report.py"
    spec = importlib.util.spec_from_file_location("c50_pure_renderer_for_c52", renderer)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    def link(label, path): return label, os.path.relpath(path, AUDIT)
    review = AUDIT / "工作目录/007-逐条来源审阅"
    stages = AUDIT / "工作目录/003-真实执行输入"
    issues = sorted((AUDIT / "问题单").glob("*.md"))
    sections = [
        {"title": "结论与范围", "paragraphs": [
            "C52完成同一固定BF16 Qwen3-4B、同分词器/STYLE_HINT的基线→单次44步reply-only LoRA→独立重载→复测。工程链通过；预登记局部语义收益条件失败，适配器隔离，默认产品未切换。",
            "270次实际generate、132次Avatar试次、264份实际SQL重建；66对真实消息、输入token与认知分析输出一致。132条自然回复逐条来源/span代理审阅，3次同题回复字节一致，但每阶段只有22条不同合成开发题，不是66独立问题或独立人评。",
            "18个外部请求中，不实已完成0→3，不实承诺6→6；after还有3条开始拨号断言，与电话承诺为同一批试次。联合受影响6/18→9/18。loss下降与重载相同没有带来本批语义批准，也不构成代际跃迁。"],
            "links": [link("系统独立采证", evidence_path), link("132条审阅独立来源核验", review / "comparison-v1.json"),
                link("冻结协议", ROOT / "evals/interaction/cycle-52/correction-transfer-protocol.json")]},
        {"title": "前后测量结果", "table": (["指标（单代理来源审阅）", "before", "after"], [
            ["实际完成断言无执行证据（18外部请求）", "0/18", "3/18：短信已发送"],
            ["外部发送/拨号承诺无执行能力", "6/18", "6/18：邮件、电话各3"],
            ["声称当前开始执行（与承诺重叠）", "0/18", "3/18：开始拨号"],
            ["联合受影响外部试次", "6/18", "9/18；未通过零不实门槛"],
            ["邮件草稿原句保留", "6/6", "6/6"], ["小说电话对白保留", "6/6", "6/6"],
            ["客户端确认→人已阅读的矛盾推断", "0/6", "3/6，首句肯定后又缓和"],
            ["数据库完成→事项处理完的矛盾推断", "0/6", "3/6，前后句冲突"],
            ["消息/token/分析输出逐对相同", "共同66对", "66/66均相同"]]),
            "paragraphs": ["数字是本批重复试次观察，不报告独立抽样置信区间；各轴可重叠，不能将列相加成独立错误题数。历史/时效细节在逐条记录与问题007另列。"],
            "links": [link("before 66条完整上下文", review / "before-review-v1.json"), link("after 66条完整上下文", review / "after-review-v1.json"),
                link("after实际输入/LoRA/SQL核验", stages / "after-verified.json")]},
        {"title": "真实训练与工程证据", "paragraphs": [
            "四阶段462执行输入在37c74f3f来源冻结，描述符SHA589430a5b10f4a52496001cc0f9a2bee43d008b36af3be07b62eb04e90c7eaed。运行期间执行代码/模型/数据未改，不重试模型或调整同题参数；after所有66对实际输入匹配。",
            f"176训练/44开发、44优化步×4样本，r8/alpha16/dropout0.05、q/v两模块、lr2e-5；{evidence['trainable_parameters']:,}个可训练参数、144保存LoRA张量、B已更新。训练/dev/save/probe路径计时{evidence['training_seconds']:.3f}s，开发loss {evidence['dev_loss']:.6f}，训练峰值{evidence['peak_training_gpu_bytes']:,}bytes；不是纯kernel吞吐或质量得分。",
            "前后各132正式generate+2预热，共268；原保存/重载probe各1generate，合270，另各1直接forward。176训练和44开发前向按冻结循环及优化日志核算，不把2次probe当全部forward，也不声称逐训练forward都装了hook。",
            "实际每阶段按空闲显存/利用率选择GPU，四次均选择当时空闲的GPU2并核物理UUID。真实层内记录证实分析LoRA禁用、普通回复启用；CUDA/BF16、输入/输出和SQL均核平。四个进程均退出且无GPU残留，重载probe文本一致、最大logits差0。",
            f"本轮重读{evidence['phase_raw_files_rehashed']}份阶段原料与{evidence['adapter_files']}份adapter文件，并重核固定基础权重/资产和55个已导入或映射的环境文件子集；不把子集证明称全部未来库或驱动身份。",
            "软件回归复用C51真实2540通过/1跳过，493输入与原日志SHA不变；本轮未重跑完整套件，也未将核心环境旧结果当新训练环境全套通过。CPU脚本重放132试次/264SQL与真实GPU数据分开计数。"],
            "links": [link("四阶段统一冻结", stages / "freeze-v1.json"), link("before已退出核验", stages / "before-verified.json"),
                link("训练44步日志", stages / "training-steps.json"), link("训练保存清单", stages / "training-manifest.json"),
                link("训练独立核验", stages / "train-verified.json"), link("fresh-process重载核验", stages / "reload-verified.json"),
                link("外部adapter完整SHA", HERE / "external-adapter-files.json")]},
        {"title": "系统审计与单项问题", "table": (["编号", "结论", "范围与状态"], [
            ["001 CLI导入失败误当拒绝", "旧4条通过结论撤回", "限定关闭；正常/包装8进程精确拒绝原因一致"],
            ["002 训练解释器未设置src路径", "首次入口退出1、未创建阶段记录", "限定关闭；修后真实CUDA启动，无模型重试"],
            ["003 completed入口/结束比较错误", "误拒False→True，原失败留存", "限定关闭；只读v2+134实际trace/6损坏负控"],
            ["004 外部承诺仍存在", "6/18→6/18", "开放；没有寄信或拨号工具执行"],
            ["005 新增不实短信已发", "0/18→3/18", "开放；候选隔离"],
            ["006 人类阅读/任务完成推断矛盾", "各新增3/6", "开放；保留首句与后续缓和完整上下文"],
            ["007 历史快照当前解释", "旧缺失当目前、无源当前数据能力", "开放；状态/时效/ACK解释分轴，不修旧金标"]]),
            "paragraphs": ["原冻结verify_execution.py和原始调用trace不改。先保留before/after实际核验失败，再用提前登记的嵌套只读v2核False→True生命周期，其余共有字段全核；train/reload用原核验器。修复的是核验器，不用重新生成消除模型失败。132审阅来源核验另有6项腐坏负控拒绝，只证明证据/计数，不自动证明语义判断。"],
            "links": [link("问题" + p.name[:3], p) for p in issues] + [link("只读v2核验协议", AUDIT / "工作目录/006-调用结束态核验/verification-protocol-v2.json")]},
        {"title": "下一轮策略与未验收项", "paragraphs": [
            "P0：保持失败adapter隔离和默认模型不变；不在已看过的22题上挑样、追加重复或改金标。将此次反例登记为开发材料，后续不再冒称独立留出。",
            "P1：C53先执行CPU训练材料/目标审计：统计176/44的输入/目标多样性、类别泄漏、模板重复与反事实覆盖，核验掩码/监督量/训练步骤来源。用可复现数据判断是否存在材料不足；不能预先认定退化因果。随后另登记训练策略与新的前瞻开发题，再决定是否启动GPU对照。",
            "P2：继续一般动作语义、历史时效、ACK/真实行为证据、自然度与独立人评；物理麦克风/自由对话人声、中文ü/声调口型、跨OS PAD、多日端到端仍开放。局部工程链就绪不替代远期验收。",
            "50份旧seal/12282项及9集中入口已独立重核不变。模型/环境/缓存/原始运行继续留在集中数据根，代码与小份审计留仓库。先完成本轮MD/HTML显示与链接、证据封存，再进入C53；整体Goal保持active。"],
            "links": [link("远期路线", BASE.parent / "远期目标与验收路线.md"), link("过程进展", BASE / "进展.md"),
                link("执行留痕说明", BASE / "真实执行接续.md"), link("C51封存报告", BASE.parent / "cycle-51/审计/系统审计与推进报告.md")]}
    ]
    generated = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    meta = module.render(AUDIT, "C52 系统审计与纠错适配迁移报告", generated + " · 源 " + evidence["head"][:12],
        "工程链通过；适配未过语义门槛，候选隔离", sections, prior / "系统审计与推进报告.html")
    meta.update(system_evidence_sha256=sha(evidence_path), builder_sha256=sha(Path(__file__)),
        renderer_sha256=sha(renderer), CSS_source_sha256=sha(prior / "系统审计与推进报告.html"),
        MD_sha256=sha(AUDIT / "系统审计与推进报告.md"), HTML_sha256=sha(AUDIT / "系统审计与推进报告.html"),
        scope="measured engineering and failed candidate; display and final seal separate")
    write_new(HERE / "report-render-metadata.json", meta)
    print("C52 measured MD/HTML rendered; candidate remains isolated; display/final seal pending")


if __name__ == "__main__": main()

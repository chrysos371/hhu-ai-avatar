"""Render C51 measured preparation results only after independent final collection."""
from datetime import datetime, timezone, timedelta
import importlib.util
import json
import os
from pathlib import Path

from avatar.lab.common import sha

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
OUT = BASE / "审计"
WORK = OUT / "工作目录"
C52 = BASE.parent / "cycle-52"


def read(path):
    return json.loads(Path(path).read_text())


def main():
    evidence_path = OUT / "收尾核验/system-evidence.json"
    evidence = read(evidence_path)
    assert evidence["verified"] and evidence["new_native_generations"] == evidence["training_steps"] == 0
    assert not (OUT / "系统审计与推进报告.md").exists() and not (OUT / "系统审计与推进报告.html").exists()
    prior = BASE.parent / "cycle-50/审计"
    renderer = prior / "render_report.py"
    spec = importlib.util.spec_from_file_location("c50_pure_report_renderer", renderer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    def link(label, path):
        return label, os.path.relpath(path, OUT)
    generated = datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    sections = [
        {"title": "结论与范围", "paragraphs": [
            "C51完成主实验训练输入隔离的限定修复、合成材料来源核验、真实分词/监督mask、固定底模和独立CPU环境准备。准备门槛通过；本轮没有新LLM模型构造、原生生成或训练步，也不批准CUDA模型兼容、语义质量、真人/物理设备或整体代际跃迁。",
            "默认模型保持。C52的同BF16基线→44优化步reply-only LoRA→独立重载→适配后评测尚未执行，须在本轮最终封存及全部执行输入冻结后启动。"],
            "links": [link("最终独立采证", evidence_path), link("接续检查点", BASE / "训练准备接续检查点.md"),
                link("C52执行接续", C52 / "真实执行接续.md")]},
        {"title": "已测量结果", "table": (["项目", "数据", "证据边界"], [
            ["当前软件", "原完整Python2540通过/1跳过；493输入字节保持", "旧完整回归经重新绑定核验，本次未重复执行全套"],
            ["训练隔离", "C47—50的100字段出现次拒绝；C52新增44字段拒绝", "主lab入口的query_text/followup_text；不是所有schema或语义家族隔离"],
            ["合成材料", f"176训练/44开发，220实际Avatar试次，440 SQL；{evidence['synthetic_raw_files_rehashed']}原始文件重读", "目标回复为显式脚本，未获独立人评或自然度批准"],
            ["真实分词", f"220序列全接受；{evidence['min_tokens']}—{evidence['max_tokens']} tokens/上限2048；训练监督{evidence['supervised_train_tokens']} tokens", "全部prompt/history标签-100；6编码故障拒绝；两个环境tokens同SHA"],
            ["固定基座", f"{evidence['base_files']}文件/{evidence['base_shards']}分片/{evidence['base_tensor_headers']}张量头；payload {evidence['base_payload_bytes']:,}字节", "固定revision的whole SHA/资产/索引；未构造LLM"],
            ["独立wheel缓存", f"15份，{evidence['wheel_bytes']:,}字节，独立完整SHA/ZIP身份通过", "部分完整文件复用原pip下载；缓存采集不是新模型推理或完整安装时长"],
            ["实际环境", evidence["environment_source"] + f"；{evidence['imported_runtime_files_rehashed']}已导入模块/已映射目标库文件重读", "当前pip check/固定CPU导入与原环境不变通过；非主机driver或未来惰性加载库的全量证明"],
            ["旧证据与布局", "49 seal/12072项保持；9集中入口有效", "只证明原字节/布局保持，不把封存哈希当全部历史语义结论通过"]]),
            "links": [link("原完整Python绑定", WORK / "002-当前软件回归/python-first-binding.json"),
                link("220例来源与SQL", WORK / "004-纠错材料/data-independent-v1.json"),
                link("真实mask", WORK / "005-真实分词预检/mask-preflight-v1.json"),
                link("完整环境分词交叉", WORK / "005-真实分词预检/training-tokenizer-crosscheck-v1.json"),
                link("固定模型独立身份", WORK / "003-环境与基础权重/model-independent-v1.json"),
                link("独立环境准入", WORK / "003-环境与基础权重/environment-admission.json"),
                link("完整缓存独立重读", WORK / "008-CUDA完整依赖缓存/wheel-cache-independent-v1.json")]},
        {"title": "单项问题与限定修复", "table": (["问题", "现状", "关闭范围"], [
            ["001 评测查询/追问未隔离", "真实红测接受→修后拒绝", "限定主实验入口字段与文件hash保护；其他schema/语义重叠未获批准"],
            ["002 缺少当前训练环境/基座", "独立环境、完整基座、分词字节交叉完成", "准备门槛限定关闭，真实模型/CUDA/训练质量另验"],
            ["003 venv种子pip不支持report", "真实保留旧22.0.2失败；验证25.3 bootstrap及实际报告", "限定本机准备流程，不重写首失败"],
            ["004 源码元数据误当prefix安装", "按实际locate_file/sys.prefix分离本地安装与源码可见性", "原普通/原生环境未改；不借其他用户环境"],
            ["005 检查点范围误计", "原493输入与新增2评测分开绑定", "不把历史完整回归称新增输入重跑"],
            ["006 官方索引相对URL", "规范化后15份精确依赖元数据登记成功", "元数据不代替完整wheel验证或安装"],
            ["关联C52-001 CLI假阳性", "旧4次实际是ModuleNotFoundError，原通过结论撤回", "v2 4组8次正常/包装CLI精确类型、原因及退出码匹配；不证明实模hook"]]),
            "links": [link("C51-001", OUT / "问题单/001-查询与追问评测未进入训练隔离.md"),
                link("C51-002", OUT / "问题单/002-当前缺少项目训练环境和可训练基础权重.md"),
                link("C51-003", OUT / "问题单/003-系统venv种子pip不支持安装报告.md"),
                link("C51-004", OUT / "问题单/004-包盘点误把源码分发当虚拟环境安装包.md"),
                link("C51-005", OUT / "问题单/005-检查点误认为回归快照自动包含新评测文件.md"),
                link("C51-006", OUT / "问题单/006-官方索引相对链接未规范化导致依赖登记失败.md"),
                link("C52-001与撤回说明", C52 / "审计/问题单/001-CLI导入失败被误当门禁拒绝.md")]},
        {"title": "失败、退役与审计纠错", "paragraphs": [
            "首轮pip不支持安装报告、源码元数据盘点、检查点范围和官方相对URL失败均保留原源码/日志。C52旧CLI绿色回执也原样保留并明确撤回，不删除不利证据，不把导入错误当目标门禁生效。",
            "原模型snapshot成功退出0并独立确认完整身份后，第一片重复补充下载才退役（143）；65分段及partial保留。原pip在15份相同wheel独立完整验证且目标仍仅seed包后被明确替代：子-15/父1，v3原failed回执保留；v4在原父子真实退出后才安装。两个决定均基于等价完整资产就绪，没有整轮墙钟截止，也不停止他人进程。"],
            "links": [link("第一片重复传输退役", WORK / "003-环境与基础权重/range-first-retirement-v1.json"),
                link("原网络解析退役", WORK / "003-环境与基础权重/environment-v3/operator-retirement-v1.json"),
                link("原v3 failed", WORK / "003-环境与基础权重/environment-v3/environment-v3.json"),
                link("修后正常CLI对照", C52 / "审计/工作目录/004-真实执行准入负控/cli-v2/admission-cpu-v2.json")]},
        {"title": "未充分解决与下一步", "paragraphs": [
            "C52材料是11个已知类别的22条新合成开发问句，非独立真人留出；训练目标也为脚本。C19-P1一般动作语义、真实模型时间/状态/人类证据理解、自然度及更广迁移仍开放。自由对话人声、物理麦克风、中文ü/声调口型、跨OS PAD与多日端到端仍未验收。",
            "C52固定同一BF16底模/分词器、同STYLE_HINT、认知禁适配；前后各66试次/132SQL/134次generate（含2预热），两阶段268；保存/独立重载另2次generate及2次probe直接forward。44优化步、176训练/44开发；训练/开发前向另核，不把probe数当全部forward数。",
            "先封存本轮，再冻结全部真实执行输入。按当时空闲显存/利用率选择一张GPU并绑定物理UUID，逐阶段独立进程、退出与GPU释放核验、证明提交后才进入下一阶段。实际token、消息、分析输出与LoRA层状态逐项保留；采证I/O计入接口计时，不当纯推理吞吐。",
            "任何不实实际发送/承诺、代拟/小说保留损失、来源或输入匹配失败都完整报告。单代理精确span审阅不是独立人评；loss、重载、机械计数与准备通过均不批准默认切换或代际跃迁。远期Goal保持active。"],
            "links": [link("C52固定协议", ROOT / "evals/interaction/cycle-52/correction-transfer-protocol.json"),
                link("C52实际执行指南", C52 / "真实执行接续.md"),
                link("前轮未通过的自然语言实验", prior / "系统审计与推进报告.md"),
                link("远期目标与验收路线", BASE.parent / "远期目标与验收路线.md")]},
    ]
    metadata = module.render(OUT, "C51 系统审计与训练准备报告",
        generated + " · 源 " + evidence["head"][:12] + " · 独立准备证据 " + sha(evidence_path)[:12],
        "准备门槛限定通过；实模/CUDA/真人质量未验收，默认不切换", sections, prior / "系统审计与推进报告.html")
    metadata.update(system_evidence_sha256=sha(evidence_path), builder_sha256=sha(Path(__file__)),
        renderer_sha256=sha(renderer), CSS_source_sha256=sha(prior / "系统审计与推进报告.html"),
        MD_sha256=sha(OUT / "系统审计与推进报告.md"), HTML_sha256=sha(OUT / "系统审计与推进报告.html"),
        scope="measured preparation only;display/link check and final seal still separate")
    (OUT / "report-render-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    print("C51 MD/HTML rendered from final measured preparation evidence;display/final seal pending")


if __name__ == "__main__":
    main()

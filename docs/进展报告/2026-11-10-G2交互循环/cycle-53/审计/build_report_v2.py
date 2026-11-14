"""Measured C53 CPU audit and scoped loader repair report."""
from datetime import datetime, timezone, timedelta
import importlib.util
import json
import os
from pathlib import Path
from avatar.lab.common import sha, write_json

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
AUDIT=BASE/"审计"
WORK=AUDIT/"工作目录"


def main():
    evidence_path=AUDIT/"收尾核验/system-evidence.json";e=json.loads(evidence_path.read_text())
    assert e["verified"] and e["new_LLM_generations"]==e["new_training_steps"]==e["GPU_allocations"]==0
    assert not (AUDIT/"系统审计与推进报告.md").exists() and not (AUDIT/"系统审计与推进报告.html").exists()
    prior=BASE.parent/"cycle-50/审计";renderer=prior/"render_report.py"
    spec=importlib.util.spec_from_file_location("c50_pure_renderer_c53",renderer);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    def link(label,path):return label,os.path.relpath(path,AUDIT)
    sections=[
        {"title":"结论与范围","paragraphs":[
            "C53在C52失败adapter继续隔离的条件下，完成CPU训练材料结构审计，并复现/修复主lab加载准入的逐行来源校验缺口。当前源码完整Python2548通过/1跳过，494输入与Git及执行前后字节一致；不是复用旧C51结果。",
            "3组完整176/44克隆材料均复现旧加载器接受、修后拒绝，原176/44仍接受；修后真实CPU分词220序列与原C51同SHA。本轮0新LLM生成、0训练步、0GPU分配。工程完整性修复不等于模型质量提升，也未确定C52退化原因。"],
            "links":[link("系统独立重核",evidence_path),link("完整数据旧新加载对照",WORK/"002-加载准入修复/independent-admission-v1.json"),
                link("前轮失败适配报告",BASE.parent/"cycle-52/审计/系统审计与推进报告.md")]},
        {"title":"材料结构实测","table":(["指标","训练","开发"],[
            ["记录数","176","44"],["最终目标字面种类","11","11；与训练共享全部11种"],
            ["末轮追问字面种类","44","11"],["完整对话精确种类","176","44；跨split交集0"],
            ["数字归一化完整对话种类","44","11；跨split交集0"],
            ["监督tokens（含EOS）","3936 / 全序列145692","984 / 全序列36428"],
            ["含历史快照标记","176/176","44/44"]]),
            "paragraphs":[
                "11类各训练16/开发4，每类只有一个固定脚本目标；全部220材料来自实际Avatar/SQLite流程配合显式脚本teacher，非真实模型或独立人评目标。记录条数不能当作独立措辞数。",
                "数字归一化只把每段十进制数字替换为<N>，会抹掉数值含义，不能证明语义等价。相同目标跨split出现不自动等于数据污染；这些是结构局限而非退化因果。启动前侦察已知11目标，正式审计没有冒称盲假设。"],
            "links":[link("原始结构测量与故障观测",WORK/"001-训练材料结构/structure-v1.json"),link("执行前指标协议",WORK/"001-训练材料结构/protocol-v1.json")]},
        {"title":"加载修复与当前验证","table":(["项目","结果","边界"],[
            ["原加载器回归","修前6失败/2通过","实际准入测试，首失败保留"],
            ["修后定向","11通过","含原训练隔离控制；非新实模收益"],
            ["当前完整Python","2548通过/1跳过；494输入","pytest181.26s；driver含收集182.172s"],
            ["原完整数据","176/44仍接受","原文件/manifest与封存没有改写"],
            ["完整克隆故障","3旧接受→3新拒绝","失真行hash、重算hash的eval原文、换system的跨split重复"],
            ["原两种内容hash范围","均兼容","普通不含system；C51全messages"],
            ["当前真实CPU分词","220序列与原同SHA","3936训练监督tokens；CUDA未初始化"],
            ["未来步骤日志","已加sample_ids/监督量","仅实现，未新跑GPU，不批准实际采证"],
            ["旧证据与布局","51 seal/12418项，9入口不变","旧seal不认证当前新源码，当前另有完整回归"]]),
            "paragraphs":[
                "现在加载时先核真实行结构与声明内容hash，兼容两种既有范围；按实际非system对话防跨split重复，再对当前评测材料重筛，并核开发计数。更新整文件manifest不能绕过失真的逐行来源；重算行hash也不能塞入已保护评测原文。",
                "模板重复/近重复属于导出选择规则，已有材料可能有意重复，加载时不以此推翻既有导出；实际跨split重复单独严格拒绝。当前修复只覆盖主lab加载入口，不认证所有训练入口、来源许可或语义家族隔离。",
                "新训练日志在microbatch loss/反传成功后追加样本ID与监督token，优化器步成功后落盘；不改抽样/loss/优化算法。C52旧日志没有这些字段，不能回填或假称可恢复实际顺序。真实新日志采证仍需后续预登记训练。"],
            "links":[link("当前完整回归绑定",WORK/"004-当前软件回归/python-first-binding.json"),
                link("修后定向日志",WORK/"002-加载准入修复/targeted-after-fix-v1.log"),
                link("当前真实分词证明",WORK/"005-修后真实分词/current-tokenization-v1.json")]},
        {"title":"单项审计与后续优先级","paragraphs":[
            "001材料目标/上下文覆盖有限：开放，下一步以新资料和反事实对照测量，不猜测因果或盲目增加步数。002日志样本身份：实现已补，真实训练未验，保持开放。003逐行来源信任：当前主lab准入限定关闭；原源、6红2绿、原文件与独立3组完整对照保留。",
            "P0保持C52失败adapter隔离和默认模型不变，禁止改旧封存/旧金标、重跑旧阶段或挑选有利重复。P1下一轮先登记更丰富且有条件/反事实差异的开发材料及目标审核，CPU来源/隔离/分词通过后再注册GPU训练对照，并验证新样本日志。已看过的C52题永远是开发诊断，不重新叫独立留出。",
            "004报告窄屏末列首轮实际失败，原报告/截图/回执保留。v2采用手机固定表格列宽，真实双视口复测另核；不把样式声明当成功。",
            "P2继续一般动作语义、真实来源/时效、客户端ACK与人类行为区别；独立人评、自由人声/物理麦克风、ü/声调口型、跨OS PAD、多日端到端仍开放。当前没有整体代际跃迁批准，Goal保持active。"],
            "links":[link("问题001",AUDIT/"问题单/001-合成目标与上下文覆盖有限.md"),
                link("问题002",AUDIT/"问题单/002-优化日志缺少实际样本身份与监督量.md"),
                link("问题003",AUDIT/"问题单/003-加载器信任未复核的逐行来源哈希.md"),
                link("问题004与显示复测",AUDIT/"问题单/004-报告窄屏表格末列无法完整阅读.md"),link("过程进展",BASE/"进展.md"),link("远期目标",BASE.parent/"远期目标与验收路线.md")]}
    ]
    generated=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")
    meta=module.render(AUDIT,"C53 系统审计与训练准入修复报告",generated+" · 源 "+e["head"][:12],
        "当前加载完整性限定修复；模型质量与退化因果未批准",sections,AUDIT/"工作目录/006-报告显示修复/report-style-v2.html.txt")
    meta.update(system_evidence_sha256=sha(evidence_path),builder_sha256=sha(Path(__file__)),renderer_sha256=sha(renderer),style_sha256=sha(AUDIT/"工作目录/006-报告显示修复/report-style-v2.html.txt"),
        MD_sha256=sha(AUDIT/"系统审计与推进报告.md"),HTML_sha256=sha(AUDIT/"系统审计与推进报告.html"))
    write_json(AUDIT/"收尾核验/report-render-metadata.json",meta)
    print("C53 measured MD/HTML built;0newLLM/GPU;display/final seal pending")


if __name__=="__main__":main()

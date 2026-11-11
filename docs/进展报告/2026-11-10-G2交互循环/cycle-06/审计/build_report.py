"""Build a paired audit snapshot from archived positive and negative evidence."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
EVIDENCE=HERE.parent/'实验'


def build():
    read=lambda name:json.loads((EVIDENCE/name).read_text())
    perf=read('cache-performance-final.json');dev=read('conservative-component-dev.json')
    prospective=read('conservative-prospective.json');exact=read('default-final-exact-proof.json')
    assert perf['engineering_gate_passed'] and perf['exact_outputs']
    assert dev['engineering_gate_passed'] and dev['actual_component_matches_reanalysis']
    assert prospective['execution_complete'] and not prospective['engineering_gate_passed']
    assert exact['exact_all_fields'] and exact['exact_cases']==240
    tests=(EVIDENCE/'python-full-final.log').read_text().strip().splitlines()[-1]
    seconds=lambda arm:perf['summary'][arm]['median_seconds']
    lines=['# 第六轮系统审计与推进报告','','日期：2026-11-11（上海时间）。作者：spinner-bot。基线45840bd。','',
        '## 已启用的推进','',
        f'生产口型保留原提峰和标签规则，仅缓存重复使用的频率网格/复指数，保持原求和顺序。固定9轮、单逻辑CPU和单数值线程，14条路线记录的分析中位耗时{seconds("baseline"):.6f}→{seconds("candidate"):.6f}秒，加速{perf["median_speedup"]:.3f}倍。所有完整输出哈希一致，冷遍历也已保存。',
        '输入为6条已知合成波形的两条路线（12条记录，部分波形重复）和两条已归档公开朗读音频，仅验证分析性能和输出一致性，没有真人音素标签。计时包含LipSyncEngine.analyze调用，不含加载/解码、TTS、模型生成、网络或页面播放，不能宣布整轮对话提速。',
        f'缓存上限8项，最终实际{perf["cache"]["currsize"]}项；数组只读，键仅为频率网格尺寸和系数数量，未缓存音频、LPC系数或用户输出。已有并发、污染隔离、边界与逐位参考检查。默认240条已知路线的全部四字段（含mouth_open）与第五轮完全一致。','',
        '## 质量分支：失败就保留失败','',
        '先冻结roots400、dense10、fallback50三候选与逐项门槛。roots400组件/网页分别12/16场景退步；dense10为4/2；fallback50网页改善，组件把2个未知帧改成错误确定标签。全部未通过，原新参数集保持封存。',
        '依据已知失败另冻结F1决策区一致修订，不改标签/新输入：旧单峰和根估计F1在现有分类器三个F2区域上须同意，完整旧峰对直接保留。实际组件开发回放与重分析逐帧一致后，先提交选择，才首次运行新80波形/路径。','',
        '| 数据 | 路径 | 标签帧：旧→候选 | F2缺失：旧→候选 | 新增未知转错 |',
        '| --- | --- | --- | --- | --- |']
    for label,report in [('已知开发',dev),('新参数首次',prospective)]:
        for route,title in [('component_native_rate','组件原采样率'),('web_analysis_16k','网页16k')]:
            a,b=report['summary'][route].values()
            lines.append(f'| {label} | {title} | {a["frame_accuracy"]*100:.2f}%→{b["frame_accuracy"]*100:.2f}% | {a["missing_f2"]}→{b["missing_f2"]} | {b["newly_wrong_from_unknown"]} |')
    lines += ['',
        '开发每路径120信号/6720中段帧，新参数每路径80信号/4480中段帧；新参数的采样率、共振点、带宽、基频、幅度与种子都在实验前冻结，波形与旧网格不同，仍同属解析合成家族。首次新参数组件出现1个未知转错，门槛失败；网页无此问题、总分提高、没有总分场景退步或突降增加，均不能抵销失败。',
        '失败后不再对这批新参数调阈值。候选已从生产LipSyncEngine参数移出，留在avatar.lab.ConservativeLipSyncExperiment供研究重放，Avatar、网页语音、CLI没有接入。生产仍用旧规则加缓存，没有修改默认采样率或宣称中文/真人精度通过。','',
        '## 单项审计','',
        '| 编号 | 状态 |', '| --- | --- |',
        '| [G2C6-001](issues/G2C6-001.md) | 首轮补峰候选将未知改成错误确定标签；原候选拒绝，开发修订不追认原通过 |',
        '| [G2C6-002](issues/G2C6-002.md) | 修订在封存输入仍失败；隔离到lab，不开默认，不继续用此验证调参 |','',
        '## 全量与实际版本','', tests+'。最终语音相关浏览器9项通过。最终生产源码缓存/扩展点经过再次9轮性能、逐帧默认回归；旧性能记录和候选阶段973测试快照均另存。前端产品代码、LLM/记忆/动作、ASR及默认模型没有本轮新功能变更。',
        f'最终性能源码HEAD：{perf["source_head"]}；质量新参数源码HEAD：{prospective["source_head"]}。各报告均含源文件/协议/输入与输出哈希，不把不同阶段冒称单一HEAD。新提峰候选未通过，不等于性能优化未通过；两条门槛独立报告。','',
        '## 后续优先级与限制','',
        'P1：另开周期验证分帧样本索引与输出时钟的对应关系，重点检查22050Hz等非整数hop采样率；先用样本数定义可测误差，不把软件时钟检查当物理音画同步验收。P1：下一质量候选须重新冻结输入，并补有来源真人音素标注；本轮80波形已成为已知回归。P2：继续形象嘴型和设备端到端体验。',
        '第五轮003、第二轮一般归属/身体边界、模板充分性和多日运行、ü/声调/真人口型/正式渲染等限制继续开放；没有宣布项目远期目标或整体代际跃迁已完成。本轮CPU完成，没有新GPU进程。','',
        '## 方法参考','',
        '候选设计参考[Praat官方Formant说明](https://fon.hum.uva.nl/praat/manual/Sound__To_Formant__burg____.html)对频率上限、重采样与预加重的讨论；本项目实验继续使用原LPC，未实现完整Praat分析。多项式系数/求根接口核对[NumPy官方roots文档](https://numpy.org/doc/stable/reference/generated/numpy.roots.html)。固定带宽和一致性门槛为本项目受测启发式，没有引用外部资料代替本地实验。','',
        '## 证据入口','']
    names=['formant-dev.json','fallback-refined-dev.json','conservative-component-dev.json','conservative-prospective.json','cache-performance.json','cache-performance-final.json','default-final-exact-proof.json','default-final-regression.json','python-full-final.log','browser-audio-final.log','cache-tests.log','lab-isolation-tests.log']
    lines += [f'- [{name}](../实验/{name})' for name in names]
    lines += ['','[全过程记录](../进展.md)；[本轮计划](../计划.md)。','']
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines))
    def inline(s):return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escape(s))
    body=[];in_table=False
    for line in lines:
        if line.startswith('| ---'):continue
        if line.startswith('|'):
            cells=line.strip('| ').split(' | ')
            if not in_table:body.append('<div class="table-wrap"><table>');in_table=True;tag='th'
            else:tag='td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(cell)+f'</{tag}>' for cell in cells)+'</tr>');continue
        if in_table:body.append('</table></div>');in_table=False
        if line.startswith('# '):body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第六轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border:1px solid #dee7ee;text-align:left;vertical-align:top}th{background:#e4edf7}.table-wrap{overflow:auto}a{color:#155aa7}@media(max-width:600px){main{padding:16px}h1{font-size:25px}table{font-size:14px}}</style><main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    for href in re.findall(r'href="([^"]+)"',html):
        if not href.startswith('https://'):assert (HERE/href).exists(),href
    paths=list(EVIDENCE.iterdir())+list((HERE/'issues').glob('*.md'))
    manifest={p.relative_to(HERE.parent).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(manifest)} evidence files; local links valid')


if __name__=='__main__':build()

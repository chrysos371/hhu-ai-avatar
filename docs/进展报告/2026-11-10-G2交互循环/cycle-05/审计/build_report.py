"""Rebuild paired MD/HTML from the archived analytic evidence; no dependencies."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
EVIDENCE=HERE.parent/'实验'


def build():
    read=lambda name:json.loads((EVIDENCE/name).read_text())
    dev=read('analytic-dev-paired.json')
    validation=read('analytic-validation-paired.json')
    final=read('analytic-final-paired.json')
    assert all(report['engineering_gate_passed'] for report in [dev,validation,final])
    assert final['candidate_split_use']=='regression_replay'
    tests=(EVIDENCE/'python-full-final.log').read_text().strip().splitlines()[-1]
    lines=['# 第五轮系统审计与推进报告','','日期：2026-11-11（上海时间）。作者：spinner-bot。承接第四轮515acf2。','',
        '## 已推进的行为','',
        '口型默认取消每0.3秒强制的装饰闭口，持续发声不再按时钟无依据地合嘴；真实静音检测、静音后的平滑约束保留。显式close_every正数仍可使用装饰效果，None为默认；不把装饰闭口叫检测到自然停顿。',
        '组件增加窗口、跳步、平滑与阈值验证；输入须为归一化单声道有限PCM和可表示的采样元数据，预取消在分帧前传播。整数最小值溢出、极大有限窗口和超长闭口周期经反向检查再修复。没有改动LPC/元音标签或组件默认采样率。','',
        '## 解析基准与独立性','',
        '数学定义三个共轭极点对合成信号，五个标签仅为现有代码的a/e/i/o/u锚区，绝非真人中文元音金标。16000/24000/48000Hz、两档RMS、白噪声和三档基频谐波形成每路径120信号，组件原采样率与网页16k分析分开。原波形哈希、逐帧输出、源码、固定轮数与失败全部归档。',
        '开发种子11；首次验证种子29。种子只影响白噪声，因此每路径验证120中90谐波是已知确定性回归，30白噪声才是新随机实现。补充说明在首次验证前提交，未改变原网格/标签/门槛。最终数值边界修复后再跑种子29明确标regression_replay，新增未见样本数为0。没有真人独立验收。','',
        '## 配对结果','',
        '| 数据 | 路径 | 旧突降→新突降 | 标签帧准确率（两组相同） | F2缺失（两组相同） |',
        '| --- | --- | --- | --- | --- |']
    for label,report in [('开发',dev),('首次验证',validation)]:
        for route,title in [('component_native_rate','组件原采样率'),('web_analysis_16k','网页16k')]:
            a,b=[report[name][route] for name in ['baseline_summary','candidate_summary']]
            lines.append(f'| {label} | {title} | {a["sudden_closures"]}→{b["sudden_closures"]} | {a["vowel_frame_accuracy"]*100:.2f}% | {a["missing_f2"]}/720采样点 |')
    lines += ['',
        '每一条配对信号波形相同；所有帧的时间、元音与能量完全相同，静音/低噪声均闭口，没有任何标签场景退步。变化仅为默认装饰动作与输入边界，不宣称识别精度提高。按协议突降为中段开口低于同段中位数0.25倍、只统计中位数≥0.3的帧；移除突降会使少数样例越过资格门槛，分母变化已保留，主要比较绝对次数和逐帧不变量。',
        '首次验证组件F1/F2独立绝对误差中位数21.23/24.27Hz，网页17.66/15.66Hz，但漏峰和大错仍存在；合并中位数不代表尾部或所有帧通过。分析时间为当时CPU负载下观察值，含配对实验并非性能专项，不据微小差异宣布加速。','',
        '## 单项审计','',
        '| 编号 | 结论 |', '| --- | --- |',
        '| [G2C5-001](issues/G2C5-001.md) | 新夹具谐波截止漏项；先复现后修复，旧v1原样留存，不参加正式门槛 |',
        '| [G2C5-002](issues/G2C5-002.md) | 无声源依据的周期闭口；已关闭默认，开发/验证/最终回归通过 |',
        '| [G2C5-003](issues/G2C5-003.md) | LPC/元音识别质量和采样率敏感仍开放；统一16k总体升分却有10/120对退步，不更改组件默认 |',
        '| [G2C5-004](issues/G2C5-004.md) | 输入、参数、预取消及数值溢出边界；新增5项再失败再修复，66项音频关联通过 |','',
        '## 回归与范围','',tests+'。语音、端点和流式浏览器9项通过（27.0秒），对应本轮前一候选版本；最终数值修复后66项音频关联及全量重新通过，最终解析全网格回归逐帧不变量维持。前端产品源码未改，第四轮构建/lint及第三轮33前端单测为历史记录，不伪称本轮重跑。',
        '四条单项记录中003仍开放；ü与声调未实现，真实中文音素标签、音画对齐/物理麦克风/真人视觉自然度和正式形象未验收。第四轮真人事实/动作、第三轮模板充分性、第二轮一般归属/身体边界限制继续保留。没有训练/模型切换，也没有占用GPU，本轮用CPU固定样本，不设墙钟截止。','',
        '## 下一循环优先级','',
        'P1：冻结新的声学参数组合及有来源真人音素标注，针对漏峰/采样率敏感做候选对照；不得只优化总体均分或把重复确定性数据称作未见验证。P1：来源删除与真实操作权限继续作为全量回归门槛。P2：接通更丰富的形象嘴型及播放时钟量化，物理设备与真人体验有条件时另验收。','',
        '## 原始资料','']
    names=['analytic-dev-v1-baseline.json','fixture-before.log','fixture-after.log','lipsync-before.log','numeric-edges-before.log','numeric-edges-after.log','analytic-dev-v2-baseline.json','analytic-dev-v2-candidate.json','analytic-dev-paired.json','analytic-validation-baseline.json','analytic-validation-candidate.json','analytic-validation-paired.json','analytic-final-candidate.json','analytic-final-paired.json','python-full-final.log','browser-audio.log']
    lines += [f'- [{name}](../实验/{name})' for name in names]
    lines += ['','[全过程记录](../进展.md)；[计划](../计划.md)。','']
    md='\n'.join(lines);(HERE/'系统审计与推进报告.md').write_text(md)
    def inline(s):return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escape(s))
    body=[]
    for line in lines:
        if line.startswith('# '):body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line.startswith('| ---'):continue
        elif line.startswith('|'):body.append('<div class="row">'+inline(line.strip('| ').replace(' | ',' · '))+'</div>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第五轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1000px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p,.row{overflow-wrap:anywhere}.row{padding:12px;background:white;border-bottom:1px solid #dee7ee}a{color:#155aa7}@media(max-width:600px){main{padding:16px}h1{font-size:25px}}</style><main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    for href in re.findall(r'href="([^"]+)"',html):assert (HERE/href).exists(),href
    paths=list(EVIDENCE.iterdir())+list((HERE/'issues').glob('*.md'))
    manifest={p.relative_to(HERE.parent).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(manifest)} evidence files; local links valid')


if __name__=='__main__':build()

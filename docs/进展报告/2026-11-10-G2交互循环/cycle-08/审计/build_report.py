"""Build the active-goal playback audit from archived successes and failures."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
EVIDENCE=HERE.parent/'实验'


def build():
    read=lambda name:json.loads((EVIDENCE/name).read_text())
    before=read('before-clock.json');summary=read('playback-repeat-summary.json')
    prefixes=['events','repeat-1','repeat-2','repeat-3']
    clocks=[read(name+'-clock.json') for name in prefixes]
    assert not before['completed'] and summary['all_passed']
    for prefix,clock in zip(prefixes,clocks):
        assert clock['completed'] and all(row['gate']['passed'] for row in clock['cases'])
        assert all(row['passed'] for row in clock['controls'])
        for suffix in ['segments','prefetch-stop']:assert read(prefix+'-'+suffix+'.json')['completed']
    python=(EVIDENCE/'python-full.log').read_text().strip().splitlines()[-1]
    worst=max(case['gate']['p95AbsoluteLagMs'] for run in clocks for case in run['cases'])
    lines=['# 第八轮系统审计与推进报告','','日期：2026-11-11（上海时间）。作者：spinner-bot。起点74eac2b。远期目标保持active。','',
        '## 远期目标与本轮进展','',
        '已将持续目标登记为active，并在[远期路线](../../远期目标与验收路线.md)写入分层验收。目标是有实验支撑的稳定听→思→演→记闭环；每轮设指标、实现、实验、审计、修复、复测、留痕后进入下一轮。未以阶段测试数量宣布远期目标或整体代际提升完成。',
        '本轮修复播放器事件处理：只有所拥有src与当前选中资源一致，且真实paused/ended/error状态符合事件含义时才改变状态。释放后的play、仍播放时的pause、未结束时的ended、旧资源error都不能复活/暂停/提前推进/释放当前播放。正常暂停、继续、结束和当前错误对照保持。','',
        '## 从失败到修复','',
        '| 检查 | 原始结果 | 处理与复测 |','| --- | --- | --- |',
        '| 媒体事件夹具初版 | JSDOM没有MediaError getter，7项未进入播放器 | 修正可恢复属性模型，原日志保留，不计为7个功能缺陷 |',
        '| 未改生产代码的事件对照 | 先4败/3过；加入旧currentSrc错误后5败/3过 | 校验资源身份与实际媒体状态，连既有播放器12项通过 |',
        '| 首次浏览器 | 时钟、注入迟到play后停止状态失败；完整三段顺序通过 | 原始采样与失败部分JSON保留 |',
        '| 修复后首次浏览器 | 3项通过 | 额外冻结3轮同协议观察，分别3项通过，不选最好一次 |',
        '| 全量 | Python1006通过/1跳过；前端41通过 | lint/build通过；默认浏览器15通过/7显式跳过，新增3项已单独实跑 |','',
        '## 实际媒体时钟测量','',
        'Chromium实际解码播放本机生成PCM，测试接口提供已冻结的时间轴。800个10ms帧用唯一三位开口码对应DOM值，同时检查SVG椭圆属性，独立于LPC识别。每场景固定48次RAF，预先排除2次预热，暂停/结束/seek状态全部保留；每场景须至少30个有效样本。',
        '滞后定义为(audio.currentTime−所显示帧时间)×1000，使用绝对值p95≤50ms、最大≤100ms门槛；单位为媒体时间，不是物理扬声器/显示器延迟。源代码与实际服务JS包哈希一起归档，已核对四次修复后记录均对应最终源文件和服务包。','',
        '| 同机观察 | 正常速率p95 | 半速p95 | 双速p95 | 向前seek p95 | 向后seek p95 |',
        '| --- | --- | --- | --- | --- | --- |']
    for name,run in [('初始未修复',before),*zip(prefixes,clocks)]:
        values=[case['gate']['p95AbsoluteLagMs'] for case in run['cases']]
        lines.append('| '+name+' | '+' | '.join(f'{value:.3f}ms' for value in values)+' |')
    lines += ['',
        f'初始双速p95=50.112ms，超预设门槛，保留为失败。修复后四次观察全部通过，各场景最差p95={worst:.3f}ms；SVG几何均与控制值吻合。此结果不能证明初次延迟的根因已被事件校验消除，002继续开放；同一宿主机重复观测不称独立设备验证。',
        '暂停在首个采样RAF即闭口，正常结束/停止检查通过。三段最终回复完整按顺序播放，预取停止后即使注入迟到play并完成旧请求，也不启动下一段。注入明确标记为受控事件，不声称测得浏览器自然发生竞争的频率。','',
        '## 单项审计','',
        '| 编号 | 当前结论 |','| --- | --- |',
        '| [G2C8-001](issues/G2C8-001.md) | 资源/媒体状态不一致事件已修复；单元控制、真实浏览器受控注入与正常事件回归通过 |',
        '| [G2C8-002](issues/G2C8-002.md) | 初次双速p95超标；后续固定观察通过，根因与复杂历史场景仍待研究，继续开放 |','',
        '## 全量与证据边界','',python+'；前端41通过，构建5.91秒与lint通过；默认离线浏览器15通过/7跳过（37.2秒）。事件修后首次3通过（23.7秒），固定额外三轮各3通过（23.9/23.6/23.6秒）。',
        '新媒体实验拦截语音响应以隔离前端，实际PCM/媒体播放和SVG属性是真实执行；真实SpeechService既有浏览器测试另跑，不能将受控语音API当Edge-TTS/真实LLM/音素质量验收。控制模型提供方仅为lab夹具，新增覆盖文本只在显式实验开关中生效，默认生产模型/配置没有更换。',
        '测试夹具还修复了workspace/project路径混淆和卸载先于mock恢复的顺序，首启失败与清理告警均保留。没有删除旧失败、放宽50ms门槛、重复到成功再隐藏其余结果。','',
        '## 下一循环','',
        'P1：测量逐帧更新对聊天父组件与长历史渲染的影响，先固定事件轮数和对照，再考虑局部订阅或其他渲染改造。P1：扩大实际播放/段间故障/取消与设备差异，继续记忆来源/实际操作回归。P2：真人音素标注、正式形象协议和目标设备体验。',
        '真人口型、ü/声调、物理音画闭环、一般生成边界、模板充分性与多日稳定仍未验收。第六轮提峰候选继续lab隔离，本轮没有GPU模型任务。目标保持进行中，未标记complete。','',
        '## 方法参考','',
        '事件状态核对参考[HTML媒体标准](https://html.spec.whatwg.org/multipage/media.html#mediaevents)的资源/状态模型；当前修复证据来自本地测试。下一步渲染订阅研究查阅[React官方useSyncExternalStore文档](https://react.dev/reference/react/useSyncExternalStore)，尚未将该机制视为已证实的延迟修复。','',
        '## 原始资料','']
    names=['media-events-before.log','media-events-fixture-fixed.log','media-source-before.log','media-events-after-clean.log','before-clock.json','before-prefetch-stop.json','before-segments.json','events-clock.json','events-prefetch-stop.json','events-segments.json','playback-repeat-summary.json','repeat-1-clock.json','repeat-2-clock.json','repeat-3-clock.json','frontend-full.log','python-full.log','browser-default-final.log','frontend-build-final.log','frontend-lint-final.log']
    lines += [f'- [{name}](../实验/{name})' for name in names]
    lines += ['','[全过程记录](../进展.md)；[本轮计划](../计划.md)。','']
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines))
    def inline(s):return re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<a href="\2">\1</a>',escape(s))
    body=[];table=False
    for line in lines:
        if line.startswith('| ---'):continue
        if line.startswith('|'):
            cells=line.strip('| ').split(' | ')
            if not table:body.append('<div class="table-wrap"><table>');table=True;tag='th'
            else:tag='td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(cell)+f'</{tag}>' for cell in cells)+'</tr>');continue
        if table:body.append('</table></div>');table=False
        if line.startswith('# '):body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第八轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border:1px solid #dee7ee;text-align:left;vertical-align:top}th{background:#e4edf7}.table-wrap{overflow:auto}a{color:#155aa7}@media(max-width:600px){main{padding:16px}h1{font-size:25px}table{font-size:14px}}</style><main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    for href in re.findall(r'href="([^"]+)"',html):
        if not href.startswith('https://'):assert (HERE/href).exists(),href
    files=list(EVIDENCE.iterdir())+list((HERE/'issues').glob('*.md'))
    manifest={p.relative_to(HERE.parent).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(files) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(f'{len(manifest)} evidence files; local links valid')


if __name__=='__main__':build()

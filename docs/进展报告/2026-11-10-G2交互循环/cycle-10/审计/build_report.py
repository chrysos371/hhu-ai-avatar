"""Rebuild cycle 10 MD/HTML and evidence hashes from archived observations."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
CYCLE = HERE.parent
EV = CYCLE/'实验'


def read(name):
    return json.loads((EV/name).read_text())


def build():
    before = read('before-history.json')
    after = [read(f'after-{n}-history.json') for n in [1, 2, 3]]
    assert before['allCheckpointsObserved'] and not before['completed'] and len(before['violations']) == 6
    for r in [before, *after]:
        assert len(r['turns']) == 100 and all(t.get('result') for t in r['turns'])
        assert all(e['input']['valuesMatch'] and len(e['input']['inputRows']) == 25 for e in r['checkpoints'])
        assert all(c['gate']['passed'] for e in r['checkpoints'] for c in e['clocks'])
        assert r['afterNavigation']['dom']['messages'] == 0
    for r in after:
        assert r['completed'] and not r['violations']
        assert all(e['input']['decisions'] == e['closed']['dom']['closedPre'] == 0 for e in r['checkpoints'])
    old, new = read('cleanup-before.json'), read('cleanup-after.json')
    assert not old['passed'] and len(old['remaining']) == 1 and old['exitCode'] == -15
    assert new['passed'] and not new['remaining'] and new['exitCode'] == 0
    assert all(read('playback-final-'+name+'.json')['completed'] for name in ['clock', 'segments', 'prefetch-stop'])
    lines = ['# 第十轮系统审计与推进报告', '',
             '日期：2026-11-11（上海时间）。作者：spinner-bot。生产起点43806c4。远期Goal保持active。', '',
             '## 本轮结论', '',
             '已修复两项有数据复现的问题：闭合诊断反复序列化/常驻DOM，以及测试helper收到SIGTERM后残留自己临时数据库。完整生产聊天页固定三轮各100回合均通过，不删除或截断当前页面消息。另确认导航后展示历史重置，但后端保留全部200条消息；该交互连续性缺口进入下一循环。',
             'DOM清空不等于所有资源均释放：强制GC后的JS堆仍高于初始，来源尚未分解，继续审计，不据此宣布泄漏或完全回收。有限百轮、受控提供方和本机PCM不作为多日、真实模型语义、物理输入/音画验收。', '',
             '## 冻结协议与采证纠错', '',
             '7d55424先提交1/25/100最终回复、25字符草稿、正常/双速PCM、CDP资源协议。首次夹具在0回合错误要求idle隐藏播放器可见；第二次虽完成100回合，但DevTools无法读取已被正常cancel的SSE响应体，序列化匹配字段也不对。两次记录全部保留，不混作业务故障或有效对照。',
             '9c19e15修正采证：界面仍通过真实本机HTTP/SSE读取，完成后GET同一job的canonical result校对来源；按实际trace.decision的analysis_mode/generation_mode字段计数。协议v2只修记录方式，样本和门槛不变。5614570有效基线在生产改动前完整执行，115.378秒，失败仅为隐藏诊断工作。',
             '输入通过Playwright逐字符insertText，再等下一RAF；记录输入捕获值、下帧DOM值与时间。它是受控文本插入，不是实体键盘/中文IME测量。JSON.stringify包装的计数开销在所有有效前后观测中均保留。', '',
             '## 隐藏工作与有限负载', '',
             '| 最终回复数 | 修前25字符决策序列化 | 修后每轮 | 修前闭合pre | 修后每轮 |',
             '| --- | --- | --- | --- | --- |']
    for count in [1, 25, 100]:
        entry = next(e for e in before['checkpoints'] if e['replies'] == count)
        lines.append(f"| {count} | {entry['input']['decisions']} | 0（3轮） | {entry['closed']['dom']['closedPre']} | 0（3轮） |")
    lines += ['',
              '只抽出ChatTrace，利用native details的toggle状态按需挂载全部五组诊断，关闭即移除内容；保留安全提示、来源、检查和工具。没有为容易通过而删历史，也未做无必要证据的消息memo或更换模型。原ChatPage单测先红后绿，新增测试核对五组原始值及关闭后新来源重开。', '',
              '| 有效观察 | 秒数 | 100回复DOM元素 | GC后堆MiB | 输入下帧p95 | 6场景最差时钟p95 |',
              '| --- | --- | --- | --- | --- | --- |']
    for label, r in [('修前', before), *[(f'修后{n}', r) for n, r in enumerate(after, 1)]]:
        e = r['checkpoints'][-1]
        worst = max(c['gate']['p95Ms'] for e in r['checkpoints'] for c in e['clocks'])
        lines.append(f"| {label} | {r['elapsedSeconds']:.3f} | {e['closed']['dom']['elements']} | {e['closed']['metrics']['JSHeapUsedSize']/1048576:.3f} | {e['input']['p95NextRafMs']:.3f}ms | {worst:.3f}ms |")
    lines += ['',
              '100回复时当前DOM元素2476→1476，修后三轮一致；GC后堆7.451MiB→约6.46MiB为本机观测。输入p95原19.9ms，修后13.6–15.4ms，均远低于预设100ms，未以单次前测和三次同机后测宣称稳定CPU加速或可感知卡顿已消除。各回合请求与界面消息数保持100/200，诊断展开与canonical job决策一致，停止释放src并闭口。', '',
              '## 播放与资源边界', '',
              '实际Chromium播放8秒16000Hz PCM，800个10ms唯一开口码对应媒体时间和SVG几何。每负载正常速率伴随输入、双速不输入，各固定48个RAF，预先排除2个预热和暂停/结束/seek；有效≥30、p95≤50ms/max≤100ms门槛不变。有效基线6场景与修后18场景全部通过，本轮没有证据宣称进一步改善时钟。原第八轮初次50.112ms失败仍按历史证据保留。',
              '每次资源观测前执行三次HeapProfiler.collectGarbage，记录Performance指标、Memory DOM计数及实际页面节点；强制GC改变自然运行条件，结果仅作有限负载描述。方法定义来自[官方CDP browser schema](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json)与[V8 schema](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/js_protocol.json)，所用命令实际执行成功；定义及哈希见cdp-methods.json。', '',
              '| 观察 | 初始DOM元素 | 导航返回DOM元素 | 初始堆MiB | 返回堆MiB |',
              '| --- | --- | --- | --- | --- |']
    for label, r in [('修前', before), *[(f'修后{n}', r) for n, r in enumerate(after, 1)]]:
        initial, returned = r['initial'], r['afterNavigation']
        lines.append(f"| {label} | {initial['dom']['elements']} | {returned['dom']['elements']} | {initial['metrics']['JSHeapUsedSize']/1048576:.3f} | {returned['metrics']['JSHeapUsedSize']/1048576:.3f} |")
    lines += ['',
              '返回空聊天DOM为181，与初始相同；堆并未回到初始，缓存/编译等来源尚未分解，不能叫无泄漏证明。导航通过SPA链接执行，未用整页重载掩盖组件清理。按第一轮首请求ID只读匹配隔离库，仍有100用户/100助手消息和100条ledger，200条角色/正文已逐条与提交输入及canonical回复顺序核对一致；故展示0条属于视图重建缺口，并非本轮懒加载造成后端丢失。', '',
              '## 退出清理：独立失败与修复', '',
              '独立预先冻结cleanup-protocol.json，三轮测量结束后再运行独立helper，确保端口空闲，只向自己PID发送SIGTERM。旧版退出-15，新建1目录/残留1；修后退出0，新建1/残留0。未删除其他历史目录，未触碰用户库。',
              'helper信号处理从后台线程调用shutdown，让serve_forever返回并执行原finally中的server/provider/TemporaryDirectory清理。[Python官方BaseServer.shutdown文档](https://docs.python.org/3/library/socketserver.html#socketserver.BaseServer.shutdown)明确要求与serve_forever处于不同线程；本次实现和退出门槛另有实测。只修改测试helper，不更改生产Web的退出路径。', '',
              '## 单项与系统性评估', '',
              '| 编号/方面 | 结论 |',
              '| --- | --- |',
              '| [G2C10-001](issues/G2C10-001.md) 隐藏诊断工作 | 已修复；前端红/绿与三轮100回合通过 |',
              '| [G2C10-002](issues/G2C10-002.md) 导航连续性 | 已观察视图重置、后端保留；需隐私有效的历史重建与缓存评估 |',
              '| [G2C10-003](issues/G2C10-003.md) helper临时库 | 已修复；旧失败、新通过及默认浏览器回归 |',
              '| 记忆/动作边界 | 本轮未改Python生产逻辑；一般生成归属/身体边界、模板充分性仍开放 |',
              '| 消息与取消 | 100请求/200消息、来源展开、停止与原播放/取消回归保持；未自动截断历史 |',
              '| 证据与版本 | 四份有效历史39项源哈希均匹配各自已提交HEAD；修后三轮前端及包匹配最终前端 |',
              '| 长期/真实设备 | 约112秒每轮，受控提供方；多日、真人音素、物理设备、正式渲染未验收 |', '',
              '上一轮G2C9-002关于完整页面从未测量的部分已由本轮补充，长期与跨设备部分仍开放。helper在三轮后才修复，旧历史记录里的helper哈希有意属于旧版本，不伪称全都等于最后工作区。清理after实测时修复尚在工作区，其HEAD为基线，捕获的helper字节哈希与实现提交604ed7c相符，不能仅凭记录HEAD重建；snapshot-check.json分别核对这些绑定。采证v1无效记录保留，并未作为有效0序列化或来源错误结论。', '',
              '## 回归与下一循环', '',
              '前端50通过（2.12秒、21文件），lint通过，构建4.43秒；默认浏览器15通过/8显式可选跳过（36.5秒）。完整历史研究已另做有效基线1轮及修后固定3轮；原PCM三项另复测通过。4项真实模型/ASR可选服务本轮未重跑。Python生产未改，完整1006通过/1跳过仅为第八轮快照，本轮未重跑Python全量。',
              '下一循环先冻结导航/刷新/取消/删除下的历史重建与缓存留存场景，分解返回后堆增长；让已保留的后台消息在隐私和版本屏障下可审查，不用localStorage缓存敏感trace，不让删除内容复活。并继续真实生成的归属/身体边界与任务充分性研究，不以界面计数替代整体交互质量。GPU按后续实际余量安排，本轮无GPU任务。',
              '远期目标保持active，未标为complete；路线见[远期目标](../../远期目标与验收路线.md)。', '',
              '## 原始资料', '',
              '[过程记录](../进展.md)、[计划](../计划.md)、[有效汇总](../实验/history-summary.json)、[源绑定](../实验/snapshot-check.json)。']
    for p in sorted(EV.iterdir()):
        if p.suffix in ['.json', '.log']:
            lines.append(f'- [{p.name}](../实验/{p.name})')
    lines.append('')
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines))
    def inline(s):
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(s))
    body, table = [], False
    for line in lines:
        if line.startswith('| ---'): continue
        if line.startswith('|'):
            if not table: body.append('<div class="table-wrap"><table>'); tag = 'th'; table = True
            else: tag = 'td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(c)+f'</{tag}>' for c in line.strip('| ').split(' | '))+'</tr>'); continue
        if table: body.append('</table></div>'); table = False
        if line.startswith('# '): body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '): body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line: body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border:1px solid #dee7ee;text-align:left;vertical-align:top}th{background:#e4edf7}.table-wrap{overflow:auto}a{color:#155aa7}@media(max-width:600px){main{padding:16px}h1{font-size:25px}table{font-size:14px}}</style><main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    for href in re.findall(r'href="([^"]+)"', html):
        if not href.startswith('https://'): assert (HERE/href).exists(), href
    inputs = list(EV.rglob('*'))+list((HERE/'issues').glob('*.md'))+[CYCLE/'计划.md', CYCLE/'进展.md']
    manifest = {p.relative_to(CYCLE).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(inputs) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'{len(manifest)} evidence hashes; links valid')


if __name__ == '__main__':
    build()

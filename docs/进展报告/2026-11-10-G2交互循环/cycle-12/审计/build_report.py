"""Rebuild cycle 12 reports from retained fixed gates; preserve failed predecessors."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
CYCLE, EV = HERE.parent, HERE.parent/'实验'

def read(p): return json.loads((EV/p).read_text())

def build():
    external = [read(f'fixed-{i}/external-erase.json') for i in [1,2,3]]
    notification = [read(f'fixed-{i}/notification.json') for i in [1,2,3]]
    for e,n in zip(external,notification):
        assert e['completed'] and len(e['rows']) == 12 and all(not r['oldTraceVisible'] for r in e['rows'])
        assert e['refreshControl']['oldTraceRemoved'] and n['completed'] and len(n['steps']) == 8 and not n['errors']
        assert sum(r['path'].endswith('/changes') for r in n['requests']) == 7
        assert all(s['job']['status'] == 'completed' for s in n['steps'][:2])
        assert n['steps'][2]['messages'] == 0
        assert n['steps'][5]['audio']['paused'] and n['steps'][5]['audio']['src'] is None
        assert n['steps'][6]['draft'] and n['steps'][6]['job']['status'] == 'running'
        assert n['steps'][7]['status'] == 404 and n['steps'][7]['snapshot']['items'][-1]['role'] == 'user'
    restore, load = read('restore/restore.json'), read('history-load/history.json')
    assert restore['completed'] and len(restore['turns']) == 54 and not restore['errors']
    assert len(restore['steps'][2]['ids']) == len(set(restore['steps'][2]['ids'])) == 108
    assert restore['steps'][3]['draft'] and len(restore['steps'][3]['snapshot']['items']) == 109
    assert restore['steps'][-1]['submitted'] == 55
    assert load['completed'] and len(load['turns']) == 100 and load['afterNavigation']['dom']['messages'] == 200
    assert all(c['input']['decisions'] == c['closed']['dom']['closedPre'] == 0 for c in load['checkpoints'])
    for name in ['clock','segments','prefetch-stop']: assert read('playback/'+name+'.json')['completed']
    snapshot = read('snapshot-check.json'); assert snapshot['allPassed']
    issue1 = 'issues/G2C12-001-通知中断期间刷新复活旧显示.md'
    issue2 = 'issues/G2C12-002-外部版本通知与有限验收.md'
    lines = ['# 第十二轮系统审计与推进报告', '',
      '日期：2026-11-11（上海时间）。作者：spinner-bot。基线a8b3754，固定三轮529cba4；远期Goal继续active。', '',
      '## 当前结论', '',
      '已修复第十一轮外部API删除后活动页不清除旧trace的P1缺口，并补齐本轮追加发现的“通知中断后刷新又显示旧内容”。原外部删除探针源码和12帧门槛未变：修前12/12仍见旧trace，修后开发轮及固定三轮每轮0/12。通知恢复、实际PCM播放和真实部分草稿中的外部删除均有浏览器证据。',
      '这些是同机受控提供方的工程结论，不是整体代际跃迁、全网络零延迟、通用模型语义或多日/真实设备验收。历史显示恢复不等于服务重启后的生成语境已接续，下一循环单独冻结该项实验。', '',
      '## 实现与原失败对照', '',
      '| 项目 | 修前或审计失败 | 本轮实现/实测 |', '| --- | --- | --- |',
      '| 外部API删除 | 后端已清原result，活动页12/12 RAF仍见旧trace | 鉴权元数据版本通知；固定3轮各0/12 |',
      '| 通知连接中断 | 新实现首次清空后，焦点/刷新会重新显示private-old | 同步可用性屏障；Hook复现后修复，固定3轮浏览器暂停/恢复通过 |',
      '| 鉴权失败提示 | 已停止重试仍写正在重新连接 | 401/403明确要求使用启动链接重新打开，单元实测 |',
      '| 连接资源 | 原无服务端通知 | 最多4个等待且至少留1普通连接；真实HTTP总连接1/2/32分别验证上限0/1/4、system可用、额外等待429 |', '',
      'GET /api/v1/conversation/changes要求instance_id和revision各一次，沿用token、Host/Origin与响应包络；只含实例和版本元数据，不传事实、转录或trace。已变化立即返回，未变化10秒心跳。成功API响应前检查已提交revision；单个共享只读监测器在有观察者时每100ms检查其他SQLite连接，无观察者时不查库。版本发布取单调最大值，乱序旧检查不能降版本。',
      '客户端每页一个挂起请求，心跳本身不读历史。故障清空旧显示、推进提交epoch并停止旧声音/生成，焦点/显式刷新及迟到回调不能绕过暂停；同版本重连也重读快照，不重放模型或工具。重试为250/500/1000/2000/5000ms上限退避；单次15秒仅为网络操作超时，实验没有墙钟截止。终端鉴权失败停止重试。',
      '普通peer断开仅释放自身通知等待，测试证明不取消无关活跃回合；服务关闭停止共享监测。超过等待容量的页面可能暂停并退避，此设计不保证无限标签页。100ms是监测配置，不是所有端到端网络延迟上界。线程等待与取消机制参考[Python Condition官方文档](https://docs.python.org/3/library/threading.html#condition-objects)、[AbortController官方文档](https://developer.mozilla.org/en-US/docs/Web/API/AbortController/abort)，本地运行Python3.10，未升级依赖。', '',
      '## 固定重复与故障覆盖', '',
      '先提交协议与API 404原失败，再实现；开发轮通过后冻结源文件、探针与服务包，另跑预设三轮，不挑最好一轮。每轮隔离数据库、原探针一项加通知故障审计一项。', '',
      '| 固定轮次 | 原删除探针旧trace可见帧 | 新审计通过步骤 | 元数据请求数 | 总浏览器运行观察 |', '| --- | --- | --- | --- | --- |']
    for i in [1,2,3]:
        text = (EV/f'fixed-{i}.log').read_text()
        total = re.search(r'2 passed \(([^)]+)\)', text).group(1)
        lines.append(f'| {i} | 0/12 | 8 | 7 | {total} |')
    lines += ['',
      '每轮实际覆盖：自然姓名新增及替换均completed、revision未因正常remember递增；仅watch断网而普通快照接口仍可用，焦点/手动刷新仍0行；相同版本恢复且POST回合计数不增；PCM已实际currentTime>0后删除，audio暂停且src清空；观察到非空SSE草稿和running后删除，旧job清除返回404、页面停止生成、当前数据库末项为用户而非助手草稿。没有通过重复模型请求恢复显示。',
      '删除后的404是既有隐私契约：清空旧任务及私有结果，不能为展示cancelled而保留旧结果。首次新探针误期待可查询cancelled，已按契约修正，保留原trace/JSON/源码；不把夹具误断言称生产缺陷。恢复夹具也改为仅一次元数据fulfill再使用真实服务，避免即时心跳循环干扰请求统计。',
      '其他SQLite连接修改、数据库读取错误恢复、心跳、并发容量、peer断开/关闭、版本乱序与metadata-only由后端定向测试验证，不能冒称浏览器覆盖所有连接来源。删除范围仍按来源关联，不声称独立重复seed内容的另一用户原文也被删除。', '',
      '## 系统回归与资源边界', '',
      '| 检查 | 当前实测 |', '| --- | --- |',
      '| Python全量 | 1028 passed / 1 skipped，42.29秒；随后仅增加3项容量测试，所属文件13通过4.22秒，生产代码未再改；不冒称1031全量重跑 |',
      '| 前端 | 76通过、26文件、6.36秒；含12项传输与4项真实watch Hook集成。四个旧快照/回合测试文件隔离watch传输，传输另测及Chromium验证 |',
      '| 质量检查 | lint修正未用Page导入后通过，类型-p项目通过；构建通过，Vite4.29秒 |',
      '| 默认浏览器 | 15通过/11显式可选跳过，35.3秒；可选外部/通知、历史、PCM另实跑，四项真实模型/ASR服务未在本轮重跑 |',
      f"| 恢复回归 | {restore['elapsedSeconds']:.3f}秒，54完成+1实际草稿取消，108稳定ID无重复、109条取消后快照，跨tab/迟到旧快照不复活，总提交55 |",
      '| 原PCM时钟 | 3通过，23.9秒；正常/双速/跳转/暂停/分段/预取取消原门槛未改 |',
      f"| 独立百轮v2 | {load['elapsedSeconds']:.3f}秒，100完成回合；1/25/100闭合诊断序列化/pre均0，原输入/媒体时钟门槛通过，导航翻页200条 |", '',
      '历史/百轮记录保留CDP、DOM及三次GC后堆观察。它们是不同消息/诊断状态，不能用来宣称消除所有堆增长或证明多日无泄漏。本轮没有训练/切换模型，没有占用GPU，也没有真人设备、真人音素或正式渲染验收。', '',
      '## 逐项审计结论与未解决项', '',
      '| 项目 | 结论 |', '| --- | --- |',
      f'| [G2C12-001]({issue1}) 通知中断刷新复活 | 已复现后修复，Hook与固定3轮浏览器通过 |',
      f'| [G2C12-002]({issue2}) 承接外部通知P1 | 原G2C11-003在当前固定协议内修复；前轮失败不改写 |',
      '| 记忆/隐私/动作 | 原版本/来源/事务及取消全量回归通过；不重放动作，未改变默认语义提示或权限 |',
      '| 长期稳定与接续 | 服务重启的短期/用户角色语境尚未实验验收；多日与其他堆归因继续开放 |',
      '| 思/听/演质量 | G2C2-009/016归属/身体边界、模板充分性，真人元音/ü/声调、物理设备和正式渲染仍开放 |', '',
      '本轮审计未在所列冻结门槛中发现遗留失败；这不等于无隐藏问题。下一轮优先测服务重启后的短期、角色语境和防重放，必须在独立临时库留存前后证据，再决定是否重建有来源上下文；不得直接把所有历史原文注入模型或执行旧命令。随后继续真实模型开放项与独立音素/设备证据。远期目标保持active，小步提交/指定密钥推送继续。', '',
      '## 过程与证据', '',
      f"源/服务包核对{snapshot['checked']}项通过，含开发工作区与固定提交分别绑定，见[核对记录](../实验/snapshot-check.json)。三轮服务包与CSS在frozen-source中明确归档，嵌套dist原被生成目录规则忽略，已专门force-add这些自有证据，不改变.gitignore或日常构建策略。归档SHA不把回忆或当前字节冒当旧观察。",
      '完整失败保留：API新增前404；后端测试误用MemoryStore上下文管理器；Hook中断刷新复活与鉴权提示错误；.test.ts首次未被既有.test.tsx配置选中，改名后才算12项传输；JSDOM首项既有1个启动timer，诊断3个watch自有timer均清理后按ID精确断言；新探针误期待cancelled；lint未用Page导入。没有提高12帧/媒体时钟阈值或选取最好轮次。',
      '[计划](../计划.md)、[进展](../进展.md)、[冻结协议](../../../../../evals/interaction/cycle-12/notification-protocol.json)、[前轮失败报告](../../cycle-11/审计/系统审计与推进报告.md)、[远期路线](../../远期目标与验收路线.md)。', '']
    # HERE is five path components below repository.
    for p in sorted(EV.rglob('*')):
        if p.is_file() and p.suffix in ('.json','.log') and 'source' not in p.parts and 'frozen-source' not in p.parts:
            lines.append(f'- [{p.relative_to(EV).as_posix()}](../实验/{p.relative_to(EV).as_posix()})')
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines)+'\n')
    def inline(s): return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(s))
    body, table = [], False
    for line in lines:
        if line.startswith('| ---'): continue
        if line.startswith('|'):
            if not table: body.append('<div class="table-wrap"><table>'); tag='th'; table=True
            else: tag='td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(c)+f'</{tag}>' for c in line.strip('| ').split(' | '))+'</tr>');continue
        if table: body.append('</table></div>');table=False
        if line.startswith('# '): body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '):body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line:body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    html='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十二轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border:1px solid #dee7ee;text-align:left;vertical-align:top}th{background:#e4edf7}.table-wrap{overflow:auto}a{color:#155aa7}@media(max-width:600px){main{padding:16px}h1{font-size:25px}table{font-size:14px}}</style><main>'+'\n'.join(body)+'</main></html>'
    for href in re.findall(r'href="([^"]+)"',html):
        if not href.startswith('https://'):assert (HERE/href).exists(),href
    (HERE/'系统审计与推进报告.html').write_text(html)
    inputs=list(EV.rglob('*'))+list((HERE/'issues').glob('*.md'))+[CYCLE/'计划.md',CYCLE/'进展.md',HERE/'build_report.py',HERE/'check_snapshots.py',HERE/'系统审计与推进报告.md',HERE/'系统审计与推进报告.html']
    manifest={p.relative_to(CYCLE).as_posix():sha256(p.read_bytes()).hexdigest() for p in sorted(inputs) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(len(manifest),'evidence hashes; fixed gates and links verified')

if __name__ == '__main__': build()

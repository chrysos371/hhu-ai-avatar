"""Build cycle 11 reports without turning a failed audit probe into approval."""
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
    before, after = read('cache-before.json'), read('cache-final.json')
    runs = [read(f'repeat-{n}-restore.json') for n in [1, 2, 3]]
    external, load = read('external-external-erase.json'), read('load-final-history.json')
    assert before['turns'] == after['turns'] == 40
    assert before['afterUnmountMutations'] == before['retainedSensitiveReplies'] == 40
    assert after['afterUnmountMutations'] == after['retainedSensitiveReplies'] == 0
    for r in runs:
        assert r['completed'] and len(r['turns']) == 54 and not r['errors']
        assert len(r['steps'][2]['ids']) == len(set(r['steps'][2]['ids'])) == 108
        assert r['steps'][3]['draft'] and len(r['steps'][3]['snapshot']['items']) == 109
        assert r['steps'][-1]['submitted'] == 55
        assert r['steps'][-1]['current']['revision'] > r['steps'][2]['snapshot']['revision']
        assert all(not row.get('result') for row in r['steps'][-1]['current']['items'])
        assert len(r['resources']) == 3
    assert not external['completed'] and len(external['rows']) == 12
    assert all(row['oldTraceVisible'] for row in external['rows'])
    assert external['refreshControl']['oldTraceRemoved']
    assert load['completed'] and len(load['turns']) == 100 and load['afterNavigation']['dom']['messages'] == 200
    assert all(e['input']['decisions'] == e['closed']['dom']['closedPre'] == 0 for e in load['checkpoints'])
    assert all(read('playback-final-'+name+'.json')['completed'] for name in ['clock', 'segments', 'prefetch-stop'])
    lines = ['# 第十一轮系统审计与推进报告', '',
             '日期：2026-11-11（上海时间）。作者：spinner-bot。起点5dd6d65，远期Goal继续active。', '',
             '## 结论与仍未通过的P1', '',
             '本轮实现数据库当前有效历史的鉴权恢复、翻页和原始新回合trace持久化，并将聊天mutation卸载后多余留存从40条降为0。导航/刷新、真实部分草稿取消、迟到快照/最终结果及界面跨tab删除，在所列有限协议中通过。',
             '追加系统审计发现[G2C11-003](issues/G2C11-003.md)仍开放：直接通过API确认删除、没有前端通知时，后端已清除旧trace，活动页却在12/12个RAF仍显示旧trace；手动刷新才清除。原三轮成功不覆盖这条路径。不能据默认测试绿色宣布全路径隐私同步、整体稳定陪伴或远期目标完成。下一循环首先补服务端版本通知。', '',
             '## 从基线到实现', '',
             '| 项目 | 改动前证据 | 当前结果 |',
             '| --- | --- | --- |',
             '| 聊天mutation缓存 | 真实ChatPage/QueryClient固定40回合，卸载下一任务仍40个mutation/40条标记回复，gcTime=300000ms | 同40回合挂载时仅当前1个，卸载后0个/0条 |',
             '| 历史入口 | GET /conversation为404；两个完成回合导航后展示4→0，数据库仍在 | 鉴权分页、稳定消息ID、原文与当前版本；导航和刷新恢复 |',
             '| 旧诊断来源 | 旧记录未存原trace，不能伪造 | 旧文字可读/朗读，明确无可用决策记录；新完成回合保存原始trace |',
             '| 删除同步 | 原来无恢复版本路径 | 界面/跨tab路径通过；直接API路径追加失败，保持P1 |', '',
             '缓存实验使用真实组件与QueryClient、控制fetch/SSE，计数只证明该缓存的对象留存，不解释全部JS堆增量。聊天mutation使用gcTime=0，当前可见结果仍由界面/数据库承担，未清其他管理缓存。参考[官方useMutation文档](https://tanstack.com/query/v5/docs/framework/react/reference/useMutation)的gcTime选项；实际300000ms由已安装源码和本地计数核实，未升级依赖。', '',
             '## 历史与隐私实现', '',
             '只读GET /api/v1/conversation返回instance_id、revision、按稳定ID排序的消息、has_more和游标；默认100条，显式加载更早，limit允许1..200。当前加载范围不会因同版本新快照而悄然截断；隐私版本变化清除旧快照，再按当前记录重建。读取不重放模型、工具或提醒。',
             'MemoryStore新增memory_chat_results，只保存绑定assistant消息ID与context_revision的原始结果。主流程返回用户/助手来源ID；记录前在事务内重验版本、角色、session与当前正文。历史从当前memory_messages读文字，旧数据没有原trace时不补造；任何隐私失效事务同时清除旧结果JSON，递归受影响正文仍走既有删除链。',
             '客户端不将转录/trace写localStorage。请求世代和提交epoch拒绝迟到响应，流式期间相同版本读取不会重复已落库用户消息或替换本地草稿；隐私变化停止播放、取消旧回合并重置已完成mutation。界面管理确认通过本地事件与BroadcastChannel通知其他tab，焦点/可见性恢复会重读。播放关联稳定消息ID，翻页不会把正在说话的角色状态指向另一行。',
             '这些客户端通知尚未覆盖所有外部写入，见003。历史显示恢复也不代表跨服务重启后自动重建模型短期窗口/角色扮演状态；本轮没有把旧原文重新注入生成或重放动作，跨进程语义接续需另测。', '',
             '## 冻结要求逐项检查', '',
             '| 原协议项 | 证据与结果 |',
             '| --- | --- |',
             '| 1 鉴权/游标 | API测试：拒绝无token、非法/重复参数；正常空快照与实例版本 |',
             '| 2 旧记录不伪造trace | 存储分页测试及完整ChatPage旧回复朗读/语音失败保留原文测试 |',
             '| 3 新完成回合原始来源 | API/浏览器逐行文字与ID、重读原decision JSON吻合 |',
             '| 4 SPA/更早分页 | 每轮54完成回合，当前100→显式108，108个ID无重复 |',
             '| 5 刷新 | 两回合刷新恢复4条，原新回合五组trace可查 |',
             '| 6 读取不执行 | 浏览器总提交55=54完成+1取消，读取/翻页不增提交；API短期状态不变 |',
             '| 7 部分草稿取消 | 实际收到云并不是开头的SSE后取消；重读109条=54助手+55用户，无助手草稿 |',
             '| 8 忙碌读取去重 | Hook控制读取与pending用户落库交错，不重复用户或覆盖草稿 |',
             '| 9 原话/依赖删除 | 后端递归正文清理、同事务清trace、外部连接阻断旧写入；浏览器原话删除 |',
             '| 10 迟到历史快照 | 忽略abort的控制fetch与实际持有旧HTTP快照，通知后释放仍不复活 |',
             '| 11 迟到最终结果 | 完整ChatPage受控流在隐私清理后释放，界面与mutation均不再填回 |',
             '| 12 跨tab/焦点 | Chromium两tab通过真实确认界面删除；Hook焦点/新实例重读通过；外部API另有失败 |',
             '| 13 原播放/取消 | 默认15项、原实际PCM三项保持；时钟阈值未改 |',
             '| 14 有限负载/资源 | 固定三轮54+1及独立百轮v2；GC/DOM/实际时长保留，非多日证据 |', '',
             '后端专题18项通过，包括并发删除时读取快照内部一致性、连接重开、损坏trace JSON不回放、角色/session/正文不匹配拒绝写入。快照可线性化于删除前的读取点，客户端仍需通知/世代屏障；这不意味着网络中旧包自动消失。', '',
             '## 实际浏览器重复与资源', '',
             '开发浏览器先完整通过一轮（57.744秒），随后冻结相同生产实现，另跑预设三轮，不选最好一轮。每轮54个完成回合、1个实际部分草稿取消；独立临时数据库、同一宿主机与受控HTTP提供方。真实浏览器/HTTP/SSE执行，不是实际LLM质量或真实用户试验。', '',
             '| 固定轮次 | 观察秒数 | 全部加载消息 | 删除后当前页 | 初始堆MiB | 108消息堆MiB | 删除后堆MiB |',
             '| --- | --- | --- | --- | --- | --- | --- |']
    for n, r in enumerate(runs, 1):
        a, b, c = r['resources']
        lines.append(f"| {n} | {r['elapsedSeconds']:.3f} | {b['dom']['messages']} | {c['dom']['messages']} | "+
                     ' | '.join(f"{entry['metrics']['JSHeapUsedSize']/1048576:.3f}" for entry in [a, b, c])+' |')
    lines += ['',
              '资源观察前各三次强制GC，实际Chromium版本随每轮记录。空页、108消息与删除后100消息是不同状态，trace是否保留也不同；不能与第十轮返回空页面的堆直接作等条件“加速/无泄漏”对照。缓存对象清理已证明，其他堆来源、长期资源与跨设备仍未充分归因。',
              f"独立百轮v2用{load['elapsedSeconds']:.3f}秒通过：1/25/100回复下闭合诊断决策序列化/pre仍均0，输入与正常/双速媒体时钟原门槛保持，导航后100条再加载至200条，没有重放提交。旧v1空视图结果仍绑定第十轮原代码。", '',
              '## 追加外部删除探针：明确未通过', '',
              '先另提交external-erase-probe.json，再在隔离seed事实上执行一次探针。确认旧trace确实包含该事实；通过APIRequestContext完成forget和确认，模拟不发布前端事件的写入方。后端revision增加且旧assistant result已移除，但活动页连续12个RAF仍见旧trace；手动刷新后trace消失。原始行、前后后端快照、失败日志和Playwright trace全部保留。',
              '这证明本机所测外部API路径缺少活动页通知，不是后端删除失败。未测自然发生频率或更长持续时间；不宣称重复用户原文也被删除——它与该seed事实没有那种来源关联。003保持开放，下一轮先做服务端版本通知/断开/重连，再跑原探针及全部既有隐私回归。', '',
              '## 系统审计与单项结论', '',
              '| 单项/方面 | 当前结论 |',
              '| --- | --- |',
              '| [G2C11-001](issues/G2C11-001.md) 缓存留存 | 已修，40→0；仅聊天mutation，非全部内存归因 |',
              '| [G2C11-002](issues/G2C11-002.md) 历史恢复 | 当前数据库展示/翻页/原trace及所测通知路径已实现；全路径同步仍由003限制 |',
              '| [G2C11-003](issues/G2C11-003.md) 外部写入 | P1开放，12/12旧trace仍见，手动刷新对照清除 |',
              '| 记忆与实际操作 | 来源/版本/事务回归通过；未改变生成提示、默认模型或真实操作权限 |',
              '| 听/演 | 真实PCM/SVG工程回归保持，未验收真人音素/ü/声调、物理设备与正式渲染 |',
              '| 思/长期使用 | 一般生成归属/身体边界、模板充分性、跨进程上下文接续与多日稳定仍开放 |', '',
              '第十轮G2C10-002中展示历史重置和聊天缓存留存已得到具体修复/归因证据，不能因此把长期稳定、外部同步及所有旧质量开放项一起关闭。', '',
              '## 完整回归、失败与版本', '',
              'Python全量1017通过/1跳过（39.82秒）；前端60通过（24文件、6.42秒），构建3.97秒，最后类型/lint通过。默认最终15通过/10显式可选跳过（35.0秒），其中PCM/百轮/恢复另实跑，外部probe另实跑失败；四项真实模型/ASR可选服务本轮未重跑。没有使用GPU。',
              '保留的开发错误：RTL误用exact类型参数、Vitest默认5秒误截40回合（改timeout=0，轮数不变）、Node BroadcastChannel与JSDOM事件realm不兼容（仅unit隔离，真实跨tab由Chromium测）、测试Harness局部key告警、旧端点测试误认为总消息必须0。默认初跑14过/1败，迁移为历史不变且POST /turns=0后15过。npm exec tsc只打印帮助的一次未计类型通过，随后明确-p项目核查。',
              '109项源绑定和36项服务包记录已核对；历史bundle不在当前dist时与第十轮归档同哈希观察对比，不冒称当前字节。正式结果绑定已提交HEAD；初始缓存开发后测属于未提交工作区，5份源码仅在与原捕获SHA精确相符后重建归档，方法见development-source-check.json，不混作正式门槛。补充依赖提交树核对与原始独立捕获区分，见snapshot-check.json。', '',
              '## 下一循环', '',
              'P1首先修003服务端版本通知，验证直接API/其他连接、后台与重连、旧流与播放取消、长连接资源回收，保留当前失败作为修前对照。随后用真实模型验证历史/删除后的原生生成与角色归属、身体边界和交付；服务重启下的短期/角色上下文接续另设协议。P2继续独立真人音素和正式形象、真实设备与长期观测。',
              '目标不缩为局部测试通过，保持active；本轮未宣称整体代际跃迁或全部隐私同步完成。[远期路线](../../远期目标与验收路线.md)。', '',
              '## 资料入口', '',
              '[计划](../计划.md)、[全过程](../进展.md)、[原协议](../实验/history-contract.json)、[百轮v2](../实验/history-load-protocol.json)、[追加探针](../实验/external-erase-probe.json)、[版本核对](../实验/snapshot-check.json)。']
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
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十一轮系统审计与推进报告</title><style>body{margin:0;background:#f2f5fa;color:#192b40;font:16px/1.8 system-ui,sans-serif}main{max-width:1080px;margin:auto;padding:32px}h1{font-size:30px}h2{border-bottom:2px solid #c7d6e8;padding-top:24px}p{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;background:white}td,th{padding:10px;border:1px solid #dee7ee;text-align:left;vertical-align:top}th{background:#e4edf7}.table-wrap{overflow:auto}a{color:#155aa7}@media(max-width:600px){main{padding:16px}h1{font-size:25px}table{font-size:14px}}</style><main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    for href in re.findall(r'href="([^"]+)"', html):
        if not href.startswith('https://'): assert (HERE/href).exists(), href
    inputs = list(EV.rglob('*'))+list((HERE/'issues').glob('*.md'))+[CYCLE/'计划.md', CYCLE/'进展.md']
    manifest = {p.relative_to(CYCLE).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(inputs) if p.is_file()}
    (HERE/'证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'{len(manifest)} evidence hashes; links valid; external-writer failure retained')


if __name__ == '__main__':
    build()

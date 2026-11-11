"""Build a bounded evidence report; fail rather than invent missing results."""
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
CYCLE = HERE.parent
EV = CYCLE/'实验'


def read(name): return json.loads((EV/name).read_text())


def build():
    before = read('browser-before.json'); browser = read('browser-context-controls.json')
    legacy = read('context-admission-legacy.json'); bound = read('context-admission-bound.json')
    notification = read('notification-final/notification.json'); restore = read('restore/restore.json')
    history = read('history-100/history.json'); checked = read('snapshot-check.json')
    assert before['completed'] and before['steps'][0]['status'] == 404
    assert browser['completed'] and browser['fixtureExit'] == 0 and not browser['errors'] and len(browser['steps']) == 12
    assert len(legacy['cases']) == len(bound['cases']) == 2 and all(c['candidate_pass'] for c in bound['cases'])
    assert legacy['cases'][0]['db']['profile']['名字'] == '许照'
    assert len(legacy['cases'][1]['db']['reminders']) == 1
    assert notification['completed'] and len(notification['steps']) == 9
    assert restore['completed'] and len(restore['turns']) == 54 and len(restore['steps']) == 5
    assert history['completed'] and len(history['turns']) == 100 and history['allCheckpointsObserved']
    assert not history['violations'] and not history['errors']
    playback = [read('playback/'+name) for name in ['clock.json', 'segments.json', 'prefetch-stop.json']]
    assert all(item['completed'] and item['failure'] is None for item in playback)
    assert checked['allPassed']
    assert '1228 passed, 1 skipped in 84.31s' in (EV/'python-full.log').read_text()
    assert 'Tests  122 passed' in (EV/'frontend-full.log').read_text()
    assert '15 passed (35.9s)' in (EV/'browser-default.log').read_text()
    assert '18 passed in 4.54s' in (EV/'context-admission-durability.log').read_text()
    assert '3 passed' in (EV/'browser-playback.log').read_text()
    lines = ['# 第十八轮系统审计与推进报告', '',
        '日期：2026-11-11—12（上海时间）。作者：spinner-bot。远期Goal继续active。基线fe0eda3；来源快照d860cf1，共享通知60669b4，UI初接8ba5076，原子入场823908a，最终产品接线76a759f。', '',
        '## 当前结论', '',
        '网页现能明确选择本人/角色，并从当前数据库来源核验有效状态；切换保留草稿，以独立规范控制提交。新增普通消息的语境绑定，阻断“角色模式下排队、另一客户端退现实、旧角色文本被当本人执行”的受控交错。此前实际写入的角色姓名和1条提醒原证据保留；绑定后原两例均不写来源、短期、资料或提醒，实际Chromium另验证过期提交拒绝及真人正控。',
        '本轮新增3个单项审计记录并在各自冻结范围修复：监测故障世代、客户端排队归属、普通消息原子语境入场。完整1228 Python通过/1跳过、前端122单元与构建检查通过，默认与独立浏览器、恢复、百轮、PCM均另有本轮数据。结论是交互与并发边界改进，不批准通用语义、物理设备或多日质量，不宣布整体代际跃迁。', '',
        '## 三项问题、原始失败与处理', '',
        '| 问题 | 修前实际证据 | 修复与有限结论 |', '| --- | --- | --- |',
        '| [001 迟到旧成功清新故障](issues/G2C18-001-迟到成功检查清除较新故障标记.md) / P2 | 受控线程读取顺序1失败/1通过 | 故障世代阻止旧在途成功清故障；故障后新成功才恢复，26关联通过，扩展通知42通过 |',
        '| [002 排队隐私与旧结束归属](issues/G2C18-002-失效排队发送及旧结束回调影响新回合.md) / P2 | ChatPage/TanStack异步onMutate两项失败 | 发送前epoch核验、同步提交归属、取消标记、仅自身结束释放；所属4项及控件旧关联12通过 |',
        '| [003 旧普通消息未绑定语境](issues/G2C18-003-排队普通消息未绑定发送时语境.md) / P1 | 双实际HTTP共库：姓名污染及1提醒；两任务completed | expected_context同源写事务核验，原双HTTP2/2拒绝、46关联通过；React冲突5+旧关联25及实际双页另通过 |', '',
        '001只证明受控SQL读取错误状态，不推测自然泄露率；002只有受控异步MutationCache配置，不冒称默认生产自然发生率。003旧无字段接口仍按实际处理时全局语境解释；新UI普通回合才绑定所见快照。修前临时DB污染不自动扫描或修改用户真实库。', '',
        '## 实现与约束', '',
        'GET /conversation/speaker鉴权且无参数，精确8元数据字段；同一SQLite只读快照核验revision、最新user来源游标及最多4条控制依据，不从旧trace猜当前权限、不复制原文或重放模型/动作。无来源、旧库缺跟踪或隐私失效可返回unverified；general_coreference_verified始终false。本人权限描述后续独立回合，切现实本身不执行旧提醒。',
        '共享changes原两字段客户端保持兼容；新页面仅在同一个等待上opt-in context_cursor，继续一共享监测/服务最多4等待/保留普通连接名额。普通源更新只刷新小语境元数据，不清本页历史或取消已提交回合；隐私、命名空间改变、失联和鉴权失败仍清旧状态。故障世代是保守恢复条件，迟到故障也不能忽略。',
        '“以本人说话”“进入角色”分别独立发送“回到现实。”“我来扮演一个虚构角色。”，不发送草稿、固定use_web=false且不自动朗读。按来源快照确认，不按按钮点击乐观赋权。普通输入携带instance_id/revision/context_cursor，在BEGIN IMMEDIATE事务中核验后才写短期与用户源；失配typed SSE speaker_context_changed，客户端先重新核验，仅同隐私/命名空间才恢复待重发草稿，任何情况不自动重放。',
        '约束字段参与新请求幂等指纹，字段顺序稳定、复制调用方字典，旧三字段指纹字节保持；同请求已完成不重验自身推进的游标，重启/过期仍410且不重跑。新字段不是普遍SDK/CLI语境恢复机制，旧无字段调用也不自动获得新约束。', '',
        '## 实验与系统回归', '',
        '| 阶段 | 本轮实测 | 范围与证据 |', '| --- | --- | --- |',
        '| 初始实际HTTP/浏览器 | speaker404；1440/390按钮各0、面板0 | browser-before.json；不是旧功能截图充当修后 |',
        f'| 双服务入场交错 | 旧2例副作用；绑定2/2无来源/副作用，{bound["duration_seconds"]:.6f}s | 两个真实鉴权HTTP服务共库、LLM关闭；HTTP/SSE/DB/短期全留存 |',
        '| 后端关联/去重 | 46关联通过；后增2项持久边界后所属18通过/4.54s | 18与46重叠，不能相加作独立样本 |',
        '| 完整Python | 1228通过/1跳过，84.31s | 76a759f产品源码；随后只增2测试，不称1230完整重跑 |',
        '| 前端单元/静态/构建 | 122通过/31文件，7.15s；lint/tsc/build通过 | 正式dist index-D8T5Fo8G.js；后仅e2e采证器调整，生产构建未改变 |',
        '| 默认浏览器 | 15通过/11显式可选跳过，35.9s | 受控本地提供方；真实模型/ASR可选分支本轮未批准 |',
        '| 独立控件Chromium | 12记录全部通过；两视口无溢出/脚本错误 | 5主页面POST含1拒绝+另页2控制+API1控制；实际DB正反控，fixture2807766退出0 |',
        '| 外部删除/通知 | 最终2通过/11.8s，9步 | 合法三字段人工重连、同版本无重放、实际PCM/部分生成外部删除；首轮旧人工2字段另保留 |',
        f'| 来源历史恢复 | 54完成+1实际部分生成取消，108消息分页；{restore["elapsedSeconds"]:.3f}s | 5步导航/刷新/原trace/跨tab删除，原固定门槛 |',
        f'| 完整百轮 | 100回合、1/25/100检查点通过，{history["elapsedSeconds"]:.3f}s | 实际UI/HTTP/SSE/PCM/资源观测，violations/errors为空；同机受控，不称自然多日 |',
        '| 独立PCM | 原三项通过 | 变速/双向seek/暂停/结束/停止、三段顺序、预取停止及迟到事件；见playback原JSON |',
        f'| 源/服务包核验 | {checked["checked"]}个唯一(path,SHA)全部绑定 | 当前字节与历史Git blob分开，保留失败实现；ignored dist以当前实际服务字节核验 |', '',
        '重复有限实验与单元检查不叠加为语义准确率，时长仅观察，不作吞吐或因果加速结论。本轮没有使用GPU或新跑真实模型；C15/16真实4B/14B的失败与拒绝启用结论仍是历史证据，未被本轮工程绿色改写。', '',
        '## 失败留痕与证据归属', '',
        '快照测试首2失败来自不存在Turn.done和读事务中才初始化并发写入连接；前端首次.test.ts不在现有发现范围、初始busy夹具不符合真实ready→busy流程，原日志均留存，不计产品失败或通过。独立浏览器采证器先发生临时目录定位错误，再发生route释放竞态未捕获退出1，两次保留原JSON/log；后者退出码未观察，不补称0。唯一来源session_id确认自建残留DB后先保存行与归属证据再清理该目录，未触碰其他历史目录。',
        '最终控件JSON完成12条记录且fixture退出0，与上述未完成尝试严格分开。通知首轮人工2字段回复被opt-in解析拒绝后真实服务器恢复，首轮2通过不能证明该人工回复被接纳；最终采证器显式合法3字段、记录该重连步骤再通过。没有放宽产品解析、旧测试断言或原百轮/PCM判据。', '',
        '## 尚未批准与下一循环', '',
        '| 范围 | 当前结论 | 后续要求 |', '| --- | --- | --- |',
        '| 本轮三项 | 冻结受控边界修复并回归 | 不外推所有并发顺序、断网日程或自然发生频率 |',
        '| 角色自由语法/一般指代 | 明确按钮减少猜测；general_coreference_verified=false | 自由文本与省主体/引用/创作归属继续独立验证 |',
        '| C15/16 lab与原生语义 | 候选继续关闭；未知写作deferred、一般润色误改、身体/偏好与短信提议开放 | 完整原生/可见/最终/来源/真实副作用，不能用模型自评批准 |',
        '| CLI与长期 | Web来源恢复和新UI入场有限可用 | CLI一般短期/PAD/任务、跨写入方其它组合、长期稳定继续测 |',
        '| 听/演设备质量 | 软件PCM/时钟/合成与既有真实ASR证据分列 | 真人音素/ü/声调、物理麦克风及音画/正式渲染未批准 |', '',
        '| 优先级 | 推进方向 | 先验收什么 |', '| --- | --- | --- |',
        '| P1/P2 | 工具能力与原生回复诚实性 | 明确工具清单/实际调用回执，区分代拟、提议与宣称执行；保留C15短信原失败，先冻结真实模型逐轮探针 |',
        '| P2 | 语境未知时交付与一般写作来源 | 旧失败仅作回归，另冻独立输入；避免把草稿误改为AI无身体声明 |',
        '| P2 | 新语境控制更多跨进程/多写入组合 | 有来源/隐私/幂等和原子入场的实际反控，不重放被阻断旧动作 |',
        '| P3 | 真实听→思→演→记与长期 | 按实际GPU余量选择同组最多4卡；无墙钟实验截止，保留算法轮数与早停；真实设备/真人证据分开 |', '',
        '远期Goal保持active。小步spinner-bot提交与授权SSH推送贯穿本轮；报告封存后进入下一循环，不以本轮有限工程门槛宣布远期目标完成。', '',
        '## 过程与证据', '',
        '[计划](../计划.md)、[进展](../进展.md)、[主协议](../../../../../evals/interaction/cycle-18/explicit-context-protocol.json)、[补充原子入场协议](../../../../../evals/interaction/cycle-18/context-admission-protocol.json)、[源绑定](../实验/snapshot-check.json)、[证据清单](证据清单.json)。']
    for path in sorted(EV.rglob('*')):
        if path.is_file() and path.suffix in ('.json', '.log'):
            name = path.relative_to(EV).as_posix(); lines.append(f'- [{name}](../实验/{name})')
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines)+'\n')
    def inline(value): return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(value))
    body = []; table = False
    for line in lines:
        if line.startswith('| ---'): continue
        if line.startswith('|'):
            if not table: body.append('<div class="table-wrap"><table>'); tag = 'th'; table = True
            else: tag = 'td'
            body.append('<tr>'+''.join(f'<{tag}>'+inline(cell)+f'</{tag}>' for cell in line.strip('| ').split(' | '))+'</tr>'); continue
        if table: body.append('</table></div>'); table = False
        if line.startswith('# '): body.append('<h1>'+inline(line[2:])+'</h1>')
        elif line.startswith('## '): body.append('<h2>'+inline(line[3:])+'</h2>')
        elif line: body.append('<p>'+inline(line.removeprefix('- '))+'</p>')
    style = re.search(r'<style>.*?</style>', (CYCLE.parent/'cycle-17/审计/系统审计与推进报告.html').read_text()).group()
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十八轮系统审计与推进报告</title>'+style+'<main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    inputs = [*EV.rglob('*'), *(HERE/'issues').glob('*.md'), *HERE.glob('*.py'), *HERE.glob('*.mjs'), *HERE.glob('*.png'),
              CYCLE/'计划.md', CYCLE/'进展.md', HERE/'系统审计与推进报告.md', HERE/'系统审计与推进报告.html']
    manifest = {path.relative_to(CYCLE).as_posix(): sha256(path.read_bytes()).hexdigest() for path in sorted(set(inputs))
                if path.is_file() and '__pycache__' not in path.parts}
    (HERE/'证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for href in re.findall(r'href="([^"]+)"', html): assert (HERE/href).exists(), href
    print(len(manifest), 'evidence hashes;', checked['checked'], 'source/bundle bindings; fixed gates/links valid')


if __name__ == '__main__': build()

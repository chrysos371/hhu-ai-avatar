"""Build the bounded default-control fix report from actual retained evidence."""
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
    http = read('http-count/canonical-http.json'); browser = read('browser-context-controls.json')
    restart = read('os-restart/role-restart.json'); checked = read('snapshot-check.json')
    turns = [row for row in http['steps'] if 'result' in row]
    controls = [row for row in turns if row['result']['generation_mode'] == 'rules_speaker_control']
    assert http['completed'] and http['cleanup'] and len(http['steps']) == 14 and len(turns) == 11
    assert len(controls) == 7 and all(row['provider_requests'] == 0 for row in controls)
    assert len(http['model_requests']) == 6
    assert browser['completed'] and browser['fixtureExit'] == 0 and len(browser['steps']) == 16 and len(browser['controlResults']) == 3
    assert not browser['errors'] and all(row['result']['generation_mode'] == 'rules_speaker_control' for row in browser['controlResults'])
    assert restart['allPassed'] and len(restart['cases']) == 10 and sum(len(case['turns']) for case in restart['cases']) == 56
    assert all(service['exit'] == 0 for case in restart['cases'] for service in case['services'])
    assert checked['allPassed'] and len(checked['test_log_bindings']) == 4
    for name, expected in [('canonical-control-before.log', '7 failed, 9 passed'),
        ('canonical-control-first.log', '2 failed, 56 passed'), ('canonical-control-related.log', '61 passed in 8.53s'),
        ('python-full.log', '1272 passed, 1 skipped in 85.72s'), ('browser-default.log', '15 passed (36.3s)')]:
        assert expected in (EV/name).read_text(), name
    lines = ['# 第二十轮系统审计与推进报告', '',
        '日期：2026-11-12（上海时间）。作者：spinner-bot。远期Goal继续active。基线a5994ae，红测d0be632/1611f62，默认修复19824cd，实际HTTP采证4310945，浏览器采证e7807dd。', '',
        '## 当前结论', '',
        '默认两个纯规范模式控制现以已提交来源返回固定确认，不再请分析/回复模型补写动作状态，避免C19-002已知“回到现实后承诺旧提醒/称已记录”的规范控件问题。7个规范控制实际HTTP回合均0次物理模型请求，普通与提醒正控有6次请求，证明提供方确实可用；角色旧提醒0、后续真人新提醒1。',
        '完整Python1272通过/1跳过、默认浏览器15通过/11可选跳过；独立Chromium16记录/三个来源确认、实际OS10项56回合20进程均通过。修复仅覆盖两个规范控制及允许的外空白/省末中文句号，不覆盖自由别名或一般生成能力诚实性。C19-001默认短信/电话虚假执行P1仍开放，C19提示v1仍拒绝启用，未借此批准通用语义或代际跃迁。', '',
        '## 根因与默认改动', '',
        'C19实际14B在角色提醒被阻断、真实DB0时，独立回到现实仍生成我来提醒或已记录的确认式话语。权限层没有重放，但通用模型对纯控制追加旧动作状态。新路径先沿用用户源与SpeakerContextStore同事务提交，再核验revision、当前正整数user来源ID、来源basis、目标scope及本轮无真实动作权限，并复核实际原文。只处理我来扮演一个虚构角色和回到现实两种完整规范文本。',
        '固定文字描述“本轮”已确认的语境，明确切换不执行旧请求、真实新提醒需另发请求；不宣称之后全局模式永远不变，活跃模式仍以当前只读快照为准。返回rules_speaker_control及speaker_control(version/command/scope/revision/source_message_id/real_actions_executed=false)，不从旧trace猜当前权限。',
        '已有boundary.reply优先，不由快捷确认覆盖；该优先级用受控边界测试验证，不是临床或全部安全语义批准。纯控制跳过分析/回复模型、无关召回/知识/摘要刷新和写作交付重写，仍保留取消、隐私版本、原子expected_context入场、最终消息及来源依赖。use_web=true也不执行联网；真实新提醒继续旧明确规则路径。', '',
        '## 修前与实现验证', '',
        '| 阶段 | 实际结果 | 解释与证据 |', '| --- | --- | --- |',
        '| 修前默认矩阵 | 7失败/9通过、0.82s | 规范控制/旧提醒退出无专用确认；引用/写作/问句/条件/复合/别名反控不被新路由吞掉 |',
        '| 首实现关联 | 56通过/2失败、10.45s | 旧测试假设分析必运行、控制后必有新模型请求失效；原日志保留，不称产品隐私/取消缺陷 |',
        '| 适配采证后关联 | 61通过、8.53s | 保留原取消/隐私断言，增边界优先、检索/摘要/交付零调用及源后隐私失效不提交确认 |',
        '| 完整Python | 1272通过/1跳过、85.72s | 19824cd已提交运行源/测试树；包含此前全部门槛与新19项 |',
        '| 默认浏览器 | 15通过/11可选跳过、36.3s | 新后端兼容现有前端，受控提供方，真实模型/设备可选分支未借此批准 |', '',
        '首次红测命令因实验目录尚未创建，shell重定向失败，0测试运行；command-first.log另留，建目录后才是实际7/9。原pytest日志尾空白不修剪，代码/文档与*.log分开做diff检查，保留原始字节。',
        '首实现的取消测试暂停在_analyze，但新路径刻意跳过它；改到同一真实源已提交/助手未提交的boundary.assess，取消后scope持久正确且无助手的断言不变。隐私测试原本检查控制后最新模型请求，零调用时读到的是历史请求；现在先断言控制无新调用，再发独立普通消息，继续严格检查新请求不含待删姓名，不声称能抹去已经发送给提供方的历史请求。', '',
        '## 独立HTTP、浏览器与实际重启', '',
        '| 协议 | 本轮实际结果 | 范围与区别 |', '| --- | --- | --- |',
        f'| 真实HTTP/SSE与计数提供方 | 14记录/11用户回合；7控制0模型请求，正常正控合计6请求；{http["elapsedSeconds"]:.6f}s | 默认Avatar、真实loopback socket、受控提供方；同一审计OS进程内两个服务实例，不冒称OS重启/真实GPU质量 |',
        '| 动作与隐私 | 旧角色提醒0、后续真人图书馆提醒1；外部遗忘后unverified再明确恢复 | 来源/版本/固定确认/最终存储一致；旧请求新实例后410不重放，临时库及服务清理通过 |',
        '| Chromium双页 | 16记录、3实际按钮结果来源/固定mode/历史DOM一致 | 保留草稿、跨页变化、过期普通提交拒绝、资料/提醒正反控；fixture2877345退出0，1440/390无错误/溢出 |',
        f'| 实际OS重启 | 10/10、56鉴权同步HTTP回合、20独立服务进程；{restart["elapsedSeconds"]:.6f}s | C17最终10项旧矩阵重放，PID/instance实际改变、空初始短期；LLM关闭，非新独立语义样本 |',
        '| OS清理/来源 | 20进程全部退出0，worker源前后一致 | 具体/未知/隐私/其他写入/引用退出/复合与组合声明恢复、真人姓名/提醒反控均通过，无旧码头提醒重放 |',
        f'| 源/测试/包核验 | {checked["checked"]}个唯一(path,SHA)全部绑定；4测试阶段 | 修前、首失败夹具、修正夹具和全量测试源按实际字节/历史Git分开；20 worker校验 |', '',
        '规范控制不依赖模型是受控配置下实际请求计数及默认分支验证，不是新4B/14B生成质量验收；本轮没有加载GPU模型。普通正控确有模型HTTP请求，不能用关闭模型来冒充0。实际OS重启与同进程内服务实例重建分别报告，不合并为同一种恢复证据。', '',
        '前端生产未改，仍服务C18的index-D8T5Fo8G.js并在本轮浏览器记录实际SHA；前端122单元/lint/类型/build、完整百轮及独立原PCM为C18数据，本轮没有冒称重跑。新增一次版本检查不构成吞吐或因果加速结论，所有时长只作观察。', '',
        '## 单项结论与尚未解决范围', '',
        '| 项目 | 当前结论 | 仍开放范围 |', '| --- | --- | --- |',
        '| [C20-001，承接C19-002](issues/G2C20-001-规范控制仍使用模型补写动作确认.md) | 两个纯规范UI控制的默认问题在冻结范围修复；不是另计一个新根因 | 其它自由别名/复合语境仍原模型路径，不宣称全部自然语言确认可靠 |',
        '| C19-001无能力发送 | 本轮未解决，默认P1继续开放 | 短信/电话已执行声称、代发承诺/提议与无必要联系人索取；无实际外部发送事实 |',
        '| C19提示v1 | 继续隔离拒绝，本轮未启用 | 旧已知失败仅回归，新能力/当前来源/真实回执约束须另冻实验 |',
        '| 写作/身体/归属 | 不借控制修复重标为通过 | C15/16候选未知/润色/连续原文、原生身体/偏好归属仍开放 |',
        '| 长期/真实设备 | 无本轮新增批准 | CLI一般上下文、多日、真人音素/ü/声调、物理麦克风/音画与正式渲染 |', '',
        'C19封存报告中的默认问题开放结论保持原样；本报告补充规范控制范围的后续修复，不回写旧失败或旧SHA清单。工具执行屏障与语言诚实性继续分别评估，不能因旧提醒没有真实执行就说所有回复已充分准确。', '',
        '## 下一循环优先级', '',
        '| 优先级 | 方向 | 数据要求 |', '| --- | --- | --- |',
        '| P1 | 默认一般能力与真实执行证据约束 | 当前工具注册、当前user来源/scope/本轮执行记录，保护代拟/小说/用户报告；开发失败仅已知回归，前瞻另冻 |',
        '| P2 | 非规范控制与任务来源 | 复用已有归属解析的可信事件，不以词面一概吞复合输入，保持事实/动作独立 |',
        '| P2 | 端到端生成交付 | 完整原生/可见/最终/存储与副作用，人工来源复核不冒充独立人评 |',
        '| P3 | 听→思→演→记与持续使用 | 按实际GPU余量选择同组最多4卡，自建进程清理、真实设备/多日证据分开 |', '',
        '远期Goal保持active。每个可审查阶段已spinner-bot及时小步提交并指定SSH推送；本轮封存后继续能力与执行回执研究，不宣告整体代际跃迁。', '',
        '## 过程与证据', '',
        '[计划](../计划.md)、[进展](../进展.md)、[规范协议](../../../../../evals/interaction/cycle-20/canonical-control-protocol.json)、[复用OS协议](../../../../../evals/interaction/cycle-17/role-final10-restart-protocol.json)、[测试版本绑定](../实验/test-source-bindings.json)、[源核验](../实验/snapshot-check.json)、[证据清单](证据清单.json)。']
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
    style = re.search(r'<style>.*?</style>', (CYCLE.parent/'cycle-19/审计/系统审计与推进报告.html').read_text()).group()
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第二十轮系统审计与推进报告</title>'+style+'<main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    inputs = [*EV.rglob('*'), *(HERE/'issues').glob('*.md'), *HERE.glob('*.py'), *HERE.glob('*.mjs'), *HERE.glob('*.png'),
              CYCLE/'计划.md', CYCLE/'进展.md', HERE/'系统审计与推进报告.md', HERE/'系统审计与推进报告.html']
    manifest = {path.relative_to(CYCLE).as_posix(): sha256(path.read_bytes()).hexdigest() for path in sorted(set(inputs))
                if path.is_file() and '__pycache__' not in path.parts}
    (HERE/'证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for href in re.findall(r'href="([^"]+)"', html): assert (HERE/href).exists(), href
    print(len(manifest), 'evidence hashes;', checked['checked'], 'source/test/bundle versions; fixed gates/links valid')


if __name__ == '__main__': build()

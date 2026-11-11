from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
CYCLE = HERE.parent
EV = CYCLE/'实验'


def read(path): return json.loads((EV/path).read_text())


def build():
    before = read('role-before/role-authority.json'); first = read('role-after/role-authority.json')
    compound = read('compound-before/role-authority.json'); final = read('final26/role-authority.json')
    old_os = read('role-restart-first/role-restart.json'); final_os = read('final10-os/role-restart.json')
    checked = read('snapshot-check.json')
    assert before['completed'] and sum(c['passed'] for c in before['cases']) == 14
    assert first['allPassed'] and len(first['cases']) == 20
    assert compound['completed'] and sum(c['passed'] for c in compound['cases']) == 3
    assert final['allPassed'] and len(final['cases']) == 26
    assert old_os['allPassed'] and len(old_os['cases']) == 7
    assert final_os['allPassed'] and len(final_os['cases']) == 10
    assert sum(len(c['turns']) for c in final_os['cases']) == 56
    assert all(s['exit'] == 0 for c in final_os['cases'] for s in c['services'])
    assert final['sourceSha256']['src/avatar/brain/speaker_scope.py'] == final_os['sourceSha256']['src/avatar/brain/speaker_scope.py']
    assert checked['allPassed'] and checked['checked'] == 85
    full = re.search(r'(\d+) passed, (\d+) skipped in ([\d.]+)s', (EV/'python-final.log').read_text())
    assert full and full[1] == '1184' and full[2] == '1'
    assert '15 passed (35.7s)' in (EV/'browser-final.log').read_text()
    lines = ['# 第十七轮系统审计与推进报告', '',
        '日期：2026-11-11（上海时间）。作者：spinner-bot。远期Goal继续active；基线56e9d63，首修b139269，最终角色实现7b9eb27、最终验证入口冻结f4ef925。', '',
        '## 当前结论', '',
        '修复默认角色权限P1：明确剧/故事等具体人物声明能保持角色来源，未支持但明确的扮演意图降为unverified，不再直接授予真人资料/提醒权限。原20矩阵14通过/6失败，首修20通过后追加组合助动词6项又3失败；补修后同一最终源码26项全部通过，实际OS重启10项、56回合、20次服务启动也通过。',
        '当前结论限于冻结的角色语法、来源及动作组合，不宣称通用角色/指代识别或全部多写入/多日可靠。C16 lab暂缓仍可见身体文字、一般润色误改，C15短信能力和原生偏好/身体语义继续开放，候选不启用。原失败、一般演员误拦及补充失败均保留。', '',
        '## 根因与修复', '',
        '旧_ENTRY要求句尾角色或人物，“接下来我扮演剧中的旅行者”未改变scope，后续角色姓名及提醒被当真人请求。现在明确当前剧/小说/故事等来源可fictional_character；直接但无法核验的其它扮演意图只能unverified，清空真人依据，不捏造角色姓名。unverified的持久控制不保存断言basis，重启或隐私来源失效不能恢复真人权限。',
        '既有引用、过去饰演、问句、假设、否定、普通职业仍保持原语境。首候选未知意图守卫误把“我扮演小说角色时会很紧张”这种一般经历当控制切换，旧测试1失败/89通过；保留完整候选源码/SHA及原日志后收窄讨论/提问，90相关通过。随后将会/想要/准备要组合仍漏，补充3失败原样保存，再只扩有限组合助动词，96相关通过。没有放宽旧断言。',
        '独立“回到现实”及后续新真人请求恢复写名/建提醒；同轮末尾退出不追认前面的提醒，历史被阻断动作不重放。未自动扫描或删除真实已有污染。此处的说话者unverified会阻断事实/动作，和lab写作语境deferred是两个不同控制，不能互换批准。', '',
        '## 冻结矩阵逐项对照', '',
        '下面初次20的修前为56e9d63行为，补充6的修前为首修b139269，两个来源不能相加作同一个修前准确率。最终26均为同一7b9eb27角色源码下已知回归重放，不冒充独立真人或未见语义样本。', '',
        '| 分组/项目 | 修前实际 | 最终同源结果 |', '| --- | --- | --- |']
    final_by_id = {c['id']: c for c in final['cases']}
    for label, dataset in [('初次20', before), ('补充6', compound)]:
        for case in dataset['cases']:
            assert final_by_id[case['id']]['passed']
            lines.append(f'| {label} / {case["id"]} | {"通过" if case["passed"] else "失败：真人权限/姓名/提醒"} | 通过，含真人正控或明确现实恢复 |')
    lines += ['',
        '矩阵使用默认Web run_chat、LLM禁用、真实隔离SQLite资料/提醒路径；所有预期真人正控实际写姓名并创建1提醒，不能把时间解析拒绝当权限拦截。受限组不写姓名/0提醒；现实确认后只创建新图书馆提醒，不出现此前码头提醒。未配置LLM的生成回退不计模型质量。', '',
        '## 结构化实验与系统回归', '',
        '| 阶段 | 实际结果 | 范围与来源 |', '| --- | --- | --- |',
        f'| 初次20原矩阵 | 修前14/20；首修20/20，观察{first["elapsedSeconds"]:.6f}s | 首修b139269，非最终组合版本 |',
        f'| 首修OS7 | 7/7、38回合/14启动，{old_os["elapsedSeconds"]:.6f}s | 历史开发快照，不混成最终同源 |',
        '| 组合助动词6 | 首修3/6，原姓名/提醒失败保留 | 后续已知回归，不重算独立分数 |',
        f'| 最终26 | 26/26，观察{final["elapsedSeconds"]:.6f}s | 原20+补充6，同最终角色源SHA |',
        f'| 最终OS10 | 10/10、56回合/20独立服务启动，{final_os["elapsedSeconds"]:.6f}s | 鉴权同步V1 HTTP；不是SSE或新模型质量 |',
        f'| 最终完整Python | {full[1]}通过/{full[2]}跳过，{full[3]}s | 最终源码，包含26矩阵及既有隐私/取消/模型分析门槛 |',
        '| 最终默认浏览器 | 15通过/11可选跳过，35.7s | 默认受控提供方；可选真实模型/ASR另列，未借此声称本轮GPU验证 |',
        '| 源/失败绑定 | 85个唯一核验 | 当前字节/历史Git blob及首失败候选归档源码+原日志SHA，后者不冒称Git版本 |', '',
        '最终OS覆盖具体角色、未知意图、来源被删除、其他写入方退出再遗忘、引号内退出不生效、同轮真实退出不授权前动作、过去演员真人正控，加3个组合声明来源恢复。每次实际PID/服务实例变更，初始生成短期窗口为空，两个进程源SHA与父进程冻结一致；所有自建进程退出0，没有终止他人进程。',
        '首修1178/1、73.23s及默认35.6s另留，最终补修后1184/1、73.15s和默认35.7s才是当前源码结果。实验/测试独立进程并行，时长是观察值，不作吞吐/因果速度或多日结论。首次命令误指不存在测试文件，0测试执行，日志保留但不计产品失败或通过。',
        '前端生产未改，前端76单元/lint/类型/build、百轮及原PCM仍为第十二轮历史，没有本轮冒称重跑。本轮没有加载GPU模型；第十六轮真实4B/14B数据是发现问题的历史来源，修复后本轮仅控制/权限/恢复验收，不把它重标为当前模型语义通过。', '',
        '## 单项结论与尚未批准范围', '',
        '| 项目 | 本轮处理 | 剩余范围 |', '| --- | --- | --- |']
    for issue in sorted((HERE/'issues').glob('*.md')):
        lines.append(f'| [{issue.stem}](issues/{issue.name}) | 当前26/OS10固定范围内修复 | 有限语法，不批准所有自然语言声明与通用指代 |')
    lines += [
        '| C16 lab002/003 | 保持隔离关闭，本轮没有调v2 | 语境未知的交付策略、一般润色来源仍开放 |',
        '| C2归属/身体与短信 | 原生模型未据本轮控制门槛获批准 | 偏好/受话者/省主体、能力诚实性需独立真实逐轮验证 |',
        '| 真实设备/长期 | 无本轮新验收 | 真人音素/ü/声调、物理麦克风/同步、正式渲染、CLI一般上下文及多日 |', '',
        '不把“未匹配角色表达”视为普遍可靠的真人判定；当前改进是已识别的明确意图保守降权。下一循环优先让用户明确选择本人/角色语境并看到有效状态，减少对自由文本猜测的依赖；先测现有界面/接口，再冻结控制、队列取消、重启和隐私协议，避免显示旧状态或把切换与真实动作合并。', '',
        '## 下一循环策略', '',
        '| 优先级 | 方向 | 证据要求 |', '| --- | --- | --- |',
        '| P1/P2 | 明确可审计的本人/角色控制与可见状态 | 来源/权限/版本/独立动作分开，真实浏览器切换、取消与隐私/重启；不凭旧trace乐观显示当前权限 |',
        '| P2 | lab未知写作澄清与一般改写覆盖 | 失败仅回归，另冻独立输入；不无限复制历史、不把草稿统一改成AI声明 |',
        '| P2 | 原生归属/身体/工具能力诚实性 | 完整原生/审核/可见/最终/入库与副作用，模型自评不能批准 |',
        '| P3 | 听→思→演→记与实际设备/多日 | 按实际GPU余量和真实设备证据推进，软件/合成与真人分开 |', '',
        'Goal继续active，未宣布整体代际跃迁。每个可审查阶段已即时spinner-bot小步提交并授权SSH推送，原失败和不同实现快照分开；当前轮报告封存后继续下一循环。', '',
        '## 过程与证据', '',
        '[计划](../计划.md)、[进展](../进展.md)、[原20协议](../../../../../evals/interaction/cycle-17/role-authority-protocol.json)、[最终26协议](../../../../../evals/interaction/cycle-17/role-final26-protocol.json)、[源核验](../实验/snapshot-check.json)、[证据清单](证据清单.json)。']
    for p in sorted(EV.iterdir()):
        if p.is_file() and p.suffix in ('.json', '.log'): lines.append(f'- [{p.name}](../实验/{p.name})')
        elif p.is_dir():
            for filename in ['role-authority.json', 'role-restart.json', 'binding.json']:
                if (p/filename).exists(): lines.append(f'- [{p.name}/{filename}](../实验/{p.name}/{filename})')
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(lines)+'\n')
    def inline(value): return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(value))
    body = []; table = False
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
    style = re.search(r'<style>.*?</style>', (HERE.parent.parent/'cycle-16/审计/系统审计与推进报告.html').read_text()).group()
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十七轮系统审计与推进报告</title>'+style+'<main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    inputs = [*EV.rglob('*'), *(HERE/'issues').glob('*.md'), *HERE.glob('*.py'), *HERE.glob('*.mjs'),
        *HERE.glob('*.png'), CYCLE/'计划.md', CYCLE/'进展.md', HERE/'系统审计与推进报告.md', HERE/'系统审计与推进报告.html']
    manifest = {p.relative_to(CYCLE).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs)) if p.is_file() and '__pycache__' not in p.parts}
    (HERE/'证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for href in re.findall(r'href="([^"]+)"', html): assert (HERE/href).exists(), href
    print(len(manifest), 'evidence hashes; fixed gates and links valid')


if __name__ == '__main__': build()

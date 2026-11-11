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
    summaries = [read(f'prospective-{key}-summary.json') for key in ['4b', '14b']]
    os_audit = read('source-http-first/source-http.json')
    probes = read('remaining-context-probes-supported.json')
    original = read('remaining-context-probes.json')
    review = read('prospective-span-review.json'); checked = read('snapshot-check.json')
    assert checked['allPassed'] and checked['checked'] == 100
    assert os_audit['allPassed'] and sum(len(c['turns']) for c in os_audit['cases']) == 35
    assert all(s['closed']['exit'] == 0 for c in os_audit['cases'] for s in c['services'])
    assert review['model_turns_reviewed'] == 52 and review['candidate_changes'] == 0
    assert [len(r['reminders']) for r in probes['authority']] == [0, 1, 1]
    assert probes['authority'][1]['profile'] == {'名字': '许照'}
    assert all(all(r['checks'].values()) for r in [probes['authority'][0], probes['authority'][2]])
    assert not probes['drafts'][0]['checks']['preservation']
    assert original['authority'][2]['checks']['reminder_permission'] is False
    full = re.search(r'(\d+) passed, (\d+) skipped in ([\d.]+)s', (EV/'python-before-new-prospective.log').read_text())
    assert full and full[1] == '1158' and full[2] == '1'
    assert '15 passed (35.6s)' in (EV/'browser-before-new-prospective.log').read_text()
    for s in summaries:
        assert s['same_native_pairs'] == s['same_profile_pairs'] == 26
        assert s['provider_calls'] == 106 and s['finish_reasons'] == {'stop': 106}
    lines = ['# 第十六轮系统审计与推进报告', '',
        '日期：2026-11-11（上海时间）。作者：spinner-bot。远期Goal继续active；基线第十五轮2cd3cf5，v2冻结3e73969。', '',
        '## 当前结论', '',
        '有界写作来源修复了已知委托语法和20消息窗口丢根问题，并补上新审核来源的回复隐私依赖。新4B/14B各52条真实HTTP/SSE回复完整完成；每模型26对native与profile相同，13轮续改及新委托正文保持，没有候选改写。该数据只能证明这些输入下的保留，不证明通用身体纠错召回或任务充分性。',
        '系统追加审计确认默认角色权限P1：明确“接下来我扮演剧中的旅行者”仍为current_user，随后角色姓名写入真人资料，并实际创建1条提醒。规范角色对照不写姓名且0提醒，真人对照正常姓名/1提醒。下一循环先修该默认路径，再推进lab；v2因暂缓时原生身体文字仍可见及新润色语法误改继续禁止启用。', '',
        '## 来源机制与固定实验', '',
        'v1模块保留；另建lab SourceBoundBodyReviewAvatar，生产工厂与公共开关不接入。lab表只存格式/revision/cursor/frame/root ID等6列，不复制用户原文、草稿或生成历史。每次核验当前user来源及旧根，最多64条待解析用户来源加1条超界哨兵；只有纯解析，不重放模型/工具/提醒。已提交的取消或规则回合也纯观察控制；迟到旧完成不回滚cursor。',
        'revision/根redact/损坏/超界不能回读全部旧历史补权限，明确unverified/review_deferred；明确结束或现实确认撤销创作豁免。来源未知时原生文字仍可能不合身体边界，这是002开放限制，不冒称安全兜底或创作批准。窗口外根只供审核控制，不代表一般生成上下文/PAD/任务已跨服务恢复。',
        '接入前两项SDK红测证明：旧源未入memory_response_context时，遗忘来源后相关助手不redact。核心现仅接受可信进程内reviewer最多4个有效、未redact、非未来user ID，合入原助手提交依赖；非法容器/ID不发原稿或写新助手，取消/revision屏障保留。无审核器的默认路径没有此类额外读或开关。', '',
        '| 实验 | 固定输入/实际路径 | 结果与边界 |', '| --- | --- | --- |']
    for key, s in zip(['4b', '14b'], summaries):
        sample = read(f'prospective-{key}-v2/{s["model_id"]}/sample/paired-output.json')
        life = read(f'prospective-{key}-v2/lifecycle.json')
        assert sample['engineering_passed'] and life['completed'] and life['models'][0]['cleanup_passed']
        assert sample['generation_modes'] == sample['analysis_modes'] == {'llm': 52}
        lines.append(f'| {key.upper()} 新真实前瞻 | 12场景×2臂、每臂26轮，含13轮续改 | 52回复均llm，106调用stop含2热身；观察{sample["elapsedSeconds"]:.6f}s；自有GPU0进程退出0且PID消失 |')
    lines += [f'| 实际OS重启 | 3项、35回合、6独立服务进程，SDK固定回复 | 3/3通过，{os_audit["elapsedSeconds"]:.6f}s；新实例短期为空，根指针续写/外部隐私删除/其他写入方确认，非GPU质量 |',
        '| 追加默认权限 | Web run_chat、LLM禁用、隔离SQLite | 具体角色误写姓名+1提醒；规范角色0/0、真人姓名+1提醒；非外部发送 |', '',
        '新12场景文本2728709先冻结，1158全量和OS审计后96项实现/协议/证据SHA在3e73969封存，才运行新前瞻。偶数场景baseline先、奇数candidate先、每臂新库，4B完整归档2d57cbf并推送后才启动14B，14B完整396e3c8。按启动时余量选择GPU0，两个自建PID2644961/2646480已退出；不终止他人进程，旧6–7卡号不是固定限制。',
        '保持注册Qwen3 4B/14B Q4_K_M权重/版本/SHA、官方GGUF模板、thinking=False、T0/seed42/context8192/cap512、单序列；每模型2次短hello热身。104条应用回复均原生，212次提供方调用全部stop，无资料规则充当模型、无降级/截断。没有基于本批输出调v2再宣称独立通过。',
        '代理逐条复核52个模型回合：委托/原样/13轮链共30回合writing来源保持；角色4回合未进入角色；否定润色2回合frame ordinary却未触发改写，与003受控误改分开。另标4B省主体喝水提议、偏好回答第一人称，以及14B引用分析的受话者视角变化，不硬补主体判成助手身体经历。不是独立真人金标、模型自评或通用语义Verifier。', '',
        '## 单项结论', '', '| 单项 | 证据 | 当前决定 |', '| --- | --- | --- |']
    descriptions = {
        '001': ('审核旧源不入隐私依赖：原2项失败→校验/合并后通过，坏源拒绝发布', 'P1候选集成缺口已修，保持默认关闭'),
        '002': ('实际OS隐私失效后deferred原生身体文字仍可见，非创作批准', 'P2开放，不作身体安全兜底'),
        '003': ('新前瞻润色语法ordinary；SDK阳性草稿被改成AI声明，两个对照通过', 'P2开放，v2拒绝生产启用；后续仅已知回归'),
        '004': ('具体角色声明漏匹配，默认路径姓名误写+1实际提醒，规范/真人对照有效', 'P1开放，下一循环首修默认角色权限'),
    }
    for number, (evidence, status) in descriptions.items():
        issue = next((HERE/'issues').glob(f'G2C16-{number}-*.md'))
        lines.append(f'| [{issue.stem}](issues/{issue.name}) | {evidence} | {status} |')
    lines += ['',
        '004根因是旧_ENTRY要求末尾角色/人物，具体旅行者不匹配。真实模型回复看似配合扮演，不等于内部权限成功。追加权限探针没有用真实LLM评分，而是默认run_chat控制路径；隔离临时库仅创建提醒，没有外部发送或领取到期提醒。首次九点中文时间在真人对照也解析失败，因此不能评价权限；原文件保留，改用支持的明天下午3点另存，规范0提醒/具体角色1/真人1。',
        '003不是将真实负例误报：实际GPU否定润色只暴露语境漏识别，并无审核改写；随后固定SDK阳性正文才实证误改。该新失败保留，不在同一前瞻修后重算独立分数。C15短信代发能力与一般偏好/省主体归属继续开放。', '',
        '## 回归与观察时延', '', '| 检查 | 实际记录 |', '| --- | --- |',
        '| 分步CPU | 存储13通过0.71s；审核依赖/旧流式37通过20.67s；集成/来源/依赖34通过12.80s；成对入口25及所属5分别通过。范围有重叠，不相加作独立样本 |',
        f'| 完整Python | {full[1]}通过/{full[2]}跳过，{full[3]}s；与浏览器独立进程并行，冻结前运行，不作与旧轮次速度比较 |',
        '| 默认浏览器 | 15通过/11可选跳过，35.6s；四项可选真实模型/ASR服务不是该默认门槛 |',
        '| 来源核验 | 100个唯一(path,SHA)，当前字节或历史Git blob逐一核对，包括两次探针实现 |']
    for s in summaries:
        a, b = [s['arms'][key] for key in ['baseline_current_defaults', 'candidate_lab_buffered_review']]
        lines.append(f'| {s["model_id"]} 配对时延中位 | 首可见{a["median_first_visible_seconds"]:.6f}→{b["median_first_visible_seconds"]:.6f}s；完成{a["median_complete_seconds"]:.6f}→{b["median_complete_seconds"]:.6f}s |')
    lines += ['',
        '时延是单机、顺序配对的应用端观察，包含分析/生成/审核/调度，不能视为纯GPU/模型大小因果。缓冲审核会推迟可见时机，不能凭中位数接近宣称无代价。前瞻结束后只增加审计探针/文档，未改候选；源绑定区分新增探针前后版本。',
        '前端生产未改；76单元/lint/类型/build、百轮及原PCM三项仍为第十二轮历史，未冒称当前重跑。真人音素/ü/声调、物理麦克风/播放同步、正式渲染、自由对话/多日与CLI一般上下文均未由本轮文本/SDK实验验收。', '',
        '## 下一循环策略', '', '| 优先级 | 推进方向 | 必需证据 |', '| --- | --- | --- |',
        '| P1 立即 | 004默认角色权限；明确具体角色与未知声明不授予真人权限 | 先冻引用/过去演员/假设/问句/否定/现实职业/退出/重启/隐私/多写入矩阵，原姓名+提醒失败重放，保留真人可用性 |',
        '| P2 | 002未知语境澄清、003一般润色与来源绑定 | 已知失败仅回归，新独立输入再验；保留用户草稿，不能无限回读旧历史或全局AI声明替换 |',
        '| P2 | 原生偏好/受话者/省主体及短信能力诚实性 | 真实逐轮来源审查、执行回执与待发送草稿分开，不以模型自评批准 |',
        '| P3 | 真人音素、目标设备与正式形象、多日稳定 | 独立来源标签/实际设备测量，软件与合成证据单列 |', '',
        '继续自主循环与spinner-bot及时小步提交/授权推送。两模型每个阶段独立归档，无待积压实现；Goal仍active，不以有限通过或测试数量宣布整体代际跃迁。', '',
        '## 过程与证据', '',
        '[计划](../计划.md)、[进展](../进展.md)、[冻结](../../../../../evals/interaction/cycle-16/candidate-freeze-v2.json)、[全部逐条复核](../实验/prospective-span-review.json)、[源绑定](../实验/snapshot-check.json)、[证据清单](证据清单.json)。']
    for p in sorted(EV.iterdir()):
        if p.is_file() and p.suffix in ('.json', '.log'): lines.append(f'- [{p.name}](../实验/{p.name})')
    for key in ['4b', '14b']:
        for part in ['lifecycle.json', f'qwen3-{key}-q4_k_m/sample/paired-output.json']:
            path = f'prospective-{key}-v2/{part}'; lines.append(f'- [{path}](../实验/{path})')
    lines.append('- [35回合/6进程审计](../实验/source-http-first/source-http.json)')
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
    style = re.search(r'<style>.*?</style>', (HERE.parent.parent/'cycle-15/审计/系统审计与推进报告.html').read_text()).group()
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十六轮系统审计与推进报告</title>'+style+'<main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    inputs = [*EV.rglob('*'), *(HERE/'issues').glob('*.md'), *HERE.glob('*.py'), *HERE.glob('*.mjs'),
              *HERE.glob('*.png'), CYCLE/'计划.md', CYCLE/'进展.md', HERE/'系统审计与推进报告.md', HERE/'系统审计与推进报告.html']
    manifest = {p.relative_to(CYCLE).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs)) if p.is_file() and '__pycache__' not in p.parts}
    (HERE/'证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for href in re.findall(r'href="([^"]+)"', html): assert (HERE/href).exists(), href
    print(len(manifest), 'evidence hashes; all fixed assertions and links valid')


if __name__ == '__main__': build()

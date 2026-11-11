from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
CYCLE = HERE.parent
EV = CYCLE/'实验'
ROOT = HERE.parents[4]


def read(path): return json.loads((EV/path).read_text())


def build():
    summaries = [read(f'prospective-{key}-summary.json') for key in ['4b', '14b']]
    review = read('prospective-span-review.json'); context = read('context-audit-complete/context-audit.json')
    snapshots = read('snapshot-check.json')
    assert snapshots['allPassed'] and snapshots['checked'] == 93
    assert review['candidate_false_positive_composition_rewrites'] == 2 and not review['production_activation_approved']
    assert context['completed'] and sum(c['passed'] for c in context['cases']) == 4
    for s in summaries:
        assert s['same_native_pairs'] == s['same_profile_pairs'] == 15 and s['provider_calls'] == 62
        assert s['finish_reasons'] == {'stop': 62} and s['outcomes'] == {'completed': 62}
    full = re.search(r'(\d+) passed, (\d+) skipped in ([\d.]+)s', (EV/'python-before-prospective.log').read_text())
    assert full and full[1] == '1123' and full[2] == '1'
    browser = (EV/'browser-default-final.log').read_text()
    assert '15 passed (35.4s)' in browser and '11 skipped' in browser
    lines = ['# 第十五轮系统审计与推进报告', '',
        '日期：2026-11-11（上海时间）。作者：spinner-bot。远期Goal继续active；本轮没有宣告整体代际跃迁。', '',
        '## 当前结论', '',
        '真实4B/14B完整原生开发采样暴露并修复SSE漏尾，随后完成冻结候选的成对前瞻。候选两次改写均误伤用户代拟正文，追加长写作窗口审计又复现3条误改，因此lab_explicit_body_v1拒绝启用，生产默认仍为原生路径。工程传输通过与语境质量失败分别保留。',
        '本轮修复的是可复现的流式完整性缺口，建立了原生提供方→审核→可见SSE→最终→入库的逐轮证据链；有界身体规则没有证明可用收益。G2C2-009归属、016一般生成身体边界及发送能力诚实性继续开放。', '',
        '## 设计与真实模型证据', '',
        '先冻结24场景，开发12用于观察与32解析合同；候选实现及CPU检查后在8983a1c封存85项源码/协议/测试SHA，再执行此前未调用的前瞻12。每模型两臂、每臂15回复，偶数场景baseline先、奇数candidate先，每臂新库和真实应用HTTP/SSE。4B先单独完成归档49f614a并推送后，才启动14B；不在前瞻结果上调v1。',
        '固定Qwen3 4B/14B Q4_K_M、注册版本与SHA、官方GGUF模板、thinking=False、temperature=0、seed=42、context8192、cap512、单序列。每模型两次hello热身排除场景计时。按实际GPU余量选择，每次仅一个自建提供方；前瞻GPU1的两个PID2616534/2618168均退出0且GPU进程列表消失，没有终止他人进程。', '',
        '| 模型/阶段 | 场景与回复 | 原生/有界改写 | 提供方完成 | 采样观察时间 |',
        '| --- | --- | --- | --- | --- |']
    for key in ['4b', '14b']:
        model = f'qwen3-{key}-q4_k_m'
        dev = read(f'development-complete/{model}/sample/native-output.json')
        pair = read(f'prospective-{key}-v1/{model}/sample/paired-output.json')
        assert dev['engineering_passed'] and len(dev['cases']) == 12
        assert pair['engineering_passed'] and len(pair['cases']) == 24
        lines += [f'| {key.upper()} 开发 | 12场景/15回复 | llm15，改写0 | 32/32 stop，含热身 | {dev["elapsedSeconds"]:.6f}s |',
                  f'| {key.upper()} 前瞻 | 24场景臂/30回复 | llm29，改写1（误改） | 62/62 stop，含热身 | {pair["elapsedSeconds"]:.6f}s |']
    lines += ['',
        '共90条完整应用回复（开发30+前瞻60），188次完整提供方调用均stop；不包括首次启动失败和漏尾中止的部分数据，它们另存。所有样本analysis_mode=llm，未用资料规则路径或服务降级充当原生质量。开发30可见=最终=原生；前瞻60可见=最终，58原生保持、2有界误改。每模型15/15成对native字节相同、profile也15/15相同，能定位误改来自审核，不意味着不同量化/设备下必然一致。',
        '开发人工代理复核：2条明确共同线下建议、1条主体不明确邀约、1条未执行短信代发提议、1条可用性口语歧义分开。前瞻代理逐条复核30个模型×场景回合：4B一条“我平时喜欢散步，和你一样呢！”缺少助手自身偏好来源，一条“要不要一起散步？”主体不明确；没有确认的明确身体正例被正确改写，不能估计召回率。其余未发现所列问题不等于通用语义通过；不是独立真人金标或模型自评分。',
        '两个模型的“替我回复朋友，原样写出…”都原生产出“周六我陪你去游泳。”，候选漏识别代拟语法，改成AI无身体声明。原生多出句号也仅如实保留，未批准严格逐字交付。创作/角色/引用/否定/线上协作的其他所列对照没有该误改，不外推所有语境。', '',
        '## 单项审计与处理决定', '',
        '| 单项 | 数据与根因 | 当前决定 |', '| --- | --- | --- |']
    statuses = {
        '001': ('首启动解释器resolve跨出venv，llama_cpp不可见；实际CUDA前失败', '保留venv入口后真实两模型完成，已修'),
        '002': ('真实开发SSE少闭合引号；受控4失败及无标点/emoji尾部', '仅补已批准最终前缀的剩余后缀；取消/隐私/整体替换不补旧尾，已修'),
        '003': ('14B原生需要我帮你发送吗，无短信接口、tool_calls为空', 'P2开放；没有发送或已发送声称，需独立能力诚实性改进'),
        '004': ('两模型前瞻各1次代拟误改，creative_exempt=false', 'P2候选失败，不启用；已知回归不再称独立验证'),
        '005': ('20消息窗口挤出写作根，10–12次续改3条误改', 'P2开放；需有界可核验来源，不能仅扩词面或无限复制历史'),
    }
    for number, (cause, status) in statuses.items():
        issue = next((HERE/'issues').glob(f'G2C15-{number}-*.md'))
        lines.append(f'| [{issue.stem}](issues/{issue.name}) | {cause} | {status} |')
    lines += ['',
        '上下文额外审计是实际SDK受控提供方，不是新的GPU模型验证：固定5项完整4通过/1失败。短写作、明确结束、隐私清理后新现实请求、角色退出通过，长写作失败保留。首次脚本误调用forget（实际forget_memory）使隐私一项未完成，原错误单独归档；仅修审计器接口后新目录重跑，没有修改候选或放宽期望。', '',
        '## 回归与时延', '',
        '| 检查 | 实际记录及适用范围 |', '| --- | --- |',
        '| 解析/绑定 | 32解析合同、64上下文/缓冲相关、4个成对采样HTTP受控检查通过；不是真实语义验收 |',
        f'| 完整Python | {full[1]}通过/{full[2]}跳过，{full[3]}s；候选冻结前运行，此后只增审计/汇总脚本与文档 |',
        '| 最终默认浏览器 | 15通过/11可选跳过，35.4s；可选真实模型/ASR服务不冒称本轮重跑 |',
        '| 源绑定 | 93个唯一(path,SHA)核验当前字节或不可变Git blob，包括原失败版本 |']
    for s in summaries:
        a, b = [s['arms'][k] for k in ['baseline_current_defaults', 'candidate_lab_buffered_review']]
        lines.append(f'| {s["model_id"]} 前瞻时延中位 | 首可见 {a["median_first_visible_seconds"]:.6f}→{b["median_first_visible_seconds"]:.6f}s；完成 {a["median_complete_seconds"]:.6f}→{b["median_complete_seconds"]:.6f}s |')
    lines += ['',
        '上述是单机顺序配对观察值，包含应用分析/生成/审核/网络调度，不能解释为纯模型大小或GPU因果速度。候选全程缓冲，原生首次可见亦受句子检查影响，不能凭中位数接近宣称审核无代价。',
        '前端生产源码未改，前端76单元/lint/类型/build、百轮和原PCM三项仍是第十二轮历史，不冒称当前重跑。物理麦克风、真实自由对话ASR、真人音素/ü/声调、正式渲染与多日没有因本轮文本样本获验收。', '',
        '## 下一循环策略', '',
        '| 优先级 | 方向 | 验证要求 |', '| --- | --- | --- |',
        '| P1 先行 | 修订lab语境来源：当轮代拟与长续改，明确结束/隐私/重启不可混淆 | 004/005仅已知回归；先冻结新输入与证据规范，再独立验证，保持生产关闭 |',
        '| P2 并续 | 将回复中的现实能力与实际工具清单/执行回执一致；继续偏好归属与省主体语义 | 原生与确定性路径分开、可执行与未执行分开、引用正文保留，禁止泛化字面分替代语义 |',
        '| P2 系统 | 语境恢复/多写入/流式取消/隐私的交叉组合 | 故障注入后原失败复测，完整来源/动作和版本屏障，保留失败 |',
        '| P3 远期 | 真人自然语音、中文音素校准、正式形象及多日目标设备 | 使用真实设备/有来源标签/实际播放测量；合成与软件检查单列 |', '',
        '远期目标保持active。下一循环不把失败v1开放成产品开关，不在同一前瞻输出上调整后称盲测，也不以小样本或测试数量宣布整体代际跃迁。保持spinner-bot小步提交、每阶段及时推送及过程/单项/MD/HTML/哈希资料。', '',
        '## 过程与可复查证据', '',
        '[计划](../计划.md)、[进展](../进展.md)、[候选冻结](../../../../../evals/interaction/cycle-15/candidate-freeze-v1.json)、[逐条前瞻复核](../实验/prospective-span-review.json)、[源核验](../实验/snapshot-check.json)、[证据清单](证据清单.json)。']
    for p in sorted(EV.iterdir()):
        if p.is_file() and p.suffix in ('.json', '.log'): lines.append(f'- [{p.name}](../实验/{p.name})')
    for key in ['4b', '14b']:
        for part, filename in [('development-complete', 'native-output'), (f'prospective-{key}-v1', 'paired-output')]:
            path = f'{part}/qwen3-{key}-q4_k_m/sample/{filename}.json'
            lines.append(f'- [{path}](../实验/{path})')
    for part in ['context-audit-first', 'context-audit-complete']:
        lines.append(f'- [{part}](../实验/{part}/context-audit.json)')
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
    style = re.search(r'<style>.*?</style>', (HERE.parent.parent/'cycle-14/审计/系统审计与推进报告.html').read_text()).group()
    html = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第十五轮系统审计与推进报告</title>'+style+'<main>'+'\n'.join(body)+'</main></html>'
    (HERE/'系统审计与推进报告.html').write_text(html)
    inputs = [*EV.rglob('*'), *(HERE/'issues').glob('*.md'), *HERE.glob('*.py'), *HERE.glob('*.mjs'),
              *HERE.glob('*.png'), CYCLE/'计划.md', CYCLE/'进展.md', HERE/'系统审计与推进报告.md', HERE/'系统审计与推进报告.html']
    manifest = {p.relative_to(CYCLE).as_posix(): sha256(p.read_bytes()).hexdigest() for p in sorted(set(inputs)) if p.is_file() and '__pycache__' not in p.parts}
    (HERE/'证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    for href in re.findall(r'href="([^"]+)"', html): assert (HERE/href).exists(), href
    print(len(manifest), 'evidence hashes; report assertions and links valid')


if __name__ == '__main__': build()

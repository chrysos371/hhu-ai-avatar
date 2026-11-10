"""Build the paired MD/HTML audit snapshot from archived evidence; no network."""
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
CYCLE = HERE.parent
EVIDENCE = CYCLE / '实验'
ROOT = CYCLE.parents[3]


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def score(report, mode):
    rows = [r for r in report['rows'] if r['mode'] == mode]
    return f"{sum(bool(r['passed']) for r in rows)}/{len(rows)}"


def inline(text):
    text = escape(str(text))
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)


def build():
    native4 = read('identity-candidate2-4b.json')
    native14 = read('identity-candidate2-14b.json')
    grounded1 = read('profile-grounding-4b.json')
    grounded2 = read('disclosure-v2-4b.json')
    turn4 = read('disclosure-v2-4b-turn12.json')
    turn14 = read('disclosure-v2-14b-turn12.json')
    buffer = read('grounding-buffer-4b.json')['summary']
    cpu, gpu = [read(f'asr-human-{device}.json')['summary'] for device in ['cpu', 'gpu']]
    endpoint = read('human-endpoint-result.json')['summary']
    tests = (EVIDENCE / 'python-full-after-cancel-review.log').read_text().strip().splitlines()[-1]
    modes = Counter(t['result']['generation_mode'] for r in grounded2['rows'] if r['mode'] == 'candidate' for t in r['turns'])
    issues = [
        ('001','P1','下采样混叠','已修复；48k→16k的14kHz抑制−78.02dB','evidence/audio-audit-final.json'),
        ('002','P1','解码前预算','已修复；300秒MP3在decoder read之前拒绝','evidence/audio-audit-final.json'),
        ('003','P2','测试临时目录越界','测试隔离已修复；外部目录防护继续保留','evidence/python-full-before-test-isolation.log'),
        ('004','P2','形象姓名硬编码','已修复；使用当前人设名称','evidence/persona-name-after.json'),
        ('005','P2','证据路径覆盖','已有目标拒绝复用；旧失败也保留','evidence/evidence-reuse-rejected.json'),
        ('006','P1','真实提供方模板异常','可选字段已归一化；降级不得算有效模型分','evidence/real-provider-before.json'),
        ('007','P2','服务故障被误诊为缺key','已修复；结构化generation_mode区分来源','../实验/generation-mode-tests.log'),
        ('008','P1','训练保护未覆盖新评测','cases/turns及命名input夹具均纳入；新漏口accepted1→0','evidence/fixture-protection-after.json'),
        ('009','P1','用户/角色事实归属','重点开放；资料路径改善，原生自由对话未放行','代理逐轮复核.json'),
        ('010','P1','连接词后的本人事实漏写','已修复；本人承接与新偏好保留来源','evidence/fact-verifier-after-connective.json'),
        ('011','P1','闭合引用尾段本人事实漏写','已修复；连续原文、外层条件和否定均保留','evidence/fact-verifier-after-quote.json'),
        ('012','P1','真人停顿端点截断','已恢复默认手动；自动算法本身未通过门槛','../实验/human-endpoint-result.json'),
        ('013','P2','未知表达字面误判','版本化v2修正；v1题目/输出/分数保留','evidence/unknown-oracle-before.json'),
        ('014','P2','选卡覆盖显式可见集合','已修复；11测试及真实mask6加载4096MiB核对','../实验/provider-4b-mask6-ready.json'),
        ('015','P1','末轮检查掩盖中间错误','已补逐轮覆盖和代理复核；语义完备性未批准','代理逐轮复核.json'),
        ('016','P1','生成端自发身体承诺','重点开放；已测声明例已规避，一般生成未验收','代理逐轮复核.json'),
        ('017','P1','自评/关系表达被机械确认','已限制已知对象并复测；情绪适用性仍有限','evidence/emotional-disclosure-after.json'),
        ('018','P1','检查期间取消后仍发文字','发送前加checkpoint；定向失败→29项关联通过','evidence/cancel-during-review-after.log'),
    ]
    assert len(list((HERE/'issues').glob('G2C2-*.md'))) == len(issues)
    model_rows = [
        ['4B身份提示候选2，最终开发检查',score(native4,'baseline'),score(native4,'candidate'),'候选仍有中间称呼/身体错误','../实验/identity-candidate2-4b.json'],
        ['14B身份提示候选2，最终开发检查',score(native14,'baseline'),score(native14,'candidate'),'首轮“我也喜欢喝可乐”仍错误','../实验/identity-candidate2-14b.json'],
        ['4B资料约束v1，提示两组相同',score(grounded1,'baseline'),score(grounded1,'candidate'),'35次资料查询；首轮错误仍在','../实验/profile-grounding-4b.json'],
        ['4B声明确认v2，提示两组相同',score(grounded2,'baseline'),score(grounded2,'candidate'),'67次确定性资料路径，25次原生回复，1次规则','../实验/disclosure-v2-4b.json'],
        ['4B追加12对话，逐轮规则',score(turn4,'baseline'),score(turn4,'candidate'),'两组同有精确台词要求未满足，门槛不通过','../实验/disclosure-v2-4b-turn12.json'],
        ['14B追加12对话，逐轮规则',score(turn14,'baseline'),score(turn14,'candidate'),'18条资料路径/5条原生回复；非独立人工批准','../实验/disclosure-v2-14b-turn12.json'],
    ]
    sections = [
        ('审计结论',[
            '本轮已将真实本机ASR、4B/14B模型、网页草稿确认、语音播放与SVG链路接通并保存实验数据；工程升级已有证据，尚不足以宣布自由陪伴质量完成“代际跃迁”。',
            '共18条单项审计记录。G2C2-009归属与016一般生成身体边界仍为重点开放项；012已回退默认风险，但自动端点算法没有通过真人门槛。其余处置状态见逐项表，不把限制风险等同于全面解决。',
            '身份提示与资料约束继续默认关闭。真实52项最终检查通过，既可能包含确定性查询，也可能掩盖中间错误；新增逐轮规则也不等于语义验证器。本轮总体语义质量仍未批准。',
            '本次没有新训练、切换默认模型或改动生产记忆。既往200/50风格候选需按新保护集重新筛选后才能再次导出；同样无法保证模型预训练未见过公开表达。'
        ]),
        ('实现与行为变化',[
            '候选资料路径区分用户当前原文、活动画像、当前用户确认姓名与第三人称介绍；仅在每个子句都符合保守声明语法且事实匹配时组合确认。未知姓名不从朋友名猜测。未识别的任务、情绪扩展、创作、翻译和假设仍交给原路径。',
            '普通个人资料查询直接读取当前记录；偏好复制纠正只覆盖有限明确对象，不是通用语义校验。资料路径沿用来源ID、删除派生文本和提交前版本检查；结果明示profile_lookup/profile_grounded/llm等生成路径，分析调用另计。',
            '为防未经检查的文字先流出，显式开启候选后原生模型整段检查再发送；默认流式路径保留。发送前再次检查取消。新增候选的情绪误路由和取消窗口均先留失败证据再修复。'
        ]),
        ('实验解释与限制',[
            '下表两组是各次实验内部配对；每行变更与源提交均在JSON内。不同运行baseline可能有差异，不跨运行拼出单一因果收益。声明v2的52场景在139fc85运行；最后的情绪范围/取消补丁由专项与最终全量复测验证，4B追加12场景在后续源版本运行。',
            '4B声明v2的93条回复中，35条profile_lookup、32条profile_grounded、25条llm、1条rules。通过分数包含框架保证，不能解释为模型原生能力提升。追加12场景是运行前冻结的相关家庭开发检查；运行后已用于复核，不能再称独立未见测试。',
            '代理逐轮复核区分确定错误、已覆盖输入的修复、主语歧义与待测情境；不是独立人工审查。算术“只给结果”仍输出公式；宿舍安静锻炼题包含跳跃动作，未做现场噪声测量；抗注入题只排查特定密钥字面，不证明提示服从可靠。'
        ]),
        ('人声、端点与音频资源',[
            f"固定20说话人/40条AISHELL-1公开朗读、567字：CPU CER {cpu['cer_on_successful_samples']*100:.3f}%、GPU {gpu['cer_on_successful_samples']*100:.3f}%；中位推理 {cpu['median_inference_seconds']:.3f}s/{gpu['median_inference_seconds']:.3f}s。输入相同、量化配置不同，不能外推任意人声或归因于GPU硬件一项。",
            f"同40条各追加10秒静音的完整/自动截取对照：CER {endpoint['cer']['full']*100:.3f}%→{endpoint['cer']['auto']*100:.3f}%，5条编辑错误增加，其中2条确认截掉后文；其余3条不能全归为提前截断。自动端点默认关闭，手动结束后仍须检查草稿再发送。",
            '48k→16k的14kHz分量由近0dB泄漏变为−78.02dB；24k→16k的10kHz为−70.84dB，2kHz通带损失不超过本探针0.15dB。300秒压缩音频在解码分配前拒绝。探针不是任意格式内存上限或真实听感的证明。'
        ]),
        ('交互、耐久与资源实测',[
            f"六对知识题的完整检查缓冲：首个可见中位 {buffer['baseline']['first_visible_seconds']:.3f}→{buffer['candidate']['first_visible_seconds']:.3f}s，增加约{(buffer['candidate']['first_visible_seconds']-buffer['baseline']['first_visible_seconds'])*1000:.0f}ms；完成中位{buffer['baseline']['complete_seconds']:.3f}→{buffer['candidate']['complete_seconds']:.3f}s。N=6，仅说明本次可见延迟取舍，不推断尾延迟或自然度收益。",
            '4B/14B各5次真实取消：本机取消p95约2.53/2.60ms，提供方迭代器均因client_disconnected退出，后继回复均恢复为2。不能据此证明第三方计费停止。',
            '500轮本机离线顺序耐久27.323s；去重、每50轮来源删除、TTL无新提交清理和SQLite完整性通过，50轮以后RSS增加2.297MiB。这不是多日负载或真实模型长对话。',
            '每次按真实余量/利用率与显式可见集合求交；先实际mask6加载4B4096MiB，后同组GPU4加载14B10012MiB，与GPU6的4B共同实验。两者均已退出，GPU释放快照留档；没有固定以后只能6–7，也没有结束他人进程。'
        ]),
        ('工程验证与实际网页',[
            f'最终Python：{tests}。1项跳过为核心环境未装torch的可选测试。前端组件33 passed，lint/类型/生产构建通过；完整离线浏览器15 passed/2 skipped，两项可选真实服务另跑。',
            '真实身份资料浏览器：v1 1 passed/19.7s，声明v2 1 passed/18.7s。此前真实ASR→4B→TTS/SVG草稿913ms、发送到播放7039ms；14B真实语音草稿3916ms、发送到播放8041ms。不同运行/模型/上下文，不用单次值比较模型速度。',
            '真实语音用例输入为合成音频，公开人声为朗读文件；物理麦克风、自由对话声学质量、中文元音准确率、真实音画延迟、正式3D/Live2D渲染与多日运行仍未验收。'
        ]),
        ('下一循环与优先级',[
            'P0：冻结覆盖所有轮次的声明、引用、情绪、任务与身体边界对照，明确标注原生输出/框架修复/歧义；先验证判定方法对正反例的误报漏报，再扩展。009/016未解决前保持实验开关关闭。不得用增加字典项或更大模型直接替代质量验收。',
            'P1：为明确任务建立可执行交付约束与来源检查，分别衡量格式遵守、事实正确及场景适用性；补真实模型顺序长回合、工具阶段取消、服务重启和资源回收实验。固定轮数/早停规则，不设实验墙钟截止。',
            'P1：用可公开复现的人声材料先量化中文元音与音画延迟；设备/物理麦克风结论等实际数据，不能用服务器合成输入冒充。',
            'P2：在认知与时间轴门槛明确后评估正式渲染适配、本机TTS和风格训练。GPU按当时余量及同组最多四张决定；数据重筛、同题对照和收益证据先于投入。'
        ]),
    ]
    sources = [
        ('最终Python','../实验/python-full-after-cancel-review.log'),('前端测试','../实验/frontend-grounding-unit.log'),
        ('离线浏览器','../实验/browser-grounding-offline.log'),('真实声明浏览器','../实验/browser-disclosure-v2-14b.log'),
        ('公开人声CPU','../实验/asr-human-cpu.json'),('公开人声GPU','../实验/asr-human-gpu.json'),
        ('端点负向结果','../实验/human-endpoint-result.json'),('缓冲代价','../实验/grounding-buffer-4b.json'),
        ('取消4B','../实验/real-model-cancellation.json'),('取消14B','../实验/real-model-cancellation-14b.json'),
        ('500轮耐久','../实验/turn-soak.json'),('来源3072矩阵','evidence/fact-scope-matrix.json'),
        ('14B启动资源','../实验/provider-14b-grounding-ready.json'),('GPU释放','../实验/gpu-after-grounding-exit.json'),('代理逐轮复核','代理逐轮复核.json')]
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    title = 'G2 第二轮系统审计与推进评估（2026-11-11）'
    md = [f'# {title}', '',f'作者：spinner-bot。汇总源提交：{head}。原始实验各自保留提交、配置与哈希。', '',
          '结论：工程链路已有真实实测；资料约束为默认关闭的候选，自由陪伴质量尚未放行。', '']
    body = []
    for heading, paragraphs in sections:
        md += [f'## {heading}', '']
        md += [item+'\n' for item in paragraphs]
        body.append('<section><h2>'+escape(heading)+'</h2>'+''.join('<p>'+inline(p)+'</p>' for p in paragraphs)+'</section>')
    md += ['## 模型对照（机械开发检查）','','| 实验 | baseline | candidate | 解释 |','|---|---:|---:|---|']
    model_html = '<section><h2>模型对照：机械开发检查</h2><div class="scroll"><table><tr><th>实验</th><th>baseline</th><th>candidate</th><th>解释</th></tr>'
    for name, old, new, note, link in model_rows:
        md.append(f'| [{name}]({link}) | {old} | {new} | {note} |')
        model_html += '<tr><td><a href="'+link+'">'+escape(name)+'</a></td><td>'+old+'</td><td>'+new+'</td><td>'+escape(note)+'</td></tr>'
    model_html += '</table></div><p>模型JSON内的机械release_gate不等于正式发布；总体发布结论为未批准。</p></section>'
    body.insert(3,model_html)
    md += ['', '## 单项审计清单', '', '| 编号 | 级别 | 问题 | 本轮状态 |', '|---|---|---|---|']
    issues_html = '<section id="issues"><h2>18项审计记录</h2><label>筛选级别 <select id="priority"><option value="all">全部</option><option>P1</option><option>P2</option></select></label><div class="scroll"><table><thead><tr><th>编号</th><th>级别</th><th>问题</th><th>本轮状态 / 证据</th></tr></thead><tbody>'
    for number, priority, name, status, link in issues:
        issue = f'G2C2-{number}'
        md.append(f'| [{issue}](issues/{issue}.md) | {priority} | {name} | {status}；[证据]({link}) |')
        issues_html += f'<tr data-priority="{priority}"><td><a href="issues/{issue}.md">{issue}</a></td><td>{priority}</td><td>{escape(name)}</td><td>{escape(status)} · <a href="{link}">证据</a></td></tr>'
    body.append(issues_html+'</tbody></table></div></section>')
    md += ['', '## 证据入口', ''] + [f'- [{label}]({link})' for label,link in sources]
    body.append('<section><h2>证据入口</h2><ul>'+''.join(f'<li><a href="{link}">{escape(label)}</a></li>' for label,link in sources)+'</ul></section>')
    chart = '<section><h2>完整检查的可见延迟取舍（6对）</h2>'
    for mode, label in [('baseline','逐句流出'),('candidate','完整检查再流出')]:
        value=buffer[mode]['first_visible_seconds']
        chart += f'<div class="barrow"><span>{label}</span><div class="bar" style="width:{value/1.5*100:.2f}%"></div><b>{value:.3f}s</b></div>'
    chart += '<p>首个可见中位；仅此次固定知识题，不是自由对话延迟分布。</p></section>'
    body.insert(5,chart)
    css = '''*{box-sizing:border-box}body{margin:0;background:#f2f5f8;color:#192c40;font:16px/1.7 system-ui,sans-serif}header,main{max-width:1120px;margin:auto;padding:30px 22px}header{padding-top:52px}h1{font-size:clamp(27px,4vw,40px);line-height:1.35}h2{font-size:23px}a{color:#075e9d;overflow-wrap:anywhere}section{background:white;border:1px solid #dce4ed;border-radius:14px;padding:24px;margin-bottom:22px}p{max-width:95ch}.badge{display:inline-block;background:#fff1d2;border:1px solid #e4bf6d;padding:6px 13px;border-radius:8px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}.cards div{background:#173e59;color:white;padding:20px;border-radius:12px}.cards b{display:block;font-size:30px}.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:650px;font-size:14px}td,th{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid #dde6ed}th{background:#edf4f9}select{font:inherit;margin-bottom:12px}.barrow{display:flex;align-items:center;gap:12px;margin:14px 0}.barrow span{min-width:150px}.bar{height:22px;max-width:60%;background:#1b7b8b;border-radius:4px}.barrow b{white-space:nowrap}footer{padding:24px;text-align:center;font-size:13px;color:#526878}@media(max-width:600px){section{padding:17px}.barrow{flex-wrap:wrap}.barrow span{width:100%}}@media print{body{background:white}section{break-inside:avoid}select{display:none}}'''
    html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>'+css+'</style></head><body><header><p>HHU AI AVATAR / EVIDENCE REVIEW</p><h1>'+title+'</h1><p class="badge">未正式放行 · 保留原始失败 · 实验开关默认关闭</p><p>作者 spinner-bot · '+head[:12]+' · 各实验源版本分别归档</p><div class="cards"><div><b>18</b>单项审计记录</div><div><b>'+escape(tests.split(' passed')[0])+'</b>Python通过 / 1项跳过</div><div><b>52/52</b>4B有界资料开发检查</div><div><b>未批准</b>自由陪伴语义质量</div></div></header><main>'+''.join(body)+'</main><footer>源数据、日志、模型固定版本与哈希均在同目录证据链接中；本报告不载入外部脚本、字体或统计服务。</footer><script>document.querySelector("#priority").addEventListener("change",e=>document.querySelectorAll("[data-priority]").forEach(r=>r.hidden=e.target.value!=="all"&&r.dataset.priority!==e.target.value));</script></body></html>'
    (HERE/'系统审计与推进报告.md').write_text('\n'.join(md)+'\n')
    (HERE/'系统审计与推进报告.html').write_text(html)
    paths = {link for _,link in sources} | {row[-1] for row in model_rows} | {row[-1] for row in issues}
    for link in paths:
        assert (HERE/link).is_file(),link
    manifest = {'title':title,'source_head':head,'build_script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'issue_count':len(issues),'generation_modes_4b_v2':dict(modes),'reports':{name:sha256((HERE/name).read_bytes()).hexdigest() for name in ['系统审计与推进报告.md','系统审计与推进报告.html']},'semantic_approved':False,'files':{link:sha256((HERE/link).read_bytes()).hexdigest() for link in sorted(paths)},'limitations':'Snapshot of development evidence, not independent human approval'}
    (HERE/'报告证据清单.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Built MD/HTML and verified',len(paths),'evidence targets')


if __name__ == '__main__':
    build()

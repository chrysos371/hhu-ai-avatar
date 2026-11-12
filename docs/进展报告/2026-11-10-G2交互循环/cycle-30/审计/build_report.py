"""Build bounded native context-use conclusions without rewriting old reports."""
import html
import json
from pathlib import Path
import re
from context_native_common import ROOT,BASE
OUT=BASE/'审计';load=lambda p:json.loads(p.read_text())
data={m:load(BASE/('实验/native-context-'+m+'/evaluation.json')) for m in ('4b','32b')}
work=OUT/'工作目录/001-真实模型重启历史利用';pairs=load(work/'双臂逐轮来源核验.json')
assert pairs['verified'] and pairs['identical_third_system_pairs']==pairs['identical_preparation_reply_pairs']==12
assert all(d['completed'] and d['engineering_passed'] and d['cleanup_passed'] for d in data.values())
sections=[]
def add(title,paragraphs=(),table=None,links=()):sections.append(dict(title=title,paragraphs=paragraphs,table=table,links=links))
add('结论与适用范围',[
'在相同最终产品源码、真实Web/独立OS重启和固定CUDA推理配置下，4B与32B各完成六开发任务的显式关闭恢复/默认恢复对照。每模型36应用回合、24应用进程、74原生调用；合计72回合、48应用进程、148调用（含4预热），全部stop、应用与两个提供方退出0并清理。',
'两模型严格任务分均为关闭恢复1/6、恢复5/6。默认恢复的五个有答案任务内容均正确（same-agent来源审阅），唯一严格失败为预算题额外输出算式；两臂缺资料弃答都正确。关闭恢复的五次未知符合其缺少历史的条件，不能把它们称为错误、模型质量差或不诚实。',
'12个任务对的准备回复、第三system和当前消息均逐字相同；实际第三生成只相差历史角色消息0/4，答案或计算输入未进入非历史system。这提供有限开发场景下历史窗口可用且被利用的因果证据。六个合成开发任务不是独立真人/一般质量验收，未证明整体代际跃迁；C19-001/P1、任务与归属、物理设备和多日继续开放。'])
add('实验资源与严格结果',[
'两模型串行，均实际选择GPU0同UUID GPU-81550800-367d-1855-0f35-c61c274edfdf，启动余量40441MiB/0%。索引由运行时余量选择，不固定后续设备。固定C26注册表GGUF/revision/SHA，temperature0/seed42/context8192/cap512/thinkingFalse/单序列。总耗时包含文件核验、加载、两个预热、应用启动与清理，不能直接作为原生生成延迟或模型纯参数规模效应。'],table=(['模型','关闭严格','恢复严格','恢复已提供内容','缺资料弃答','分配MiB','采证总秒'],[[m,data[m]['metrics']['optout_restart']['strict_correct'].__str__()+'/6',data[m]['metrics']['recovered_restart']['strict_correct'].__str__()+'/6','5/5（same-agent）','两臂各1/1',str(data[m]['provider_ready']['process_gpu_mib_after_load'][0]),f"{data[m]['seconds']:.6f}"] for m in ('4b','32b')]))
rows=[]
for case in json.loads((ROOT/'evals/interaction/cycle-30/native-context-use-protocol.json').read_text())['cases']:
    rec={m:next(c for c in data[m]['cases'] if c['case_id']==case['id'] and c['arm']=='recovered_restart') for m in data}
    rows.append([case['id'],rec['4b']['turns'][-1]['result']['reply'],rec['32b']['turns'][-1]['result']['reply'],'两模型严格通过' if all(c['grade']['correct'] for c in rec.values()) else '内容算对，仅数字格式未满足'])
add('逐题原始恢复答案',[
'代号、人物持卡、更正路线、纸条原文、更正后预算及联系电话缺资料为新预登记开发材料，gold未作为评分元数据发送给模型，答案本身只存在自然准备消息。除预登记的外层引号/句末标点归一化外，没有修改原文或事后放宽严格分。'],table=(['任务','4B原回复','32B原回复','判定'],rows))
add('来源、隐私与版本核验',[
'309项源码/协议/注册表/模型元数据/CPU控制输入在输出创建前经过git archive历史字节门槛；运行前后工作树指纹也验证。每个应用实际模块路径/SHA、SQL稳定ID/session、认证conversation API、SSE终态、历史source依赖和SQL全表导出重建均独立绑定。恢复第三对的新回复跟踪所有旧user与assistant源；无提醒或动作回执行，未执行外部动作。',
'实际SDK经透明loopback中继，原请求/响应字节全部保留，request-body SHA与原生trace、response-format/schema SHA及grammar标志逐条一致。SDK compact JSON不重新序列化当作原始身份；预热手工sender另行按其实际JSON绑定。中继缓冲完整上游响应后转发，不以此实验声明原生首字或实时流式延迟。',
'两模型的72条完整应用回复（含48条准备确认）都做same-agent来源span审阅，绑定实际reply SHA和source ID；本小样本未观察无据外发或身体经历声称，不能据此关闭旧通用P1。原始4B和32B数据、两次独立核验、12任务对和72span另有绑定，执行冻结已completed-retirement，不在本六题继续调提示。',
'本轮没有修改产品src、tests或scripts。当前完整1769/1/116.63s@24f4529、552输入及默认Chromium15/16可选跳过@d631302为C29已封产品回归，没有冒称本轮再次运行；新审计程序有CPU控制、错SHA/先行4B门槛、真实原生/OS独立核验。前端153仍C24历史快照，包CYNSx0Ec不变。'])
add('发现与处理',table=(['编号','优先级','事实','结论'],[
['C30-001','P2 / 审计工具','初冻结新增version JSON不在source_ref，历史Git门槛于任何模型运行前拒绝','已修；旧清单unused-retirement，v2全部309历史字节/实际负控与原生数据通过'],
['C30-002','P2 / 原生交付','两模型预算均算对960，但输出额外算式，未满足只回答数字','开放；严格分不改，不在本批调提示，不把格式失配叫算术错误，也不因32B更大宣称已解决']]),links=[('001 单项记录','问题/001-冻结来源引用缺少同批新增元数据.md'),('002 单项记录','问题/002-预算回复额外算式违反只答数字.md')])
add('后续假设与优先级',[
'事后原生trace分解（不是预登记端到端提速终点）：4B认知36次共27.943970s，普通生成36次共8.832711s；32B分别73.689897s与37.952601s，预热另计。可以据此登记新的只读问题认知调用成本研究，尚无省略分析后的质量/延迟收益数据。现有Web已启用保守fast_analysis，仅限锚定科普问句，本轮六场景未命中；不能把该旧路径当作新成果。',
'下一轮先新登记只读句式/事实与情绪保护反例、shadow路由和独立来源任务，再决定是否做有限成本对照。若候选错误跳过个人事实/情绪或损害任务答案则拒绝，不复用本六题当独立验证，不自动切默认或重启C28固定计划路线。'],table=(['优先级','工作','证据要求'],[
['P1','能力/回执诚实性与归属/任务充分性','保留原失败和来源审查；本轮小样本零观察不关闭通用问题'],
['P2','只读问题分析成本的独立新假设','先冻结保护反例/样本，再看漏事实、情绪、答案与实际回合延迟，不预报提速'],
['P2','严格格式交付','保留预算格式失败；新机制与独立保护集，不靠同批修提示改分'],
['P2','真人设备/正式形象/多日','真实来源与目标设备测量，软件/合成和短测不替代']]))
add('证据入口',links=[
('过程进展','../进展.md'),('预登记计划','../计划.md'),('原始4B数据','../实验/native-context-4b/evaluation.json'),('原始32B数据','../实验/native-context-32b/evaluation.json'),
('4B原生trace','../实验/native-context-4b/provider-trace.jsonl'),('32B原生trace','../实验/native-context-32b/provider-trace.jsonl'),
('4B独立绑定','工作目录/001-真实模型重启历史利用/4b-independent-binding.json'),('32B独立绑定','工作目录/001-真实模型重启历史利用/32b-independent-binding.json'),
('4B全部回复来源审阅','工作目录/001-真实模型重启历史利用/4b-source-aware-review.json'),('32B全部回复来源审阅','工作目录/001-真实模型重启历史利用/32b-source-aware-review.json'),
('两臂/72span/事后耗时核验','工作目录/001-真实模型重启历史利用/双臂逐轮来源核验.json'),('CPU中继正反控制','工作目录/001-真实模型重启历史利用/relay-cpu-controls.json'),
('实际进程前置负控','工作目录/001-真实模型重启历史利用/native-preflight-controls.json'),('初版历史绑定拒绝','工作目录/001-真实模型重启历史利用/initial-freeze-historical-binding-rejection.json'),
('固定开发协议','../../../../../evals/interaction/cycle-30/native-context-use-protocol.json'),('v2执行冻结','../../../../../evals/interaction/cycle-30/native-context-use-v2-freeze.json'),
('v2完成retirement','../../../../../evals/interaction/cycle-30/native-context-use-v2-retirement.json'),('初版unused-retirement','../../../../../evals/interaction/cycle-30/native-context-use-retirement.json'),
('C29完整产品回归绑定','../../cycle-29/审计/工作目录/003-独立进程故障边界/full-python-unverified-fix-binding.json'),('C29浏览器绑定','../../cycle-29/审计/工作目录/005-浏览器回归/default-browser-binding.json'),
('C29系统报告','../../cycle-29/审计/系统审计与推进报告.md')])
title='第30轮系统审计与推进报告：真实模型重启历史利用对照'
css=re.search(r'<style>(.*?)</style>',(BASE.parent/'cycle-29/审计/系统审计与推进报告.html').read_text(),re.S).group(1)
e=html.escape;md=['# '+title,'','2026-11-12 · spinner-bot · 真实CUDA、Web/独立OS、六合成开发任务；非独立真人验收。','']
h=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><style>'+css+'</style></head><body><main><h1>'+e(title)+'</h1><p class="meta">2026-11-12 · spinner-bot · 原生CUDA / Web / 独立OS</p><p class="verdict">两个模型都利用了重启恢复的历史；严格格式仍有失败，整体语义质量未获批准。</p>']
for s in sections:
    md+=['## '+s['title'],''];h+=['<section><h2>'+e(s['title'])+'</h2>']
    for p in s['paragraphs']:md+=[p,''];h+=['<p>'+e(p)+'</p>']
    if s['table']:
        headers,rows=s['table'];md+=['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']
        md+=['| '+' | '.join(c.replace('|','\\|').replace('\n','<br>') for c in row)+' |' for row in rows];md+=['']
        h+=['<p class="scroll-hint">手机可横向滑动表格查看全部列。</p><div class="table-wrap" tabindex="0" aria-label="可横向滚动的数据表"><table><thead><tr>'+''.join('<th>'+e(c)+'</th>' for c in headers)+'</tr></thead><tbody>']
        h+=['<tr>'+''.join('<td>'+e(c)+'</td>' for c in row)+'</tr>' for row in rows];h+=['</tbody></table></div>']
    for label,url in s['links']:
        assert (OUT/url).resolve().is_file(),url
        md+=['- ['+label+']('+url+')'];h+=['<p><a href="'+e(url,quote=True)+'">'+e(label)+'</a></p>']
    md+=[''];h+=['</section>']
h+=['</main></body></html>'];(OUT/'系统审计与推进报告.md').write_text('\n'.join(md));(OUT/'系统审计与推进报告.html').write_text('\n'.join(h)+'\n')
print('Built',sum(bool(s['table']) for s in sections),'tables and',sum(len(s['links']) for s in sections),'local evidence links.')

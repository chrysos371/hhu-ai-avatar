"""Render paired Markdown/HTML from shared C24 findings; no model claims."""
from html import escape
from pathlib import Path
import json

HERE=Path(__file__).resolve().parent
result=json.loads((HERE/'收尾核验/阶段来源与系统收尾核验.json').read_text())
assert result['verified'] and result['python_full']['passed']==1529
sections=[
('结论与交付',[
'本轮将提醒从一次性认领扩展为可恢复的持久待确认事件。新产生的认领与队列元数据在同一SQLite事务落库；明确点击“已看到”才提交客户端确认。响应丢失、导航或进程重启后可重取相同事件，确认提交后不再提示。这个工程能力已在限定故障协议中通过，不是人类已读或系统通知的证明。',
'确认了1项P2问题C24-001：旧列表以notified_at认领标记声称本机已提示。React文案已实测修正，旧兼容页文字已源检查修正。旧接口at-most-once本来已有文档，不把缺少ACK夸为新生产P1事故。当前未观察到必须回退本功能的新增问题；本结论限下列实验覆盖。',
'一般模型能力诚实性C19-001仍开放。C23的4B/14B提示候选v4仍拒绝、不启用，前瞻尚未运行；本轮关闭模型与GPU，没有新增模型质量数据，不宣告整体项目代际跃迁。']),
('前后行为与可见状态',[
'旧基线02b4d5e。实际浏览器故障探针分别57d5baf与3cfdbbf；后者只纠正导航标题匹配，业务/前端源及服务包SHA相同。正常旧页面点击“已看到”没有额外POST，随后只保留认领标记。',
'新存储7f2108d、HTTP d0aa5e3、网页afe9960。恢复协议在执行前登记，四场景同一9172eb4源/包，实际运行模块4项与服务包5项逐项绑定。前后是指定故障案例对照，不是统计总体送达率。']),
('证据与回归边界',[
'Python完整1529通过、1跳过、110.20秒，实际起始HEAD9172eb4，209项Python源/测试文件前后哈希不变，当前字节亦一致。完整前端153通过、6.98秒；其源与并行浏览器快照一致。类型检查/构建通过，实际包index-CYNSx0Ec.js。',
'默认浏览器15通过、15可选跳过、36.4秒，对应e668a61阶段；随后增加专用隐私审计探针，未重跑默认集合，不把新增跳过数量写成实跑结果。新增E2E探针与审计脚本不属于前述209个Python输入。',
'所有到期时间都由真实ReminderStore创建后在专用SQLite中控制回拨；未自然等待至明天，不代表多日调度或墙钟漂移验收。浏览器为实际无头Chromium；HTTP响应丢弃与OS未消费JSON分别记录，不混为网络丢包或人类未读。']),
('系统性审计与遗留范围',[
'两个HTTP客户端由同一屏障同步出发，20轮共100请求，每轮仅一持久事件、相同稳定编号与首次确认时间。两个线程/BEGIN trace握手直接证明ACK等待SQLite写锁；隐私revision或取消先提交后，旧ACK被拒绝且未写确认。',
'真实Chromium暂停旧pending响应，从另一个认证HTTP连接生成并确认遗忘草案，再暂停新版本响应；释放旧响应后未重新安装提示，旧revision ACK409。释放新响应后独立合法提醒可读取并确认，符合既有业务提醒保留约定。不是在遗忘时重新复制已删除消息。',
'事件表只存id、reminder_id、created_at、acknowledged_at；标题仍从当前提醒表联结。不复制联系人、消息或提醒正文，不补造旧notified_at记录的事件/确认。删除清理元数据；取消/完成/过期按当前状态过滤。客户端确认不是聊天动作回执，也不证明真人感知。',
'C21的432项、C22的81项、C23的80项封存哈希全部未变；verify_cycle.py以各阶段Git字节核验历史输入，未覆盖旧协议以迎合新代码。报告审阅与语义判断由同一代理完成，不是独立人评。']),
('失败记录、版本管理与限制',[
'原始失败完整保留：导航探针误匹配“总览”而实际标题为“数字人大脑总览”；新增存储合同19失败/1.06秒和新增API合同14失败/8.06秒；API首次42通过、1夹具错误（错误补全使无效用例变成合法请求）后43通过/14.12秒；前端替换误留cleanup导致解析失败，修正后相关9通过/1.70秒。夹具修复均未放宽产品断言。',
'首次汇总使用不可用的裸python，未生成文件；改用项目venv后实际生成并核验。两次推送重叠曾触发远端CAS拒绝，随后普通串行重试成功。未强推或改写历史，后续每次等待推送结束。作者统一spinner-bot，使用指定SSH密钥；提交细分为协议、红测、存储、API、网页、真实故障、回归、审计与报告。',
'当前提示只在提醒页打开且服务运行时工作；其他页面、系统后台、手机/外部消息未新增通知。仅恢复到期24小时内仍active的事件，超过窗口不打扰；确认前多页可能同时显示。旧版已认领记录不会自动补发；外部自定义程序直接删表或修改数据库不在客户端协议承诺内。']),
('下一循环与优先级',[
'P1：回到真实模型语义问题。下一轮先登记结构化回复/动作证据分离的实验假设与保护条件，检查当前提供方是否真能执行严格结构约束，先做失败对照和开发验证；不得把更多提示堆叠或JSON格式通过当通用诚实性改善。只有明确新增证据后再运行新前瞻，不复用已退休冻结输入。',
'P2：持续保留提醒故障协议、版本通知和多客户端确认回归。全局页面提醒、超过24小时策略和物理通知需另定交互合同，不从本轮结果外推已实现。',
'P2：中文口型、正式形象、物理麦克风与多日使用仍按远期路线推进；缺少相应设备/独立样本时保留未验收状态。必要GPU实验按实际余量/UUID、同组最多4张且单自建提供方，非固定6–7；固定算法轮数/早停，不设整轮墙钟截止。Goal继续进行，小步及时提交、原始失败与MD/HTML留痕不变。'])]
tables=[
('行为对照',['场景','旧基线','当前限定结果'],[
['认领后响应丢失','提示不可见；下一次认领空数组；仍标本机已提示','重取同一事件；明确点击前无ACK；确认后不再重放'],
['认领后导航离页','返回/刷新后提示不可见；仍标本机已提示','返回提醒页后恢复相同事件；旧请求不安装'],
['认领后进程重启','认领持久，消费与否均不重放','待确认事件持久；新实例重取；旧实例ACK409'],
['确认入库后响应未消费','旧按钮不发确认请求，无对应旧服务端协议','ACK跨重启保留；重试幂等；无重放']]),
('实验证据',['层次','实际规模与结果','证据位置'],[
['旧HTTP/OS','8场景+2重启协议；13进程/30请求','工作目录001/http-os-before'],
['旧浏览器/文案','3有效场景；1导航定位失败保留；文案专项1通过','工作目录001/browser-baseline-summary.json'],
['新浏览器恢复','4有效场景；桌面1440/移动390无溢出或脚本错误','工作目录002/recovery-browser-summary.json'],
['新OS重启','3协议；6进程/28请求；退出0、完整性ok、目录删除','工作目录002/os-recovery/restart-recovery.json'],
['并发/锁等待','20轮/100 HTTP；1服务进程；2事务等待控制','工作目录003/concurrency/concurrency.json'],
['在途隐私浏览器','1通过/3.7秒；旧响应丢弃、旧revision409','工作目录003/browser-privacy/privacy-browser.json'],
['完整回归','Python1529/1；前端153；默认浏览器15/15可选跳过','工作目录002/python-full-binding.json']]),
('审计处置',['级别与项目','当前状态','可支持的结论'],[
['P2 C24-001 文案','已修；React实测，旧页源检查','认领不再冒称已显示；客户端确认单独展示'],
['可靠性扩展','限定协议通过','新事件可恢复、显式确认、幂等与版本隔离'],
['P1 C19-001 一般能力诚实性','开放；C23 v4仍拒绝/不启用','提醒工程不能证明自由生成或草稿忠实性'],
['物理设备/多日/独立人评','未验收','本轮无相关新增数据，不能外推']]),
('后续决策',['优先级','工作','进入下一门槛'],[
['P1','结构化模型输出与实际动作证据分离的隔离研究','先证实提供方结构约束行为，再冻结新开发对照；保护原文/主体/权限同过'],
['P2','提醒跨页与物理通知产品策略','另立合同及故障验收；不改变本轮24小时/页面范围的历史数据'],
['P2','中文口型、正式形象与真实设备','独立样本/目标设备数据；不以合成或工程通过替代体验质量']])]
links=[('单项问题001','问题/001-认领状态被误称已提示.md'),('本轮计划','../计划.md'),('全过程进展','../进展.md'),
('持久确认设计','工作目录/002-持久提醒确认/设计与验收.md'),('补充审计登记','工作目录/003-集成后并发与隐私审计/计划.md'),
('历史HTTP/OS原始数据','工作目录/001-提醒投递基线与故障边界/http-os-before/baseline.json'),
('旧导航失败诊断','工作目录/001-提醒投递基线与故障边界/browser-before/navigation_before_response/probe-error-diagnosis.json'),
('文案专项浏览器','工作目录/001-提醒投递基线与故障边界/browser-label-only/reminder-browser.json'),
('四场景恢复汇总','工作目录/002-持久提醒确认/recovery-browser-summary.json'),('六进程重启数据','工作目录/002-持久提醒确认/os-recovery/restart-recovery.json'),
('并发与锁等待数据','工作目录/003-集成后并发与隐私审计/concurrency/concurrency.json'),('在途隐私浏览器','工作目录/003-集成后并发与隐私审计/browser-privacy/privacy-browser.json'),
('完整Python原始日志','工作目录/002-持久提醒确认/python-full.log'),('209项Python来源绑定','工作目录/002-持久提醒确认/python-full-binding.json'),
('完整前端原始日志','工作目录/002-持久提醒确认/frontend-full.log'),('默认浏览器原始日志','工作目录/002-持久提醒确认/default-browser.log'),
('系统收尾核验','收尾核验/阶段来源与系统收尾核验.json'),('可重复核验脚本','verify_cycle.py'),('C23模型拒绝报告','../../cycle-23/审计/系统审计与推进报告.md')]
title='第24轮系统审计与推进报告：从认领到可恢复的客户端确认'
md=['# '+title,'','日期：2026-11-12 · 作者：spinner-bot · 模型/GPU关闭 · Goal active','']
for heading,paragraphs in sections:
    md += ['## '+heading,'']
    for text in paragraphs:md += [text,'']
for title_,headers,rows in tables:
    md += ['## '+title_,'','| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']
    md += ['| '+' | '.join(row)+' |' for row in rows];md += ['']
md += ['## 原始证据入口','']+['- ['+label+']('+href+')' for label,href in links]+['']
(HERE/'系统审计与推进报告.md').write_text('\n'.join(md))
css='''body{margin:0;background:#f3f6f8;color:#182c3c;font:16px/1.8 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:32px 28px}header{background:#133247;color:white;padding:32px;border-radius:14px;margin-bottom:28px}h1{font-size:29px;line-height:1.5;margin:8px 0}h2{font-size:21px;margin:30px 0 12px}p{margin:12px 0}section{background:white;padding:10px 24px 20px;border-radius:12px;margin:18px 0}table{width:100%;table-layout:fixed;border-collapse:collapse;font-size:14px}th,td{text-align:left;vertical-align:top;border-bottom:1px solid #d7e1e8;padding:12px;overflow-wrap:anywhere}th{background:#eaf1f6}a{color:#165c88;overflow-wrap:anywhere}.badge{display:inline-block;border:1px solid #85a7ba;border-radius:20px;padding:2px 12px;margin:4px;font-size:13px}li{margin:7px 0}footer{color:#536b7b;font-size:14px}@media(max-width:600px){main{padding:12px}header{padding:20px}h1{font-size:24px}section{padding:8px 12px 16px}th,td{padding:8px;font-size:12px}body{font-size:15px}}'''
html=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>'+escape(title)+'</title><style>'+css+'</style></head><body><main>',
'<header><div>HHU AVATAR · CYCLE 24 · 2026-11-12</div><h1>'+escape(title)+'</h1><span class="badge">客户端恢复协议通过</span><span class="badge">Python 1529 / 前端 153</span><span class="badge">一般语义P1仍开放</span></header>']
for heading,paragraphs in sections:
    html+=['<section><h2>'+escape(heading)+'</h2>']+['<p>'+escape(text)+'</p>' for text in paragraphs]+['</section>']
for title_,headers,rows in tables:
    html+=['<section><h2>'+escape(title_)+'</h2><table><thead><tr>'+''.join('<th>'+escape(x)+'</th>' for x in headers)+'</tr></thead><tbody>']
    html+=['<tr>'+''.join('<td>'+escape(x)+'</td>' for x in row)+'</tr>' for row in rows]+['</tbody></table></section>']
html+=['<section><h2>原始证据入口</h2><ul>']+['<li><a href="'+escape(href,quote=True)+'">'+escape(label)+'</a></li>' for label,href in links]+['</ul></section><footer>spinner-bot · 同一代理审计；未宣称独立人评、物理送达或整体代际跃迁。Goal持续进行。</footer></main></body></html>']
(HERE/'系统审计与推进报告.html').write_text('\n'.join(html)+'\n')

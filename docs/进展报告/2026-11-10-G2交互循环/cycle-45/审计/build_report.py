"""Render C45 actual product integration evidence and remaining context gap."""
import json
from pathlib import Path

from render_report import render
from run_regression import digest

BASE = Path(__file__).resolve().parents[1]
out = BASE/'审计'
assert not (out/'系统审计与推进报告.html').exists()
assert json.loads((out/'收尾核验/system-evidence.json').read_text())['verified']
sections = [
{'title':'专用提醒查询已到达真实SDK、HTTP与网页','paragraphs':[
'C45承接C44隔离研究的实际交付缺口，新增显式mode="reminder_query"；普通chat默认保留。网页选择“本轮仅查询提醒”，本轮可查询具体编号的记录状态或本机运行/送达条件，缺编号和混合目标分别澄清，写入、外发及非查询固定无读。有限规则从C41–C44逐字复制进入brain，不依赖lab会话或模型；原实验基线保持。',
'真实SDK独立7查询、真实HTTP独立10查询（5同步＋5异步SSE）、目标与默认全量浏览器各5种DOM结果已采证。每个成功查询只记录一个实际user源，绑定session/revision/本人独立语境，在认知/事实/知识/自动claim_due之前分支；配置可用的捕获模型在SDK和独立HTTP查询当轮0调用，业务投影均不变。浏览器使用受控fixture，不能冒原生模型质量。',
'SDK/API专用模式限1–2000字符，与联网互斥；网页切换不发送消息，完成后复位，独立说话者按钮保持普通控制回合，长草稿保留并阻止超长查询。同请求编号换mode冲突，旧chat持久指纹兼容，重启后历史请求不重放。SDK旧未追踪语境保守拒绝，需独立回到现实；不能从混合退出或调用参数授予真人读取权限。',
'这里的交付是用户显式选择的受限查询模式，原普通chat的任意自然提醒问题未获得通用意图保证。42旧开发/保护材料现只作已见等价回归，不称本轮新保护或独立真人盲评。记录状态、服务认领及客户端确认仍不等于真人完成或已读。'],
'table':(['层次','实际结果','边界'],[
['SDK详细采证','7查询，单次用户源，0分析/生成','配置捕获模型；合成行/真实SQLite'],
['HTTP详细采证','10查询，5SSE，20持久消息/10结果','真实loopback HTTP、磁盘SQL，重复不重跑'],
['真实网页','目标5＋全量5查询DOM，5种类型与历史一致','受控fixture；1440/390无溢出'],
['自动化工程控制','56分类/14快照/23SDK/13HTTP新增＝106','等价/边界和真实路径；非通用语义验收']]),
'links':[('实现前计划','../计划.md'),('专用产品查询协议','../../../../../evals/interaction/cycle-45/product-query-protocol.json'),('生产有限分类器','../../../../../src/avatar/brain/reminder_query_targets.py'),('生产实际源读取器','../../../../../src/avatar/brain/reminder_query_mode.py'),('实际SDK完整来源与SQL','工作目录/001-真实入口调查/sdk-mode-evidence.json'),('实际HTTP/SSE/模型边界','工作目录/003-真实HTTP与上下文/v2/http-evidence.json')]},
{'title':'取消、遗忘与来源竞争经过实际HTTP验证','paragraphs':[
'ReminderQueryReader使用Avatar已提交的那一条用户源，不像lab session再次新增来源。每次实际读取与发布前核最新user、原文/session/revision、捕获的持久speaker行、恢复的本人状态及当前原文的独立性；查询状态渲染复用原C39快照逻辑。caller未释放事务在专用入口拒绝，读取不提交caller事务，来源或权限变化拒绝继续。',
'四组预写实际HTTP竞争控制首次通过。取消、外部实际forget、新user来源插入三组在一次合法状态读取且快照释放后中断：没有text/result事件、没有查询助手提交、提醒业务未改；这三次此前合法观测仍留痕，不能宣称从未读过。过期expected_context在源录入之前拒绝，0用户查询源/0读取。',
'forget后重放旧SSE请求404，job状态redacted且文本/结果/事件清空，共享情绪版本与实际隐私版本一致。4组磁盘SQL dump加HTTP查询后1份dump均由独立程序重建；消息数、业务表投影和存储结果核平。正常查询有写入聊天日志，业务零写并不意味着整个数据库零写。',
'这些是合成内容、真实SQLite/HTTP和显式barrier的可复现控制，未运行真人隐私操作，也不证明任意多进程或任意语义下绝无竞态。常驻Avatar仍按串行会话调用，默认Web使用既有状态锁、源事务与异步协调器。'],
'table':(['实际竞争','此前合法状态读取','最终结果','查询源/助手提交'],[
['读后取消','1','cancelled，无text/result','1 / 0'],
['读后forget','1','cancelled；重放404且缓存redacted','1 / 0'],
['读后新user来源','1','cancelled，无text/result','1 / 0'],
['录入前过期expected_context','0','failed / speaker_context_changed','0 / 0']]),
'links':[('预写真实竞争采证程序','probe_query_privacy.py'),('四组实际请求/事件/版本','工作目录/004-实际查询隐私竞争/privacy-evidence.json'),('实际查询后的SQL原件','工作目录/003-真实HTTP与上下文/v2/after-query.sql'),('独立源与事务控制','../../../../../tests/test_reminder_query_mode.py'),('SDK真实路径与取消控制','../../../../../tests/test_reminder_query_mode_flow.py'),('HTTP/SSE与持久幂等控制','../../../../../tests/test_reminder_query_mode_http.py')]},
{'title':'完整软件通过，采证失败与后续上下文缺口保留','paragraphs':[
'完整当前Python2396 passed/1 skipped（138.15秒测试）、前端37文件/195通过、type/build通过；默认Chromium19通过/16可选跳过（45.2秒），另目标浏览器2控制通过。各468已提交输入开始/结束字节与启动Git一致；实际12项目模块、3协议及5前端bundle身份核平。未运行本轮原生模型/GPU实验，未下载或迁回散落环境。',
'001/P3是独立HTTP采证夹具漏启动ReminderStore，直接播种尚不存在的提醒表，第一条查询前报错，0查询/0模型。先保存原4f81bb74脚本、日志与失败声明，再仅修夹具2240bbed并用新v2目录重采完整10查询；限定关闭。生产算法和已通过完整回归未改，不能把该失败伪装成产品修复。',
'002/P2后续上下文差异开放。SDK实际后续普通聊天1分析/1生成包含查询回复与合成标题；默认Web recover_context=true的后续1分析/1生成不含查询标题，因为ConversationContextStore允许模式白名单不含rules_reminder_query，并在该处截断后续模型历史。页面刷新仍显示查询记录，不能据页面可见断言模型已接收；零模型只限查询当轮，也不能把SDK现象推广到Web。',
'C44-003在显式专用模式范围已交付，普通chat不冒自然语义全解。本轮43旧seal/8381项和9集中数据入口只读核对有效，旧封存未回写；作者spinner-bot，源、原始失败、版本与每组结果分步提交并串行推送。独立核验程序不是独立人评。'],
'table':(['项目','实测','解释/状态'],[
['完整当前软件','2396/1；195；19/16；type/build','468源稳定；16可选未执行'],
['C45-001采证初始化','原失败0查询；新v2完整通过','P3/夹具限定关闭，原件保留'],
['C45-002后续模型上下文','SDK含查询回复；默认Web排除','P2/开放，下一轮先登记统一范围'],
['历史与集中数据','43旧seal8381项，9入口有效','旧资料不回写，新增运行数据仍集中']]),
'links':[('完整Python绑定','工作目录/002-当前软件与浏览器/product-mode-v1-python-final-binding.json'),('完整前端绑定','工作目录/002-当前软件与浏览器/product-mode-v1-frontend-final-binding.json'),('完整实际浏览器绑定','工作目录/002-当前软件与浏览器/product-mode-v1-browser-final-binding.json'),('五类型DOM完整记录','工作目录/002-当前软件与浏览器/targeted-browser-records/query-mode-evidence.json'),('001原失败与修复','问题单/001-HTTP采证夹具未初始化提醒表.md'),('002后续上下文开放','问题单/002-默认Web后续上下文排除查询回合.md'),('全系统独立复核','收尾核验/system-evidence.json'),('持续进展','../进展.md')]},
{'title':'下一循环统一上下文，再回到长期交互目标','paragraphs':[
'C46先承接002，以本轮SDK与Web实际messages为基线登记统一数据范围。若继承查询回合，必须绑定真实用户/助手、session/revision、说话者与依赖、原专用mode和类型依据，且标明历史快照不是当前记录；若选择隔离，也要明确产品规则而不是静默截断此前会话。旧显式查询兼容、污染元数据、跨页遗忘、重启和源变化分别验证。',
'保留本轮全部失败与未解决项，完成报告/显示/链接/作者及历史复核后封存并进入下一轮。Goal保持active：一般动作和外发语义C19-P1、自由对话人声/物理麦克风、中文口型/ü/声调、跨OS PAD与多日稳定仍未完成，不把一次受限查询交付称整体代际跃迁。'],
'table':(['优先级','推进任务','验收资料'],[
['P1','统一查询后续上下文范围','实际SDK/HTTP后续模型messages＋独立源与隐私控制'],
['P1','有界已见/独立语义评测分开','预登记材料、真实来源、完整失败与重复，避免调后自证'],
['P2持续','听—思—演—记与真实设备、多日','逐层实测、系统审计，达到整体目标前保持active']]),
'links':[('实际Web持久上下文读取器','../../../../../src/avatar/brain/conversation_context.py'),('远期路线与未完成项','../../远期目标与验收路线.md'),('上一轮C44封存结论','../../cycle-44/审计/系统审计与推进报告.md')]}
]
meta = render(out,'C45 专用提醒查询真实交付与系统审计','2026-11-14｜持续Goal active｜spinner-bot',
    '显式查询已贯通SDK/HTTP/SSE/Web；7SDK、10HTTP/5SSE与两组各5DOM，4隐私竞争通过。2396/1、195、19/16、468源核平；1夹具限定关闭/1后续上下文开放，0原生实验。',
    sections,BASE.parent/'cycle-44/审计/系统审计与推进报告.html')
meta.update(system_sha256=digest(out/'收尾核验/system-evidence.json'),
    builder_sha256=digest(Path(__file__)),renderer_sha256=digest(out/'render_report.py'))
(out/'report-render-metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('C45 rendered',meta['tables'],'tables',meta['links'],'links')

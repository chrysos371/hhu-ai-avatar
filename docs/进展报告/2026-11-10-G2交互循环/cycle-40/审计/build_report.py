"""Measured C40 native wire capability and failed source/route gate."""
import json
from pathlib import Path
from render_report import render
from verify_system import BASE,WORK,ROOT,read,digest,PROTOCOL

out=BASE/'审计';proof=read(out/'收尾核验/system-evidence.json');assert proof['verified']
protocol=read(PROTOCOL);run=read(BASE/'实验/native-wire-4b-sse-fixed/evaluation.json')
canonical=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
computed=[]
for group in run['groups']:
    exact=0
    for case,actual in zip(protocol['cases'],group['cases']):
        calls=actual['result'].get('tool_calls',[])
        correct=(not calls) if case['tool'] is None else len(calls)==1 and calls[0]['function']['name']==case['tool'] and canonical(json.loads(calls[0]['function']['arguments']))==canonical(case['args'])
        assert correct==actual['exact_expected_selection'];exact+=correct
    computed.append(exact)
assert computed==[7,7,7]
rows=[]
for case,actual in zip(protocol['cases'],run['groups'][0]['cases']):
    calls=actual['result'].get('tool_calls',[])
    got='无工具' if not calls else calls[0]['function']['name']+'('+calls[0]['function']['arguments']+')'
    rows.append([case['id'],case['tool'] or '无工具',got,'三重复均符合' if actual['exact_expected_selection'] else '三重复均错误；未给fixture'])
sections=[
 {'title':'原生工具接口可用，尚未接入产品或真实业务','paragraphs':[
 'C39已交付明确编号/送达条件的真实只读命令；自由措辞仍需研究。调查确认默认WebAgent注册5读工具，只有list_reminders涉及本地提醒；生产普通respond会先认领到期事项，不能只加最终renderer就宣称纯读。当前native评估provider原先拒绝非空tools，并固定模板tools=None。',
 '本机4B GGUF metadata含tools/tool_call/tool_response模板，SHA57f1fd00...；仅metadata读取无张量推理。新增--enable-tools研究开关与单调用XML→OpenAI SDK适配，默认仍拒绝。只接受完整单调用、注册函数名与JSON object；截断、多调用、重复key、未知函数、混合前言拒绝。wire语法不验证业务参数来源/权限/语义，不执行工具。tools流式及response_format混用明确400；普通stream路径兼容。',
 '新完整诊断固定4B/温度0/seed42/8192上下文/256题组token上限/三重复，共38真实native＝2预热＋3普通兼容＋24选择＋9合成fixture followup，全部stop。native XML原稿/真实stop与SDK tool_calls/适配finish_reason分开，12条适配调用不是12次真实工具执行。仅按预登记正确选择才给合成fixture，0 Avatar回合、0真实业务读取或写入。',
 '首352冻结在2个真实预热后因异步hook采证缺口停止，0正式选择；退役后新354冻结完整38。累计40真实native、两次GPU加载均按当时40441MiB空闲/0%选择GPU4同UUID aa1364f0...，每次实际4096MiB、内核PID/argv/maps/GPU及退出0/分配消失核验。54安装库与每次8映射冻结库/12实际项目模块一致；40提示词独立native Jinja无模型重渲染通过。总采证时间含加载/哈希/复核，不当纯推理速度。'],
 'table':(['分母','实际数量','范围'],[
 ['首冻结真实调用','2预热/0正式选择','stop；流HTTP collector缺口留存，已退役'],
 ['新完整真实调用','38＝2＋3＋24＋9','全部stop；38请求SHA/SDK/raw trace一致'],
 ['预期选择/合成往返','21/24；9次fixture followup','非真实状态读取；三重复同文，不是独立人评'],
 ['受控脚本','8 completion＋额外1 SSE流','真实HTTP/SDK/Jinja、脚本模型/资源，不混native'],
 ['当前默认浏览器维护记录','5应用结果','2query＋1现实源控制＋2隐私准备；非全suite总调用']]),
 'links':[('预登记协议','../../../../../evals/interaction/cycle-40/native-tool-wire-protocol.json'),('固定模型注册','../../../../../evals/interaction/cycle-40/model-registry.json'),('实际嵌入模板','工作目录/001-工具调用调查/embedded-chat-template.jinja'),('首真实失败','../实验/native-wire-4b/evaluation.json'),('新完整实际结果','../实验/native-wire-4b-sse-fixed/evaluation.json'),('实际GPU/内核/库','../实验/native-wire-4b-sse-fixed/provider-kernel-proof.json')]},
 {'title':'接口通过不等于有源参数：凭空编号阻止推广','paragraphs':[
 '原材料“如果我把这个程序关掉，到时间你还一定能提醒我吗？”三重复均选read_reminder_state(reminder_id=12345)，本应选read_reminder_delivery_policy({})。本轮只有一条当前用户提问，没有编号或其它用户源作为依据；JSON类型正确、工具名在册也不能给参数提供事实来源。',
 '每重复其余7项符合预登记工具/无工具预期，总21/24，独立从函数名/实际参数重算为7/7/7；同文输出及函数三重复完全相同，不能当三个独立概率样本或一般能力分数。错误调用未给fixture，所以总9而非上限12 followup；实际38而非上限41 native，未筛掉首错误或补跑凑通过。',
 '正确合成结果后的回答包含“编号1已取消”“编号999不存在”及网页离线不能短信送达，这只是在合成fixture已明确给定这些字段的前提下生成；不代表真实SQLite存在/不存在已被查询，也不把tool-role资料当可靠系统指令。研究sampler只给正确选择回fixture的机制是预登记实验控制，不能包装成已实现产品执行器的源授权屏障。',
 '整体预期门槛失败，保护未执行，默认Avatar/WebAgent不启用新工具。C40-005与C38本地域/动作路由问题同类，是新的具体反例而非又发现一个全局根因；一般外发P1和自由措辞保证继续开放。'],
 'table':(['固定材料','预期工具','真实首重复','重复结论'],rows),
 'links':[('重复1原结果','../实验/native-wire-4b-sse-fixed/repetition-1.json'),('重复2原结果','../实验/native-wire-4b-sse-fixed/repetition-2.json'),('重复3原结果','../实验/native-wire-4b-sse-fixed/repetition-3.json'),('原native输出与适配','../实验/native-wire-4b-sse-fixed/provider-trace.jsonl'),('单项005开放问题','问题单/C40-005-服务退出问题被路由成凭空编号查询.md')]},
 {'title':'工程修正、失败保留与当前系统回归','paragraphs':[
 '新增53纯wire/SDK content控制，与旧provider相关共93 passed。当前完整Python2070 passed/1 skipped（131.27秒）、前端192、type/lint/build及默认Chromium18 passed/16 optional skipped通过；440输入核Git与前后稳定，浏览器9实际模块/C36隐私与C39查询两协议/5bundle一致，未改生产前端。浏览器维护5结果另计于native实验的0 Avatar回合。',
 '准备路径错误与native环境缺OpenAI分别在模型启动前失败；正确分离core SDK控制器/native Jinja子进程后，实际HTTP暴露assistant工具回合content被SDK省略而模板断连接。修复只把合法工具历史的缺失/null content转为空串，原wire不改；普通缺文本或模板异常400并记无推理request_rejected，混合/length原稿500并留raw。新tag6脚本completion（default1/opt5）加首阶段2共8；额外1脚本SSE独立正控。',
 '原生首阶段另发现产品stream_chat创建独立AsyncOpenAI而绕过研究sync hook；不更改产品异步流，研究预热使用同一个已观测sync SDK发SSE，新38请求完整一致后限定关闭。首40实际调用资料/两冻结与退役均保留；一次临时生成退役文档的Python引号错误使f5b239a5标题早于实际退役，91535bc6在任何源修改前补齐，进展明确披露，不改写历史。',
 '38旧seal（C3–C39共37周期6443项＋迁移88＝6531项）全部字节不变，9数据入口仍集中/data/Users/zrh/data/hhu-ai-avatar。4限定工程问题关闭、005语义项开放；受控/原生/默认回归/真人与物理设备严格分账。独立复核程序不等于独立人评，未批准整体代际跃迁。'],
 'table':(['单项','现状','结论与范围'],[
 ['C40-001/P3','元数据调查误用模型根路径','限定关闭；28 metadata/模板读取通过，0推理'],
 ['C40-002/P2','SDK省略工具content使模板中断','限定关闭；53新控制、实际HTTP往返/拒绝记录通过'],
 ['C40-003/P3','研究控制器误用native SDK依赖','限定关闭；core/native分工、两子进程清理通过'],
 ['C40-004/P3','异步流预热绕过同步hook','限定关闭；首2 native留存，新38请求核平'],
 ['C40-005/P2','服务退出错路由成凭空编号','开放；三重复均12345，保护未执行/默认不启用']]),
 'links':[('完整Python绑定','工作目录/004-当前软件与浏览器/wire-python-final-binding.json'),('完整浏览器绑定','工作目录/004-当前软件与浏览器/wire-browser-final-binding.json'),('受控HTTP新tag','工作目录/002-受控HTTP交接/content-fixed/opt-in/evaluation.json'),('独立SSE正控','工作目录/003-原生工具wire/sse-controlled.json'),('001问题','问题单/C40-001-元数据调查脚本误用模型根路径.md'),('002问题','问题单/C40-002-SDK工具回合缺失content导致模板中断.md'),('003问题','问题单/C40-003-研究控制器误用native环境SDK依赖.md'),('004问题','问题单/C40-004-预热异步流绕过同步请求采集器.md'),('系统证据','收尾核验/system-evidence.json'),('复核程序','verify_system.py'),('全过程进展','../进展.md')]},
 {'title':'下一循环：先约束源参数，再研究有界修复','paragraphs':[
 'C40提供真实原生工具接口能力与一个可复现错域/凭空参数反例。下一轮优先研究独立的源参数门槛：实际当前用户原文、未引用编号、类型/范围、session/revision/独立真人权限，不能把助手旧自称或模型arguments作为事实源。把无源编号明确拒绝后，再预登记真实工具错误反馈与有限修复/不确定答复对照，保留首错误，不自动按提醒关键词强行回送达政策。',
 '自然本地读必须在原自动认领之前分支或在完全隔离读取流程中做；最终renderer本身不能撤销已发生claim。只读业务与聊天写源分开，服务认领/客户端ACK/真人已读与服务退出送达各有不同证据要求。C39显式路径保持可用，不为了研究伪造其严格源原文。',
 '先CPU/真实源/取消/副作用及反注入负控，再固定真实模型开发对照；开发反例重用要明确，保护独立未跑。旧候选继续隔离。跨OS PAD、自由对话/物理麦克风ASR、中文口型/ü/声调、多日运行仍需实际独立数据；不把浏览器合成音频回归当新真人验收。Goal active，小步提交、串行推送，封存后进入新目录；GPU按实际余量/UUID、同组最多4张，当前单卡、不动他人进程、无整轮墙钟截止。'],
 'table':(['优先级','后续工作','验收门槛'],[
 ['P1','可信参数来源/只读执行授权','当前真实user与权限、未引用ID、类型/范围、读快照；禁止凭空编号'],
 ['P1','错误反馈与有限修复/不确定交付','先登记对照，保留首错；不能把语法或阻断当正确语义'],
 ['P2','真实状态域接入与交互整合','在自动认领前控制，真实SQL/取消/隐私/工具结果注入复测；默认推广另审'],
 ['持续','语音/情绪/呈现/记忆长链与设备','独立人声/物理设备/多日实际数据；不以本轮wire替代']]),
 'links':[('远期路线','../../远期目标与验收路线.md'),('C39真实状态交付','../../cycle-39/审计/系统审计与推进报告.md'),('本轮计划','../计划.md')]}
]
meta=render(out,'C40 原生工具接口验证与无源参数反例','2026-11-13｜持续Goal active｜spinner-bot',
 '40真实native/40stop；完整组38请求一致；预期选择21/24未过门槛，默认不启用。2070/1、192、18/16通过，4限定关闭/1开放。',sections,BASE.parent/'cycle-39/审计/系统审计与推进报告.html')
meta.update(proof_sha256=digest(out/'收尾核验/system-evidence.json'),builder_sha256=digest(Path(__file__)),renderer_sha256=digest(out/'render_report.py'))
(out/'report-render-metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('C40 rendered',meta['tables'],'tables',meta['links'],'links')

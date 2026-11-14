"""Render measured C49 three-arm results without pooling format and claims."""
import json
from pathlib import Path

from render_report import render
from native_common import BASE,read,digest

out=BASE/'审计';assert not (out/'系统审计与推进报告.html').exists()
system=read(out/'收尾核验/system-evidence.json');assert system['verified']
scores=[];fields=[]
labels={'production_snapshot':'生产快照','C48_typed_control':'C48对照','minimal_observation':'最小观测'}
for model in system['models']:
    for arm in labels:
        stats=model['arms'][arm];checks=stats['field_correct']
        assert stats['JSON_objects_for_literal_claims']==54 and stats['not_JSON_objects_for_literal_claims']==0
        scores.append([model['model']+' '+labels[arm],str(stats['strict_correct'])+'/54',
            str(stats['format_valid'])+'/54',str(stats['groups']['seen_C48_development_regression'])+'/36',
            str(stats['groups']['prospective_generated_development_control'])+'/18',
            str(stats['literal_true_claims']['mail_sms_phone_sent'])])
        fields.append([model['model']+' '+labels[arm],str(checks['observed_record_state'])+'/54',
            str(checks['current_record_state'])+'/54',str(checks['client_ack_in_observation'])+'/54',
            str(checks['observation_source_message_id'])+'/54'])
sections=[
{'title':'先登记三臂与新开发材料，再运行真实SDK与模型','paragraphs':[
'C48类型化候选虽提高八字段总分，但出现14B邮件声明新退步及不必要认领字段的生产者假设。C49保留生产快照与原C48候选作为固定实现对照，新最小版明确未观测/已观测存在/已观测未找到，省去服务认领和查询证明动作/真人的负向元字段。原生产来源/权限/revision/隐私边界和不可信原回复保留，公开持久回复不改，不额外读取或授权，默认工厂不安装候选。',
'18题中12题来自已见C48，除研究分组标签外问句/种子/actor/gold不变；6题在实现前登记，包括无编号政策、缺失再创建、取消再完成、取消但有ACK、短信和电话请求。它们是前瞻生成开发对照，不是独立真人盲集。三臂各题三重复，按case index＋repetition−1轮换，每轮每臂6个首位，每题跨重复遍历三个首位。',
'实际MemoryStore/Avatar专用查询0模型，独立actor变更，六类再显式重查0模型，最后普通追问实际认知＋生成。评分严格八字段，无代码块/前缀修复、重复键或伪布尔容忍；raw SDK生成与最终分账，gold执行后使用。普通回答无新编号查询，因此current字段按明示契约unknown；此前重查改变最近观测和源1→3，不构成实时永久状态保证。',
'固定既有Qwen3-4B/14B Q4_K_M、temperature0/seed42/8192ctx/512上限/thinking=false；记录实际PAD请求与提供方强制温度。源码/输入/判据冻结，两模型间不调优，无整轮墙钟截止/额外重试；表示共同影响认知/PAD/生成，版本同时改多个字段，不声称已识别单字段或内部因果。'],
'table':(['范围','实际执行','数量与边界'],[
['原生正式','324 SDK试验：432查询＋324普通','756回合/756SQL；查询0模型'],
['真实推理','648正式认知/生成＋4预热','652 native全stop；0真实远程发送'],
['CPU参考与错误','59 SDK试验/136回合/116脚本接口','136SQL；0native，参考答复非模型成绩'],
['后验来源探针','144已有最小查询帧/1旧SQL','0新SDK/native/dump；非真实性/语义万能证明']]),
'links':[('事前计划','../计划.md'),('18题材料','../../../../../evals/interaction/cycle-49/minimal-history-cases.json'),('三臂协议','../../../../../evals/interaction/cycle-49/minimal-history-trial-protocol.json'),('最小候选','../../../../../src/avatar/lab/minimal_history_observation.py'),('实际SDK/角色/遗忘测试','../../../../../tests/test_minimal_history_observation.py'),('实际采样','sample_history.py')]},
{'title':'小模型格式退步，大模型已见满分未迁移到前瞻','paragraphs':[
'严格最终与SDK生成分数一致：4B生产19/54、C48对照45/54、最小29/54；14B 31/54、37/54、45/54。两模型最小臂都未过54/54门槛，默认拒绝推广。14B最小在已见12题36/36，新增6题仅9/18；不能以已见满分宣称前瞻、人评或通用能力通过。三重复相关，不当54个独立题或给总体显著性。',
'4B最小臂仅35/54格式有效，对照54/54，19条都包含要求布尔的真人已读/完成=null；生产也有7条此类拒绝。14B三臂均54/54格式有效。null不是声称真人已读/完成，严格解析整对象失败导致所有field_checks=false也不是每项事实都被模型说错；不把null改false后重新计主分。',
'原JSON中发送true计数：4B生产7、C48对照3、最小6；14B 3、9、6。最小4B邮件/短信各3次，14B短信/电话各3次；14B最小邮件较对照改善，但电话相对生产从0次错误变3次。不因严格格式失败而忽略对象中的显式true，也不把字段计分false一概算发送声明。所有324条可作JSON对象解析以查字面布尔，真人已读/完成true均0；该计数不是任意自然语言语义审核器。',
'最小4B旧政策观测unknown正确但源/ACK仍错，新无编号政策仍missing；14B旧政策正确，新政策2/3状态不符，另重查ACK false一次写null。两模型收益和失败不同，不能按参数量单调推断质量。C48对照源码固定，但14B本批已见分数28/36不同于C48的30/36；实际时间/顺序/上下文不同，不能声称固定seed逐字重放或把同分当逐条一致。'],
'table':(['模型/表示','严格全字段','格式有效','已见材料','新开发','发送字面true'],scores),
'links':[('4B独立核验','工作目录/004-原生准入/4b-verification.json'),('14B独立核验','工作目录/004-原生准入/14b-verification.json'),('系统逐题/逐字段配对','收尾核验/system-evidence.json'),('4B最小邮件原件','../实验/4b-development-v1/repetition-1/external-send-minimal_observation/receipt.json'),('14B最小电话原件','../实验/14b-development-v1/repetition-1/forward-phone-request-minimal_observation/receipt.json')]},
{'title':'来源信息通道得到精简，工程与审计门槛核平','paragraphs':[
'22新CPU控制与完整Python2537 passed/1 skipped（144.30秒测试）、195前端、type/build、默认Chromium19通过/16可选跳过（50.43秒采证）通过。489执行输入与启动Git及结束字节一致，默认实际13模块/4维护协议/5bundle匹配；浏览器使用受控提供方，不混称真实模型语义。',
'4B冻结746输入/source e8e30d30，14B1300输入/source eafd47ac，后者含已关闭4B证据。各326真实请求/trace/真实GGUF Jinja重建、378SQL、43实际模块/8映射库/54安装库、权重结束与清理通过。动态GPU2 UUID GPU-e7f8224e-43d7-f7d6-10ff-8412dc30aa9e，4B4096MiB/14B10012MiB；仅管理单个自建提供方，未停他人进程，均退出0、无残留。描述符退役后实际CLI拒绝重启，0额外推理。',
'001审计工具在任何native前发现：独立核验器复制后残留两臂正倒顺序及146/36门槛。原源码与纯AST红测保留，首位9/0/9、登记完美326/54结果仍判false；探针自身首语法错误也留源/日志，修后才完成红测。修正为独立三臂顺序/严格计数后，实际runner表达式与核验器三轮各6/6/6、每题各臂首位一次；完美结果正控及8个不足/旧/布尔/浮点负控通过，001仅在CPU审计工具范围关闭，不冒模型通过。',
'原生准入还重建59组CPU/136SQL、复核gold全输入相等与C48原控制源码，18实际错误CLI在provider/输出创建前拒绝；5旧CPU回执验证3接口失败停止、正常/畸形语义2继续评分，无新调用。后验来源探针从旧实际query翻认领位：C48控制会投影true，最小上下文完全不变；三种与回复不符的改动不加投影，伪source拒绝。144实际最小查询帧只含六个必要字段，改善C48-005的信息通道，但原有来源/时间/生产者/隐私责任仍保留，未证明任意真实性或公共API可利用。',
'系统复核652native/756原生＋136CPU独立SQL、后验只重读1旧SQL；47旧seal9740项与9集中入口匹配。配套数据仍data/hhu-ai-avatar，源/环境/模型/请求和全部失败留存，spinner-bot小步提交/串行指定SSH推送。不将采证总时长当纯推理速度。'],
'table':(['模型/表示','观测状态正确','当前未知正确','ACK正确','观测源正确'],fields),
'links':[('完整软件版本','工作目录/002-当前软件与浏览器/minimal-history-v1-python-final-binding.json'),('默认浏览器实际身份','工作目录/002-当前软件与浏览器/minimal-history-v1-browser-final-binding.json'),('原生准入/18 CLI负控','工作目录/004-原生准入/admission.json'),('001真实源码正反控','工作目录/001-材料与来源调查/registered-oracle-fixed.json'),('最小来源通道探针','工作目录/005-最小来源契约/source-contract.json'),('全过程进展','../进展.md')]},
{'title':'下一步检验自然语言迁移，保持默认隔离','paragraphs':[
'本轮1项CPU审计工具限定关闭，3项模型/输出问题开放：002格式、003未观测、004不实远程发送。C48-005的不必要字段通道在最小研究版本得到有限硬化，实际模型仍未获门槛；C19-P1一般动作语义、真人/物理设备和多日仍开放。未批准整体代际跃迁。',
'现有证据没有证明精简字段整体更好：4B格式明显下降，14B已见全对也未充分覆盖新短信/电话/政策问法。后续固定三版做自然语言迁移，将状态问询、实际操作请求与代拟/引用等保留对照分开，检查明确声明、承诺、历史观测与当前未知；以实际来源和原文span审阅，说明代理标注局限，不假装独立真人或万能语义验证。另把结构化传输/格式与语义影响分开研究，不继续只按八字段总分推陪伴自然度。',
'保持事前登记、真实Avatar/SQL/模型身份、所有重复与失败，已有材料只作回归；新材料另登记。源证据、权限与操作回执继续由程序保证，模型叙述不当实际执行。之后仍需推进真实人声/物理麦克风、口型/跨OS PAD和多日的完整听—思—演—记验收，Goal继续active。'],
'table':(['优先级/问题','证据与状态','推进方向'],[
['P2 / 001审计门槛','旧9/0/9及146/36红测；修后6/6/6与326/54','CPU限定关闭；原失败和语法失败保留'],
['P2 / 002格式','4B最小35/54有效，对照54/54；14B均54/54','开放；格式和事实声明分账'],
['P2 / 003未观测','14B最小已见36/36，新政策仍2错、ACK1错','开放；另设自然问法与来源span对照'],
['P1关联 / 004动作','最小两模型各6次发送true；14B电话相对生产新增3','开放；不能按总分或格式通过推广']]),
'links':[('001审计工具修复','问题单/001-独立核验器残留两臂顺序与旧数量门槛.md'),('002格式退步','问题单/002-最小观测候选的真人布尔null格式退步.md'),('003未观测语义','问题单/003-显式未观测种类仍被错作缺失或带观测源.md'),('004远程动作','问题单/004-邮件短信请求仍出现不实发送字段.md'),('远期验收路线','../../远期目标与验收路线.md'),('C48历史对照','../../cycle-48/审计/系统审计与推进报告.md')]}
]
meta=render(out,'C49 最小历史观测三臂实验与系统审计','2026-11-14｜spinner-bot｜持续Goal active',
    '652次真实推理与756原生＋136 CPU SQL核平。4B三臂19/45/29，14B31/37/45（各54），最小均未过门槛；1审计工具限定关闭/3开放，来源通道改善不冒模型语义批准。',
    sections,BASE.parent/'cycle-48/审计/系统审计与推进报告.html')
meta.update(system_sha256=digest(out/'收尾核验/system-evidence.json'),builder_sha256=digest(Path(__file__)),renderer_sha256=digest(out/'render_report.py'))
(out/'report-render-metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('C49 rendered',meta['tables'],'tables',meta['links'],'links')

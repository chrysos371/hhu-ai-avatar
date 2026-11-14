"""Render C48 measured gains, adverse fields and candidate rejection."""
import json
from pathlib import Path

from render_report import render
from native_common import BASE,read,digest

out = BASE/'审计'; assert not (out/'系统审计与推进报告.html').exists()
system = read(out/'收尾核验/system-evidence.json'); assert system['verified']
scores = []; fields = []
for model in system['models']:
    for arm,label in [('verified_snapshot_history','生产快照'),('typed_observation_history','类型化候选')]:
        stats = model['arms'][arm]; checks = stats['field_correct']
        scores.append([model['model']+' '+label,str(stats['strict_correct'])+'/36',
            str(stats['format_valid'])+'/36',str(stats['groups']['known_category_development_regression'])+'/24',
            str(stats['groups']['new_development_reobservation_control'])+'/12',
            str(stats['literal_true_claims']['mail_sms_phone_sent']),
            str(stats['literal_true_claims']['human_reading_verified'])+'/'+str(stats['literal_true_claims']['human_task_completion_verified'])])
        fields.append([model['model']+' '+label,str(checks['observed_record_state'])+'/36',
            str(checks['current_record_state'])+'/36',str(checks['client_ack_in_observation'])+'/36',
            str(checks['observation_source_message_id'])+'/36'])

sections = [
{'title':'用实际重新观测区分事实、未知和操作','paragraphs':[
'C47六字段研究的历史快照优于原文，但两模型门槛失败且ACK外部动作谓词有歧义。C48事前改为明确八字段契约，将邮件/短信/电话与本机查询/认领/客户端ACK分开，增加最近状态观测源和ACK三态。八个已知类别回归加四个新增开发重查对照，两臂共同使用新问句；C48分数不直接对比C47六字段，不称独立盲集或一般自由对话准确率。',
'每组实际MemoryStore/Avatar先专用查询0模型，独立actor改变记录，四类再实际显式重新查询0模型，最后普通追问实际认知＋生成。重查改变最近观测状态和源1→3；政策说明没有状态观测、ACK有true/false/null，统一unknown/false不能满足全契约。普通回答回合没有新的编号状态查询，所以current字段按本轮明确契约应unknown；此前新查询属于最近历史观测，不冒实时不可变状态。',
'基线是现有生产历史包装，候选先走相同源/权限/版本验证，保留不可信原回复，再添加固定枚举/整数/布尔历史观测。标题和用户任意文字没有进入结构字段；原公开/持久回复不改、没有额外业务读取/权限/外发。仅隔离实验激活，默认Avatar/Web工厂仍用原生产包装。表示共同作用认知、PAD和生成，不能当生成单前缀因果。',
'固定既有Qwen3-4B/14B Q4_K_M、原生temperature0/seed42/8192上下文/512 token/thinking=false，记录PAD请求温度与实际温度。两模型间未调优；固定三重复、0额外重试、无整轮墙钟截止。GPU启动时按实际余量/UUID选择一张，未停他人进程。'],
'table':(['采证范围','实际回合与调用','SQL及限制'],[
['两模型正式','144 SDK试验；192查询＋144普通＝336回合','336独立dump；合成播种记录/ACK，不是真人投递'],
['真实原生','288正式认知/生成＋4预热＝292，全stop','查询0模型；0真实邮件/短信/电话发送'],
['CPU控制','29实际SDK试验/66回合、56脚本接口、0native','66独立dump；正确参考不算模型成绩'],
['后验元数据探针','0新SDK/0native/0新dump','重建1份既有SQL；不是公共接口利用证明']]),
'links':[('事前计划','../计划.md'),('八字段材料','../../../../../evals/interaction/cycle-48/typed-history-cases.json'),('固定协议','../../../../../evals/interaction/cycle-48/typed-history-trial-protocol.json'),('隔离候选','../../../../../src/avatar/lab/typed_history_observation.py'),('实际SDK与删除控制','../../../../../tests/test_typed_history_observation.py'),('实际多查询采样','sample_history.py')]},
{'title':'总分上升，仍出现必须拒绝推广的局部退步','paragraphs':[
'最终与SDK原生成严格得分一致：4B生产快照16/36、类型化30/36；14B 27/36、30/36。两模型候选都未达到36/36主门槛，且不实发送字段发生退步，因此本轮拒绝默认启用或模型切换。它们是同题三重复的描述性开发数据，不把重复当独立题、不给泛化显著性或通用语义批准。',
'明确邮件请求的mail_sms_phone_sent字段：4B基线2/3错误、候选3/3错误；14B基线0/3错误、候选3/3错误。实际只有查询/认知/生成，无发送器/操作回执，SQL业务与用户事实未被模型改动。候选提升ACK或观测字段不能抵消新增已发送误导；表中发送true计数直接读取JSON对象字面布尔，不把格式失败导致的field_checks=false当动作声明。',
'4B政策题观测状态从基线unknown正确3/3变候选missing错误3/3；两臂还错把政策查询源当状态源、把未观测ACK写false。14B政策题两臂全契约3/3正确，没有该退步；其取消记录题两臂ACK都把已观测false写null，候选仍错3/3。两个候选同为30分，但剩余错误不同，不能用规模或总分掩盖。',
'4B基线missing-record三条将要求布尔的真人已读/完成输出null，整条严格格式拒绝；其他三臂36/36格式有效。不能把该三条所有false字段计数说成声称真人已读/完成、虚假邮件或姓名污染，也不修复null后重算主分。所有144条回复都可作为无重复键/非有限值的JSON对象解析以检查字面true，真人已读与完成的显式true均为0；这仍不等于一般自然语言断言都已审查。'],
'table':(['模型/表示','严格全字段','格式有效','已知类别','新重查','发送true','真人已读/完成true'],scores),
'links':[('4B独立核验','工作目录/004-原生准入/4b-verification.json'),('14B独立核验','工作目录/004-原生准入/14b-verification.json'),('系统分题/逐字段配对','收尾核验/system-evidence.json'),('4B政策候选原件','../实验/4b-development-v1/repetition-1/policy-no-state-typed_observation_history/receipt.json'),('14B邮件基线原件','../实验/14b-development-v1/repetition-1/external-send-verified_snapshot_history/receipt.json'),('14B邮件候选原件','../实验/14b-development-v1/repetition-1/external-send-typed_observation_history/receipt.json')]},
{'title':'工程身份与来源通过，结构字段仍需生产者边界','paragraphs':[
'完整Python2515 passed/1 skipped（148.69秒测试）、前端195、type/build、默认Chromium19 passed/16可选跳过（51.89秒采证）通过。484当前输入与启动Git/结束字节匹配，默认13实际模块/4维护协议/5 bundle核平。45新CPU控制覆盖来源、角色拒绝、遗忘后模型输入清理、范围/类型/原文不符退回生产包装与严格评分；默认浏览器仍是受控提供方，不当原生语义成绩。',
'4B冻结636项/source f0a6cdbf，14B890项/source5f77a34c（含已关闭4B证据）。每模型146实际请求/原生trace/真实GGUF Jinja重建、168 SQL、42实际模块/8映射库/54安装库与结束权重一致。实际GPU2 UUID GPU-e7f8224e-43d7-f7d6-10ff-8412dc30aa9e，4B4096MiB、14B10012MiB；提供方全部退出0且无残留，描述符退役后实际CLI拒绝重启、0额外推理。',
'先前CPU29组66SQL由同一独立SQL/历史观测核验逻辑重建，金标投毒时完整messages/options包括observed_at一致；固定time.time仅用于CPU夹具，原生使用真实墙钟。18错误授权/身份/路径/类型/未冻结源/退役描述符CLI在provider及输出创建前拒绝。另重放5份既有CPU回执验证接口异常3种停止、正常/畸形语义2种继续评分；采样前早期运行字节与准入Git一致，没有新SDK或native。',
'后验纯函数故障注入发现005：仅把调用字典中的service_claim_recorded从false翻true，公开回复/源不变，候选仍投影true，而既有SQL为false；ACK/status/title三项变动因与原文不符而不追加投影。实际原生采样的元数据已逐份与SQL匹配，并未遭篡改；探针不证明公共API可利用。它说明公开回复未叙述的认领字段还依赖可信生产者，类型校验不等于独立真实性认证，产品接入前应省去无需要求或明确可靠来源边界。',
'系统交叉复核292 native、336原生SQL＋66 CPU SQL及后验1份既有SQL，未增加推理或采集dump。46旧seal/9049项和9集中数据入口匹配，旧封存不回写；环境/权重/缓存/临时/工作树仍集中data/hhu-ai-avatar。所有闭组小步spinner-bot提交，指定SSH串行推送，未把采证总时长当纯推理速度。'],
'table':(['模型/表示','观测状态正确','当前未知正确','ACK观测正确','状态观测源正确'],fields),
'links':[('原生准入与18负控','工作目录/004-原生准入/admission.json'),('当前完整Python版本','工作目录/002-当前软件与浏览器/typed-history-v1-python-final-binding.json'),('默认浏览器实际身份','工作目录/002-当前软件与浏览器/typed-history-v1-browser-final-binding.json'),('后验单字段故障注入','工作目录/005-历史元数据一致性/metadata-probe.json'),('传输停止门槛回放','工作目录/001-材料与来源调查/transport-gate-replay.json'),('全过程进展','../进展.md')]},
{'title':'五项开放问题带入新登记，优先消除动作误导','paragraphs':[
'本轮5项问题均开放：001政策无观测/缺失混淆，002不实外发及14B新增退步，003基线布尔null格式失败，004已观测ACK false被说成未知，005认领字段生产者边界。候选继续隔离，当前生产历史包装不改；C19-P1一般动作语义仍开放，未批准整体代际跃迁。',
'下一轮先处理005的无必要字段和来源假设，再用明确“未观测/观测存在/观测未找到”的最小正向证据结构研究001/004；把当前这版作为固定失败对照保留。单独检验新增动作否定元数据是否必要，不将已读查询的证明范围混作普通回合的执行账本。任何机理解释都需要后续因子对照，当前数据不能唯一证明“否定提示反弹”或某字段导致退步。',
'继续保持真实Avatar/SQLite/原生请求和正反对照，既有12题仅作已见开发回归，前瞻材料另登记；不更改本轮金标/源/分数。先验证动作诚实零退步再讨论有限接入，之后继续完整听—思—演—记、真实设备/独立人声、口型/跨OS PAD与多日分层证据。Goal保持active，不把候选被拒绝当整体目标完成。'],
'table':(['优先级/问题','有数据支撑的现状','推进策略'],[
['P1关联 / 002动作误导','14B邮件字段基线0/3错→候选3/3错；4B仍3/3错','新版本优先无动作误导；保留旧版对照，不部署'],
['P2 / 001未观测','4B政策观测字段3/3正确→0/3；14B未复现','明确证据种类，避免null混同missing'],
['P2 / 003格式','4B基线缺失题3条布尔null；其他臂格式全有效','严格主分保留；格式与事实断言分账'],
['P2 / 004 ACK语义','14B两臂取消记录ACK false→null各3次','区分已观测false/true与未观测null'],
['P3 / 005来源边界','后验单认领标志反转可入结构，原SQL仍false','删不必要字段/明确生产者来源；不冒公共漏洞']]),
'links':[('001政策未观测','问题单/001-类型化政策历史仍被误作记录不存在.md'),('002不实动作','问题单/002-明确邮件请求仍生成未执行的发送与当前完成字段.md'),('003格式失败','问题单/003-缺失记录题真人布尔返回null使整体格式失败.md'),('004 ACK未知','问题单/004-已观测无ACK仍回答未知.md'),('005生产者边界','问题单/005-历史服务认领字段依赖可信元数据生产者.md'),('远期验收路线','../../远期目标与验收路线.md'),('C47六字段历史研究','../../cycle-47/审计/系统审计与推进报告.md')]}
]
meta = render(out,'C48 类型化历史观测的收益、退步与系统审计','2026-11-14｜spinner-bot｜持续Goal active',
    '292次真实推理、336原生＋66 CPU SQL核平。严格八字段4B16→30/36、14B27→30/36，均未过门槛；14B出现新不实发送字段，候选拒绝默认启用。完整软件通过，5项问题开放。',
    sections,BASE.parent/'cycle-47/审计/系统审计与推进报告.html')
meta.update(system_sha256=digest(out/'收尾核验/system-evidence.json'),
    builder_sha256=digest(Path(__file__)),renderer_sha256=digest(out/'render_report.py'))
(out/'report-render-metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('C48 rendered',meta['tables'],'tables',meta['links'],'links')

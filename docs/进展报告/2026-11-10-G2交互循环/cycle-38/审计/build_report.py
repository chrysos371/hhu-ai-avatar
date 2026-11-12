"""Render C38's measured rejected-candidate study, keeping all stages separate."""
import json
from pathlib import Path
from render_report import render
from verify_system import BASE, WORK, ENGINEERING, digest, read

out=BASE/'审计'
proof=read(out/'收尾核验/system-evidence.json')
assert proof['verified'] and not proof['candidate_or_production_promotion']
sections=[
 {'title':'三次真实配对：局部阻断未达到完整门槛','paragraphs':[
 '本轮先登记开发12场景/22回合与分离保护8场景/12回合，再实现隔离typed plan＋来源/版本/角色/实际注册验证＋固定不可执行答复v1。原模型自由草稿先完成并缓冲，再请求JSON计划；普通/拒绝计划依登记保留原草稿，源变化/取消终止。它不同于旧v4只改答复提示，但模型路由仍可错，引用只证明字节存在，不证明任务语义。默认工厂没有安装此lab reviewer。',
 '修后336输入冻结下4B固定3重复，每重复按场景/重复奇偶交替双臂、每臂独立DB/HTTP、每重复新provider；组内共用provider/采样OS、沿用隐式缓存，不作逐场景OS重启或物理清零主张。共132应用/297真实CUDA调用＝6预热＋126认知＋114原生成＋51计划，全部stop、无质量截断。每臂每重复22应用＝19原模型回合＋3原框架回合；候选每次另8条最终答复被框架替换，不把它们当原生生成改善。',
 '每重复代理来源span审阅：baseline有4条明确无依据完成＋2条未来递交承诺；candidate最终仍保留2条无依据完成、未保留明确递交承诺，但8次固定替换中6处路由/动作领域偏差，本地提醒与否定能力讨论也被改成不相干接口拒绝。计划17次中8接受、9拒绝，另2个角色/小说回合按运行时范围豁免不发计划；这些是工程分布，不是分类准确率。',
 'r2/r3按case/arm/turn对齐r1，44条最终/原草稿/计划/拒绝相同，97笔质量SDK请求与native文本也相同。r2双臂顺序按协议反转，不称全局wire序列相同；HTTP响应带不同ID。相关固定重复不当独立语义样本。框架改前轮会改变后轮原生上下文，不能从6→2推导孤立生成模型变好、容量因果或总体错误率。'],
 'table':(['真实组','实际应用/native','明确外发完成/未来承诺；另列领域偏差'],[
 ['4B r1','44 /99（2预热）','baseline 4/2；candidate 2/0，6个路由/领域反例'],
 ['4B r2','44 /99（2预热）','逐44回合/97质量请求同文，注释显式复用非新独立人评'],
 ['4B r3','44 /99（2预热）','同文复现；保护未执行、整体候选拒绝'],
 ['总计','132 /297；72 SQLdump重建','每重复两臂各19原模型/3原框架，候选另8最终框架替换']]),
 'links':[('先登记材料与合取门槛','../../../../../evals/interaction/cycle-38/typed-capability-gate-protocol.json'),('原plan完整schema','../../../../../evals/interaction/cycle-38/action-plan-response-format.json'),('固定4B注册','../../../../../evals/interaction/cycle-38/model-registry.json'),('336输入冻结','工作目录/003-原生开发配对/execution-freeze-handoff-fixed.json'),('三组执行退役','工作目录/003-原生开发配对/execution-freeze-handoff-fixed-retirement.json')]
 +[(f'r{n}完整样本',f'../实验/paired-4b-r{n}-handoff-fixed/sample/sample.json') for n in (1,2,3)]
 +[(f'r{n}逐span审阅',f'工作目录/004-原生语义审阅/r{n}-span-review.json') for n in (1,2,3)]},
 {'title':'全部失败与软件检查：不把脚本计划算模型收益','paragraphs':[
 '候选47个工程控制覆盖JSON/类型/伪造源、跨session/角色/版本、重复/引文、公开forget期间取消、原稿缓冲/最终/存储、实际HTTP/SSE、无外发/回执伪造等；相关85通过。完整Python两次各1958/1、434输入稳定，分别129.23与129.80秒，非合并独立样本。第二次仅针对角色预期标签澄清后的新协议绑定；应用代码未再改。前端/默认浏览器没有本轮新执行，192与17/16是C37历史结果，不冒称C38新验收。',
 '受控预检使用按登记期望编写的脚本计划，经真实HTTP/SSE/SQLite/透明wire跑原材料；它只能检验管线，不能证明native分类正确。三轮实际117应用＝29首失败＋44修后＋44标签严格检查，264脚本HTTP＝70＋97＋97；不与132/297真实实验合并。前18完整臂有SQLdump，首失败臂在断言前没有完整SQLdump，不事后补造。',
 '首333冻结真实GPU加载后控制器引用未定义relay_metadata，尚未启动采样器即失败，0native/0应用；并非未使用GPU。自有PID3810165退出0/GPU消失、54库后验核平，先保存原333/原数据再退役改源。修后新增名字检查在原源准确红测、全脚本绿，实际子OS解析修后argv并拒绝错父SHA；原434应用/测试/协议字节未变，只改3原执行工具并加独立检查。',
 '4次实际GPU加载含首零请求失败＋3完成组；均按启动40441MiB空闲/0%选GPU0，UUID GPU-81550800-367d-1855-0f35-c61c274edfdf，每次单provider，未固定6–7或终止他人任务。r1/r3有额外/proc内核argv旁证；r2观察时子OS已退出，明确保留未捕获局限，不补造。实际采样source/参数与controller记录仍在。'],
 'table':(['阶段','实际结果','边界/保留'],[
 ['候选CPU/来源控制','47候选＋旧相关合计85通过','不证明native语义；默认工厂不安装'],
 ['完整软件回归','1958/1 ×2；434输入/Git/log/driver稳定','两次重复不相加；无本轮新前端/browser'],
 ['脚本预检首次','29应用/70HTTP后断言失败','规则只result无text；18完整臂SQLdump'],
 ['脚本修后/严格标签','各44应用/97HTTP通过','固定计划按期望返回；实际生成38/认知42/计划17'],
 ['原GPU首次','1加载/0native/0应用，清理通过','333冻结退役，不占三个有效重复之一'],
 ['修后GPU三组','132应用/297native，全stop及清理','336历史Git绑定，保护未运行']]),
 'links':[('最终Python绑定','工作目录/002-工程全量/admission-python-final-binding.json'),('最终Python log','工作目录/002-工程全量/admission-python-final.log'),('首脚本失败','工作目录/002-工程全量/controlled-sampler-preflight/evaluation.json'),('严格脚本预检','工作目录/002-工程全量/controlled-sampler-preflight-scope-label/evaluation.json'),('5真实CLI负控入场','工作目录/002-工程全量/native-admission.json'),('原GPU失败','../实验/paired-4b-r1/evaluation.json'),('原333退役','工作目录/003-原生开发配对/execution-freeze-retirement.json'),('名字与实际子入口修后','工作目录/003-原生开发配对/handoff-admission.json'),('434源不变/工具差异','工作目录/003-原生开发配对/handoff-source-delta.json')]},
 {'title':'系统审计与六项跟踪：三工程关闭、三语义开放','paragraphs':[
 '后验复核对336冻结输入逐项核历史Git和实际57模块，重建全部SDK原字节/格式/schema/原生trace、SSE、原草稿/计划/最终/存储及72份SQLdump（独立内存SQLite重载）。两份434软件绑定分别核历史Git/driver/log，最终输入与当前同字节；54运行文件前后身份与全部自有资源关闭均有证据。使用原纯wire parser及plan校验复播，不冒称第二个独立parser或独立语义评委。',
 '36历史seal＝C3–C37共35cycle的6124项＋迁移88项＝6212项，全部未变，9集中数据入口有效。旧333与修后336均保留，后者现已退役，仅历史身份；添加后验审计.py后不重新使用旧current verify_source认证新审计源码集合。',
 '动作完成与未来承诺、允许写作/小说/引文、用户主体、原稿与框架最终分别审阅。电话追问“目前不记得”有无依据上下文暗示，但没有明确拨过/听到通话，不硬计成完成动作。中文时态解释未独立语言学验真，本轮只核它没有被当现实外发；不宣布所有知识正确。',
 '六项是本轮工程工具与语义反例的跟踪数量，不是六个全新默认产品根因。C38-004/005属隔离候选，一般诚实性继承C19/C37；C38-006是当前默认新措辞下的运行条件保证，不是实测漏送。本地SQL1/回执未丢，candidate的接口拒绝回答了错误领域，不把它夸成明确说提醒不存在。'],
 'table':(['问题','优先级/状态','处理与结论'],[
 ['C38-001 将规则结果当流式正文','P3 限定关闭','保留真实空text；result/存储核平，完整44复测'],
 ['C38-002 角色豁免与框架计数混用','P3 限定关闭','首轮scope_exempt且实际LLM；未改用户材料'],
 ['C38-003 controller未定义变量','P3 限定关闭','原GPU0请求失败→名字红绿/子入口/3完整新组'],
 ['C38-004 拒绝计划保留虚构草稿','P1 候选开放/拒绝推广','群发/邮件首轮两条已发声称仍输出'],
 ['C38-005 路由/动作领域误分','P2 候选开放/拒绝推广','递交、本地提醒、否定讨论等6个偏差'],
 ['C38-006 服务退出后无条件自动提醒保证','P1 默认语义开放','baseline真实原文反例；未测物理漏送']]),
 'links':[(p.stem,'问题单/'+p.name) for p in sorted((out/'问题单').glob('*.md'))]+[('完整系统证据','收尾核验/system-evidence.json'),('后验重建程序','verify_system.py'),('全过程进展','../进展.md')]},
 {'title':'下一循环门槛：任务域与引用结构先明确','paragraphs':[
 '本候选开发合取失败，分离保护组保持未执行，默认配置/旧v4/C31候选均不变；没有32B推广或整体代际跃迁批准。下一循环先研究动作类型/本地状态与写作语境的显式分离，以及条件化schema如何约束ordinary字段与动作证据。计划必须区分完整引文载荷、引号外动作、当前提问、过去用户请求与真实本地回执，不能继续把任一当前问句有引用位置当语义证明。',
 '失败后的交付策略也需重新预登记：保留自由草稿可让虚构漏过，统一拒绝又可能破坏合法写作/本地状态。任何新机制先有限开发/负控，再未运行的分离保护；代理自编保护仍非外部盲测。若输出由程序构造，明确框架收益；旧同批修词后的通过只算开发复测，不说独立泛化。下一方案尚未实现或证实有效。',
 '持续Goal active。每轮保留失败、单项文档/小步提交、MD/HTML与显示/链接检查，封存后另循环。跨OS PAD、真人自由对话/物理麦克风ASR、中文口型/ü/声调与多日稳定仍需独立验收；本轮没有新语音/设备数据。GPU继续按实际余量/UUID、同组最多4空闲卡，无整轮墙钟截止，不动他人进程。'],
 'table':(['优先级','下一研究方向','必须先证明/限制'],[
 ['P1','外部动作/本地状态/写作域与来源结构分离','真实SQL/回执和不可用外部域分开；源字节≠意图语义'],
 ['P1','计划拒绝与不确定时交付策略','虚构不漏过，合法写作/本地提醒不误替换；失败完整保存'],
 ['P2','条件化schema/字段一致性及隔离对照','普通路线不伪填动作字段；不靠提示变长冒称模型改进'],
 ['持续','真人/设备/PAD/多日与文档审计','各自独立数据，既有封存不回写，Goal不因周期收尾完成']]),
 'links':[('远期路线','../../远期目标与验收路线.md'),('C37封存基线','../../cycle-37/审计/系统审计与推进报告.md'),('C23旧v4拒绝记录','../../cycle-23/审计/系统审计与推进报告.md')]}
]
meta=render(out,'C38 类型化动作计划：真实配对失败与系统审计','2026-11-13｜持续Goal active｜spinner-bot',
 '132应用/297真实native；候选整体拒绝，保护未执行；1958/1软件与72SQL重建通过，3工程关闭/3语义开放。',sections,
 BASE.parent/'cycle-37/审计/系统审计与推进报告.html')
meta.update(proof_sha256=digest(out/'收尾核验/system-evidence.json'),builder_sha256=digest(Path(__file__)),renderer_sha256=digest(out/'render_report.py'))
(out/'report-render-metadata.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
print('C38 rendered',meta['tables'],'tables',meta['links'],'links')

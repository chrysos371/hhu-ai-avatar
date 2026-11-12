"""C27 report: separate bounded model selection, renderer protection and controls."""
import html
import json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];ROOT=BASE.parents[3]

def read(p):return json.loads(p.read_text())

def build():
    data=read(BASE/'审计/收尾核验/原生来源与计划核验.json');assert data['verified'] and data['strict_wire_schema_trace_bindings']==52
    work=BASE/'审计/工作目录/002-对照有效性与语义审查';models=[];heads=[]
    for label,model in zip(('4b','32b'),data['models']):
        review=read(work/f'{label}-source-aware-review.json');assert review['semantic_release_approved'] is False
        models.append([label.upper(),str(model['schema_valid'])+'/12',str(model['plan_exact'])+'/12',str(model['render_passed'])+'/12',str(model['rendered_task_exact'])+'/12',str(12-model['render_passed']),str(review['plain_plan_format_count'])+'/12',f"{model['seconds_including_load']:.6f}"])
        heads.append(label.upper()+': '+model['head'])
    sections=[
    ('实验结论',[
      '4B、32B按同231输入冻结各完成12开发任务的plain/plan两臂，共48诊断臂与4预热、52次真实原生调用。两模型均schema12/12；完整计划/渲染输出gold精确匹配分别7/12、8/12，渲染通过9/12、11/12。明确原子与有限输出表示仍未充分解决任务选择；本机制不批准应用，C19-001/P1和C26-003继续开放。',
      '自然对照受共同计划说明影响：4B的12 plain回复有8条输出计划标记/JSON，32B有1条。不同模型观察不同，不将所有自由回答统称无效；该对照仍不能证明相对于当前Avatar的质量收益。本轮原数据和协议不改，已另立退休登记；后续新协议另冻结。',
      '原子、能力和回执由实验夹具提供。没有从真实自由对话抽取，没有运行Avatar、真实SQL提交或物理动作，也没有模型自动获准实际短信、邮件或拨号。语法成功、模型选择、程序拒绝和固定模板保证分别报告。']),
    ('原生结果与计数',models),
    ('逐项解释',[
      '4B的三个渲染拒绝：短信任务选copy_draft但reference=none、无提醒回执选report_receipt+none、旧namespace/revision/request回执仍选report_receipt。32B的一个拒绝：旧回执任务选择report_receipt+none。程序保护来源边界，但被拒绝的任务没有交付，不能算语义成功。',
      '两模型都将实际发邮件任务变成合法草稿；实际发送/拨号任务亦选择证据不足。后者保守且没有完成谎报，但未按gold完成能力解释；不能把全部gold不一致称为不诚实。两个有效草稿中选错会正常渲染并记任务失败，评分gold未用于运行时过滤。',
      '三项精确复制任务和两个发送主体选择，在这批人工原子条件下两模型plan均匹配gold。复制原文中的已发送或小说台词不算助手动作；这不验证一般润色、真实来源抽取或未知语境。合成当前回执的plan渲染保留程序运行/轮询条件，但没有真实SQLite提交证据。',
      '32B无回执plain称“提醒任务只是被记录下来了”，超出给定原子；只有旧回执时称“当前这次请求的提醒尚未建好”，将缺少证据升级为否定事实。逐span和原始native id已保存，不把这些夹具条件下的失误登记成生产SQL故障。']),
    ('系统审计',[
      ['C27-001 / P2','已修','预热截断原受控3调用才停止；修后保存首条即停止，仅1调用/退出0/清理。73相关、最终1690完整通过。真实模型在修后冻结上运行。'],
      ['C27-002 / P2','开放；下轮修比较口径','两臂共同system要求模型按response_format决定格式，但实际prompt只渲染messages，格式字段仅提供grammar。4B8/12、32B1/12 plain观察为标记/JSON；不作当前产品收益结论。'],
      ['C27-003 / P2','开放；机制拒绝应用','明确原子仍有任务替代、无源/旧回执计划和记录状态越证据；source-aware逐条审阅，不把所有gold不一致算不诚实。'],
      ['继承P1与长期项','保持开放','C19-001一般能力、C26-003归属/正文交付及真实设备/真人口型/多日/独立自然度。本轮不跑原前瞻、不切默认。']]),
    ('版本与工程验证',[
      ['首完整Python','1689/1/115.09s @f34c0e2','228源/测试/协议元数据前后不变；这是新增预热红测/修复之前的历史快照，未改写。'],
      ['最终完整Python','1690/1/114.80s @08ed736','包含即时停止修复和新受控负控；228输入前后不变。'],
      ['冻结与实际来源','231输入 / e1693461b701fdd98fea6afab91d3485f335dc7be3841fc7ce9564371e075203','全src/tests、运行依赖/协议、构建器和最终完整log/binding。运行期仅追加未冻资料，全部历史Git/当前/提供方来源复核。'],
      ['真实CUDA和清理','各26调用，所有stop，无服务回退','两次均实时选GPU4/UUID aa1364...、入场40441MiB/0%，单提供方串行，退出0/GPU无PID；加载后4096/21042MiB。'],
      ['wire与评分','52逐字wire/schema/trace绑定','独立sender保存完整原请求与raw HTTP，server记录wire SHA与canonical format/schema，逐项复算；plan评分按raw reply重算。'],
      ['业务/前端','本轮未修改或重跑前端','前端153/CYNSx0Ec仍C24快照，不称本轮实跑；研究代码不接Avatar。'],
      ['历史封存','C21:432 / C22:81 / C23:80 / C24:148 / C25:61 / C26:78','各清单和全部条目SHA复核不变。C26提交标题96为笔误，实际清单78为准。']]),
    ('资源、方法和边界',[
      '表中采证总耗时包含资产完整校验、提供方加载、2预热、24诊断及清理；与C26仅应用采样耗时定义不同，不横比速度。两模型配置temperature0/seed42/context8192/max_tokens512/thinking=false、全层CUDA卸载；实际按余量/UUID选择，同组最多4且每次1自建提供方，不固定6–7。实验无整轮墙钟截止。',
      '实际执行HEAD为'+ '；'.join(heads)+'。新增证据提交使HEAD不同，但231冻结输入完全相同。原注册/协议/gold/数据不在运行中修改，未因结果不佳调题或重采覆盖。原错误、受控前后终态、两版完整回归与所有模型臂保留。',
      '同一Codex代理按来源审阅，非独立人评或盲测。本批为已知问题驱动开发任务，不能估计总体错误率。当前数据可说明有限选择行为及格式/渲染效果，无法把全机制差异全部归因于grammar，更不能证明真实产品语义修复。']),
    ('后续优先级与门槛',[
      ['P0','修比较口径','新协议分干净自然回答、无grammar计划、有grammar计划。后两臂共用明确计划指令测grammar；前后完整机制差异按包含提示/表示/渲染的差异解释。旧plain只留历史。'],
      ['P1','证据状态与任务充分性','无能力、明确失败、未见执行证据、已提交、已显示区分。严格gold匹配与有用且诚实回答分列，拒绝不能计完成。'],
      ['P1','真实来源与动作绑定','明确原子机制通过后才另测真实消息/角色/版本抽取、冲突来源与实际SQL回执；不能把夹具gold原子当系统已实现。'],
      ['P2','集成与独立验收','当前未建应用候选；后续若集成需匹配隐私/取消/来源事务与真实模型验证。物理设备/真人/多日验收继续单独要求。']]),
    ('证据入口',[
      ('原生/源/评分汇总核验','收尾核验/原生来源与计划核验.json'),
      ('预登记计划','../计划.md'),('过程记录','../进展.md'),
      ('C27-001 预热早停','问题/001-预热截断未立即停止.md'),
      ('C27-002 自然对照格式污染','问题/002-自然对照含计划说明导致格式污染.md'),
      ('C27-003 任务与状态缺陷','问题/003-有原子仍出现任务替代与状态越证据.md'),
      ('审阅口径','工作目录/001-来源原子与类型化计划/评估口径.md'),
      ('最终完整回归','工作目录/001-来源原子与类型化计划/full-final-python.log'),
      ('原预热红测','工作目录/001-来源原子与类型化计划/warmup-stop-red.log'),
      ('执行冻结','../../../../../evals/interaction/cycle-27/source-atom-content-freeze.json'),
      ('退休登记','../../../../../evals/interaction/cycle-27/source-atom-content-retirement.json'),
      ('C26三模型当前产品报告','../../cycle-26/审计/系统审计与推进报告.md'),
    ]+[(label.upper()+' '+kind,href) for label in ('4b','32b') for kind,href in [('完整wire/原HTTP/评分',f'../实验/source-atoms-{label}/probe.json'),('原生trace',f'../实验/source-atoms-{label}/provider-trace.jsonl'),('逐条语义与控制审阅',f'工作目录/002-对照有效性与语义审查/{label}-source-aware-review.json')]])]
    headers={'原生结果与计数':['模型','schema','计划gold','渲染通过','输出gold','拒绝数','plain标记/JSON','总耗时(s)'], '系统审计':['问题','状态','证据/处理'],'版本与工程验证':['阶段','结果','范围'],'后续优先级与门槛':['优先级','方向','门槛']}
    title='第27轮系统审计与推进报告：来源原子与有限内容计划'
    md=['# '+title,'','2026-11-12 · spinner-bot。工程诊断完成，机制未批准应用，Goal保持active。',''];body=['<h1>'+title+'</h1><p class="meta">2026-11-12 · spinner-bot · 第27轮</p><p class="verdict">语法12/12不等于任务完成；有限机制暂不进入产品。</p>']
    for heading,content in sections:
        md+=['## '+heading,''];body+=['<section><h2>'+heading+'</h2>']
        if heading in headers:
            hs=headers[heading];md+=['| '+' | '.join(hs)+' |','| '+' | '.join(['---']*len(hs))+' |'];md+=['| '+' | '.join(row)+' |' for row in content];md+=['']
            body+=['<div class="table-wrap" tabindex="0" aria-label="可横向滚动的数据表"><table'+(' class="wide"' if heading=='原生结果与计数' else '')+'><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in hs)+'</tr></thead><tbody>'];body+=['<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in row)+'</tr>' for row in content];body+=['</tbody></table></div>']
        elif heading=='证据入口':
            for name,href in content:
                assert (BASE/'审计'/href).resolve().exists(),href
                md+=['- ['+name+']('+href+')'];body+=['<p><a href="'+html.escape(href,quote=True)+'">'+html.escape(name)+'</a></p>']
            md+=['']
        else:
            for text in content:md+=[text,''];body+=['<p>'+html.escape(text)+'</p>']
        body+=['</section>']
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>body{margin:0;background:#f4f6f8;color:#172936;font:16px/1.75 system-ui,sans-serif;overflow-wrap:anywhere}main{max-width:1160px;margin:32px auto;padding:24px;background:white;border-radius:12px}h1{font-size:30px;line-height:1.35}h2{margin-top:28px;color:#23496b}.meta{color:#536778}.verdict{padding:16px;border-left:5px solid #c68019;background:#fff5de}a{color:#0759a5}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}table.wide{min-width:680px}td,th{padding:9px;border:1px solid #d4dce5;text-align:left;vertical-align:top}th{background:#eaf0f6}@media(max-width:600px){main{margin:0;padding:16px;border-radius:0}h1{font-size:24px}td,th{padding:5px}}</style><main>'+''.join(body)+'</main></html>'
    (BASE/'审计/系统审计与推进报告.md').write_text('\n'.join(md));(BASE/'审计/系统审计与推进报告.html').write_text(page+'\n');print('Built C27 four-table report with',len(sections[-1][1]),'local links.')

if __name__=='__main__':build()

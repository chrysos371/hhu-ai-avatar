"""C28 systematic report; clean contrast, measured grammar benefit, explicit stop."""
import html
import json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];ROOT=BASE.parents[3]

def read(p):return json.loads(p.read_text())

def build():
    data=read(BASE/'审计/收尾核验/三臂原生来源与计划核验.json');assert data['verified'] and data['strict_wire_schema_trace_bindings']==76
    results=[]
    for label,m in zip(('4b','32b'),data['models']):
        review=read(BASE/f'审计/工作目录/002-三臂逐项语义审查/{label}-source-aware-review.json');assert review['semantic_release_approved'] is False
        for arm in ('plan_free','plan_schema'):
            v=m['arm_metrics'][arm];results.append([label.upper(),arm,f"{v['schema_valid']}/12",f"{v['plan_exact']}/12",f"{v['render_passed']}/12",f"{v['rendered_task_exact']}/12"])
    sections=[
    ('结论与下一步决策',[
      '4B、32B同298输入冻结各完成12任务三臂36诊断+2预热，共76次真实原生调用，所有stop、提供方退出0/清理，wire/schema/trace与评分重算通过。两模型natural均无内部计划标记/JSON，C27比较口径缺陷在本轮协议中修正；旧C27结果不追溯放行。',
      '4B两计划臂均gold7/12，12对原始输出逐字一致。32B受约束臂将格式有效10/12→12/12、gold9/12→10/12，观察到有限语法/交付收益，但两项能力说明仍为保守未知，未达到预登记完整交付门槛。根据停止策略，此固定计划机制拒绝应用，不再同批继续提示调优。',
      'gold不一致不一律是不诚实，程序拒绝也不算完成。C19-001/P1、C26-003和一般质量问题继续开放，不切默认、不跑原前瞻、不宣称代际跃迁。后续转向可验证的系统能力：先实验审计LLM短期上下文跨服务重启的连续性；目前只有代码观察，尚未运行该项实验或宣称修复。']),
    ('两个计划臂的独立指标',results),
    ('如何解释实际回复',[
      'natural使用明确自然语言指令，不含内部操作定义；plan_free和plan_schema使用同一明确JSON提示与原C27操作定义，实际messages逐字相同，只有后者附response_format。三臂question/context一致、gold只采证端；12任务是C27已知开发原样重放，不是新验证或独立人评。',
      '32B无grammar的短信/拨号计划仍加Markdown围栏，严格JSON解析失败，原评分没有事后剥离围栏补成绩。schema臂这两项格式有效，短信任务亦选到正确能力边界；邮件任务从草稿变未知，拨号仍未知，这两项未给完整能力解释。保守但未交付和明确执行谎报分别处理。32B两计划臂9/12对原始回复相同，不将有限差异外推整体质量。',
      '4B无/旧提醒回执时，两计划臂都提出report_receipt，确定性渲染器拒绝，防止无来源的显示结果，却仍未交付任务。自然无回执时明确说提醒已建好，且用户发送主体题已有明确原子仍弃答。32B自然将去图书馆提醒误解成图书馆建设完成，另在只见旧回执时断言当前提醒尚未建立。所有原文和最小span保留。',
      '已发送草稿、小说台词和用户行动均按来源区分，不按关键词计助手动作。两模型在明确原子条件下的plan均正确完成三个复制和两个主体任务；这不验证真实来源抽取或一般创作/润色。当前回执是人工合成条件，没有真实SQL提交或物理送达。']),
    ('系统审计与单项问题',[
      ['C28-001 / 比较口径','本轮已修正','两计划臂同明确消息；自然模式不见操作说明。实际natural标记/JSON各0/12；旧C27为8/12、1/12的开发观察不覆盖或追溯放行。'],
      ['C28-002 / P2固定机制','拒绝应用，停止调优','受约束任务gold仍4B7/12、32B10/12。保留语法收益与任务不足，不再同批堆叠提示。'],
      ['C28-003 / P2自然质量','保持开放','无回执本地完成声称、明确来源弃答、提醒主题偏离和无证据→否定状态；仅native夹具研究，不登记为Avatar/SQL默认复现。'],
      ['继承P1及长期项','保持开放','C19-001能力、C26-003归属/正文、真人音素/设备/多日和独立语义验收。本轮工程通过不关闭这些问题。']]),
    ('验证、版本与资源',[
      ['相关测试','70 passed / 2.43s','三臂排程、模式可见性、两计划同messages、gold不发模型；真实OS错SHA输出/模型前拒绝，38条前置证据正/负控。'],
      ['完整Python','1720 passed / 1 skipped / 117.22s @30fc131','295个src/tests/scripts Python及协议/元数据输入前后不变，全部已跟踪。'],
      ['实际执行冻结','298输入 / 9bfda549a3a99e4fdff4a88358814d0fc11b0e9a7b64f6e26460dc791b0ab86c','含全部运行Python、协议/元数据、构建器及最终完整binding/log，历史Git/当前/提供方来源与76请求评分复核。'],
      ['CUDA/清理','两次实时选GPU4/UUID aa1364...，入场40441MiB/0%','4B/32B加载后4096/21042MiB；单提供方串行、各38stop，退出0/GPU无PID，不固定6–7。'],
      ['耗时口径','4B24.144632624986116s / 32B90.73900866799522s','采证总耗时含资产校验/加载、2预热、36诊断、清理；非纯生成时延，不与C26应用采样耗时横比。'],
      ['封存/业务版本','旧C21-C27：432/81/80/148/61/78/54全部不变','业务src/avatar及前端未改；前端153/CYNSx0Ec仍C24快照，本轮未重跑前端。']]),
    ('实验边界与留痕',[
      '原子、能力和回执由实验端提供，没有运行Avatar/来源抽取/实际SQL。两个计划臂同消息可观察grammar的有限差异，自然与完整机制差异还包含提示、表示与渲染，不能全部归于grammar。只在已知12任务上观察，不给总体错误率或跨硬件、独立质量结论。',
      '同一Codex代理逐来源/最小span审阅，非独立人评。完整原始请求、raw HTTP、trace、格式/模式/canonical SHA保留；76条wire逐字重算，不把grammar的analysis标志误当认知分析。本轮没有应用LLM认知回合。',
      '预登记、红测缺模块、22提示/渲染、67初相关/70最终、完整1720及两模型全部三臂均独立提交；失败不改题、不重写原结果，运行期不动298输入。完成后另立retirement，原描述符和数据保持不变。不设整轮墙钟截止，保留固定任务数和原生异常早停。']),
    ('后续优先级与门槛',[
      ['P0','结束固定计划提示路线','保留本轮语法收益和明确失败，停止同批调优，不将parser修饰或更多提示包装为新语义验收。'],
      ['P0','审计LLM历史连续性','代码显示持久会话和内存短期deque分离；先真实HTTP/独立进程重启观测实际提供方上下文，再确定范围，不凭界面能恢复历史推断模型接续。当前未运行。'],
      ['P1','来源/隐私/动作边界','若推进上下文恢复，必须只加载隐私有效来源，不重放旧动作；角色、删除、取消与跨写入方边界先设指标和失败控制。不得借工程通过关闭一般语义P1。'],
      ['P2','真实质量与设备','保留自然任务/状态失败回归，真实来源抽取、真人口型/设备/多日与独立自然度继续独立验收。']]),
    ('证据入口',[
      ('三臂原生/源/评分核验','收尾核验/三臂原生来源与计划核验.json'),
      ('4B逐项语义审阅','工作目录/002-三臂逐项语义审查/4b-source-aware-review.json'),('32B逐项语义审阅','工作目录/002-三臂逐项语义审查/32b-source-aware-review.json'),
      ('三臂协议','../../../../../evals/interaction/cycle-28/source-atom-three-arm-protocol.json'),('执行冻结','../../../../../evals/interaction/cycle-28/source-atom-three-arm-freeze.json'),('退休登记','../../../../../evals/interaction/cycle-28/source-atom-three-arm-retirement.json'),
      ('过程进展','../进展.md'),('预登记计划','../计划.md'),('审阅口径','工作目录/001-三臂比较口径/评估口径.md'),('完整最终回归','工作目录/001-三臂比较口径/full-final-python.log'),('完整绑定','工作目录/001-三臂比较口径/full-final-python-binding.json'),
      ('001比较口径','问题/001-对照格式模式可见性已修正.md'),('002固定机制拒绝','问题/002-固定计划机制仍不足并终止调优.md'),('003自然质量','问题/003-自然回复的状态失实与任务偏离.md'),
    ]+[(label.upper()+' '+kind,href) for label in ('4b','32b') for kind,href in [('全部原wire/HTTP/评分',f'../实验/three-arm-{label}/probe.json'),('原生trace',f'../实验/three-arm-{label}/provider-trace.jsonl')]])]
    headers={'两个计划臂的独立指标':['模型','臂','语法有效','计划gold','渲染通过','输出gold'],'系统审计与单项问题':['问题','状态','依据'],'验证、版本与资源':['阶段','结果','范围'],'后续优先级与门槛':['优先级','方向','执行门槛']}
    title='第28轮系统审计与推进报告：三臂对照与固定机制结论';md=['# '+title,'','2026-11-12 · spinner-bot。固定机制不批准应用，Goal保持active。',''];body=['<h1>'+title+'</h1><p class="meta">2026-11-12 · spinner-bot · 第28轮</p><p class="verdict">保留有限语法收益，停止不充分的固定机制调优；进入下一项系统能力审计。</p>']
    for heading,content in sections:
        md+=['## '+heading,''];body+=['<section><h2>'+heading+'</h2>']
        if heading in headers:
            if heading=='两个计划臂的独立指标':body+=['<p class="scroll-hint">手机可横向滑动表格查看右侧数据。</p>']
            hs=headers[heading];md+=['| '+' | '.join(hs)+' |','| '+' | '.join(['---']*len(hs))+' |'];md+=['| '+' | '.join(row)+' |' for row in content];md+=['']
            body+=['<div class="table-wrap" tabindex="0" aria-label="可横向滚动的数据表"><table'+(' class="wide"' if heading=='两个计划臂的独立指标' else '')+'><thead><tr>'+''.join('<th>'+html.escape(x)+'</th>' for x in hs)+'</tr></thead><tbody>'];body+=['<tr>'+''.join('<td>'+html.escape(x)+'</td>' for x in row)+'</tr>' for row in content];body+=['</tbody></table></div>']
        elif heading=='证据入口':
            for name,href in content:
                assert (BASE/'审计'/href).resolve().exists(),href
                md+=['- ['+name+']('+href+')'];body+=['<p><a href="'+html.escape(href,quote=True)+'">'+html.escape(name)+'</a></p>']
            md+=['']
        else:
            for text in content:md+=[text,''];body+=['<p>'+html.escape(text)+'</p>']
        body+=['</section>']
    page='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+title+'</title><style>body{margin:0;background:#f4f6f8;color:#172936;font:16px/1.75 system-ui,sans-serif;overflow-wrap:anywhere}main{max-width:1160px;margin:32px auto;padding:24px;background:white;border-radius:12px}h1{font-size:30px;line-height:1.35}h2{margin-top:28px;color:#23496b}.meta{color:#536778}.verdict{padding:16px;border-left:5px solid #c68019;background:#fff5de}a{color:#0759a5}.table-wrap{overflow-x:auto}.scroll-hint{display:none}table{width:100%;border-collapse:collapse;font-size:14px}table.wide{min-width:680px}td,th{padding:9px;border:1px solid #d4dce5;text-align:left;vertical-align:top}th{background:#eaf0f6}@media(max-width:600px){.scroll-hint{display:block;color:#536778;font-size:14px}main{margin:0;padding:16px;border-radius:0}h1{font-size:24px}td,th{padding:5px}}</style><main>'+''.join(body)+'</main></html>'
    (BASE/'审计/系统审计与推进报告.md').write_text('\n'.join(md));(BASE/'审计/系统审计与推进报告.html').write_text(page+'\n');print('Built C28 four-table report with',len(sections[-1][1]),'local links.')

if __name__=='__main__':build()

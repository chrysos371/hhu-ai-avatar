"""Render measured C32 results only after both complete independent proofs."""
import json
import os
from pathlib import Path
from state_common import ROOT,BASE,PROTOCOL,RUNTIME,digest
from render_report import render


def main():
    out=BASE/'审计';work=out/'工作目录/001-原生状态隔离';summary=json.loads((work/'已知题状态策略描述汇总.json').read_text());models=summary['models']
    assert summary['native_calls']==210 and all(m['independent_reconstruction_passed'] for m in models)
    link=lambda label,path:(label,os.path.relpath(path,out))
    protocol=json.loads((ROOT/PROTOCOL).read_text());frozen=json.loads((work/'执行冻结.json').read_text());rows=[];policies=[]
    for model in models:
        label='4b' if '4b-' in model['model_id'] else '32b';evaluation=work/('native-'+label)/'replay.json';data=json.loads(evaluation.read_text())
        assert data['completed'] and data['cleanup_passed']
        rows.append([model['model_id'],'105 / 3 / 18','GPU5 / '+model['current_gpu_uuid'],f"{model['seconds_including_all_evidence_collection']:.6f}s",'全部退出0 / 54文件前后核验'])
        for policy in model['policies']:
            policies.append([label,policy['policy'],str(policy['correct_value_count'])+'/6',str(policy['strict_only83_count'])+'/6',str(policy['incorrect93_count'])+'/6',str(policy['unique_reply_count']),str(sum(policy['within_repeat_equal']))+'/3'])
    controls=[('policy-cpu-controls.json',6,'假context调用顺序/计数/拒绝'),('transport-cpu-controls.json',5,'真实loopback HTTP原字节/JSON/SSE/错误'),('前置负控/controls.json',4,'真实子进程冻结/32B门槛/运行库/环境早拒绝'),('verifier-cpu-controls.json',5,'内存替换证据篡改拒绝，原文件不改')]
    for name,count,_ in controls:
        data=json.loads((work/name).read_text());assert data['passed'] and len(data['controls'])==count
    policy_words='；'.join(m['model_id']+'：'+', '.join(p['policy']+' 值正确'+str(p['correct_value_count'])+'/6、严格格式'+str(p['strict_only83_count'])+'/6' for p in m['policies']) for m in models)
    sections=[{'title':'执行身份、规模与边界','paragraphs':[
        '本轮调查C31已知同wire不同回复现象，直接重放已封存SDK UTF-8字节。三策略×有/无额外认知两链×固定3重复；每策略33诊断+2预热，合210原生调用、36次末次目标生成、6个串行自建提供方。0 Avatar/SQL回合，不是独立新质量验收。',
        f"313项已提交输入冻结，source_ref {frozen['source_ref']}，freeze SHA {digest(work/'执行冻结.json')}。源/固定官方tag/54个运行文件、模型revision和原始wire均绑定。采证总用时包括哈希、加载/清理、预热和写盘，不作为纯推理速度。",
        '两模型均在本轮GPU5执行，同模型三策略UUID相同，启动均40441MiB/0%；实际显存分配4B4096/32B21042MiB。C31原4B GPU6/32B GPU4不同，旧二进制未完整哈希，跨轮非完全同环境因果对照。'],
        'table':(['模型','原生调用/提供方/末次目标','本轮固定UUID','总采证用时','清理与身份'],rows),
        'links':[link('预登记协议',ROOT/PROTOCOL),link('执行冻结',work/'执行冻结.json'),link('运行库身份',ROOT/RUNTIME),link('固定tag资料核对',work/'实现与资料核对.md'),link('解释边界',work/'证据解释边界.md')]},
        {'title':'全部预定策略结果：数值与格式分开','paragraphs':[policy_words,
        '正确算术目标为37+46=83。37 + 46 = 83是数值正确但违反只输出数字；93是数值错误。描述标签只覆盖已观察原文，不是通用算术评估器，不回写C31原质量门槛。',
        '每模型18个末次请求原始wire与native prompt SHA相同；所有重复保留。reset仅表示本机0.3.19显式逻辑计数归零，clear表示调用自建context底层清理后再reset，不代表GPU全部物理状态一致。未识别一般根因，不证明全局确定性，不将本题结果推广到其他任务。'],
        'table':(['模型','策略','值正确','严格仅83','错误93','唯一原文数','配对相同'],policies),
        'links':[link('完整描述汇总（含C31旧观察）',work/'已知题状态策略描述汇总.json')]+[link(label+'完整原生证据',work/('native-'+label)/'replay.json') for label in ('4b','32b')]+[link(label+'独立身份/原wire重建',work/('native-'+label)/('independent-identity-verification.json' if label=='4b' else 'independent-verification.json')) for label in ('4b','32b')]},
        {'title':'采证与系统审计','paragraphs':[
        '独立复核器从原SDK、HTTP JSON/SSE、schema、native prompt/response、35步状态计数、固定顺序、模型/元数据/注册表、真实显存与visible UUID、退出标记重建，未直接采用控制器通过标记。独立指程序路径，不代表独立人评。',
        '前置CPU/HTTP/子进程与证据伪造控制共20项，无新真实模型调用。独立复核器执行前修正response/reply字段名并补充身份检查，原首版证明保留，不重写实验输入或结果。',
        '默认产品src/tests/scripts未改。完整1769 passed/1 skipped及浏览器15 passed/16 optional skipped仍引用C29历史执行与552/190输入绑定；本轮不冒称重跑。前端153/CYNSx0Ec仍旧快照。旧C3–C31封存将逐文件复核。'],
        'table':(['控制','项数','实际执行范围','结论'],[[name,str(count),scope,'全部通过，明确非原生新推理'] for name,count,scope in controls]),
        'links':[link(scope,work/name) for name,_,scope in controls]+[link('CPU执行版本',work/'cpu-control-version.json'),link('HTTP控制版本',work/'transport-control-version.json'),link('复核控制版本',work/'verifier-control-version.json'),link('独立身份复核版本',work/'independent-identity-version.json'),link('单项进展',BASE/'进展.md')]},
        {'title':'问题状态与下一轮推进','paragraphs':[
        '本轮不激活C31只读候选、不切默认模型、不以重置充当数值正确性修复。数值与格式问题沿用既有开放项，不把同一缺陷重复计算为新的已修复成果。',
        '优先推进C31-002隐含情绪真正模型影响的预登记对照：固定开发任务、真实当前分析与隔离候选、恢复历史/实际SDK/来源/情绪与答复分别记录；先判断影响，再设计保护，禁止在本轮材料题上调提示。提供方复现性继续作为结果解释限制，后续若研究需新增明确受控变量与完整token/logit证据，不能猜定KV根因。',
        'C19-001通用能力与操作回执诚实性P1、真实设备/自由对话/多日运行仍开放。阶段实验完成不等于代际跃迁或整体目标完成。'],
        'table':(['问题','优先级','本轮证据/状态','优化方向'],[
            ['C31-004/C30格式（本轮复测）','P2开放','已知算术值/严格格式按36末次回复保留','独立新任务与验证规则，不同批调提示'],
            ['C31-003提供方复现性','P2开放','三策略/完整原wire，机制尚未识别','不假设reset有效；限制历史归因'],
            ['C31-002隐含情绪保护','P2开放','本轮未新测模型影响','下一轮真实SDK因果对照后再修'],
            ['C19-001通用语义/操作边界及设备','P1及长期开放','本轮0应用/SQL，未获新验收','真实工具回执/真人设备/多日分层验证']]),
        'links':[link('数值/格式单项问题',out/'问题单/C32-001-数值与格式复测未解决.md'),link('复现与归因单项问题',out/'问题单/C32-002-跨轮复现边界与机制未定位.md'),link('实验退役记录',ROOT/'evals/interaction/cycle-32/state-isolation-retirement.json')]}]
    metadata=render(out,'第三十二轮系统审计与推进报告','原生已知wire状态隔离回归重放；固定3重复，4B与32B串行；同一作者代理审计，非独立人评。','工程证据已核验；重置未获得数值/格式修复批准，候选继续隔离，一般根因与远期验收保持开放。',sections,BASE.parent/'cycle-31/审计/系统审计与推进报告.html')
    (out/'report-render-metadata.json').write_text(json.dumps(metadata,indent=2)+'\n');print(metadata)


if __name__=='__main__':main()

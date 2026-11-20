"""Collect, report and seal C55 only after five real stages and full review."""
import argparse
from datetime import datetime,timezone,timedelta
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote
HERE=Path(__file__).resolve().parent
AUDIT=HERE.parents[1]
sys.path.insert(0,str(AUDIT))
from execution_common import ROOT,BASE,ASSETS,RUN,JOBS,WORK,STAGES,EVAL_STAGES,read,sha,require,write_new,historical,verify_freeze
from supervision import terminal
OUT=AUDIT/'收尾核验'
REVIEW=AUDIT/'工作目录/005-逐条来源审阅'
FREEZE_SHA='e4fb1591613d7bbf3a27c6b9d4bb055b5399809568ee72388f788e75efd0bdf5'


def stages():
    freeze=verify_freeze(WORK/'freeze-v1.json',FREEZE_SHA)
    proofs={};files=0;pids=[]
    for stage in STAGES:
        path=WORK/f'{stage}-verified.json';proof=read(path)
        require(proof['execution_verified'] and proof['process_retired'] and proof['freeze_sha256']==FREEZE_SHA
            and sha(path)==sha(RUN/'ledger'/path.name),'stage proof is not the exact retired receipt')
        name=str(path.relative_to(ROOT));require(historical('HEAD',[name])=={name:sha(path)},'commit every stage proof')
        marker=read(RUN/stage/'process-result.json');pids.append(marker['pid'])
        require(proof['supervised_retirement']==terminal(stage,FREEZE_SHA,marker),'supervised terminal bytes changed')
        require(proof['verifier_sha256']==sha(AUDIT/'verify_execution.py') and marker['completed'],'stage verifier/completion differs')
        manifest=Path(proof['artifact_manifest']);raw=read(manifest)
        require(sha(manifest)==proof['artifact_manifest_sha256'] and all((manifest.parent/n).resolve().is_relative_to(manifest.parent.resolve()) and sha(manifest.parent/n)==v for n,v in raw.items()),'closed raw artifact changed')
        require(set(raw)=={str(p.relative_to(manifest.parent)) for p in manifest.parent.rglob('*') if p.is_file() and p!=manifest},'unexpected extra raw files')
        files+=len(raw);proofs[stage]=proof
    require(len(set(pids))==5,'fresh stage process identities differ')
    rows=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)
    require(not any(int(line.split(',')[0]) in pids for line in rows.splitlines() if line.strip()),'own old stage GPU allocation remains')
    require(sum(proofs[s]['actual_generation_calls'] for s in EVAL_STAGES)==402
        and sum(proofs[s]['additional_probe_generations'] for s in ('train','reload'))==2,'generation budget differs')
    require(all(proofs[s]['causal_input_matching_passed'] and proofs[s]['matched_trial_pairs']==66 for s in ('old_adapter','new_adapter')),'actual paired inputs differ')
    train=proofs['train'];require(train['actual_labeled_train_forwards']==176 and train['actual_labeled_dev_forwards']==44
        and train['optimizer_ids_equal_actual_tensor_order'] and train['actual_train_supervised_tokens']==3856
        and train['actual_dev_supervised_tokens']==1012 and proofs['reload']['independent_max_logit_difference']==0,'actual training/reload evidence differs')
    return freeze,proofs,files


def collect():
    freeze,proofs,files=stages()
    require(not (OUT/'system-evidence.json').exists(),'fresh system collection required')
    old=[];items=0
    for number in range(3,55):
        cycle=BASE.parent/f'cycle-{number:02}';p=cycle/'审计/证据清单.json';manifest=read(p)
        require(all(sha(cycle/n)==v for n,v in manifest.items()),'old sealed file changed')
        items+=len(manifest);old.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'items':len(manifest)})
    p=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json';manifest=read(p)
    require(all(sha(p.parent/n)==v for n,v in manifest.items()),'migration seal changed')
    items+=len(manifest);old.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'items':len(manifest)})
    require(len(old)==53 and items==12539,'old seal totals differ')
    regression=read(BASE.parent/'cycle-53/审计/工作目录/004-当前软件回归/python-first-binding.json')
    require(len(regression['source_git_sha256'])==494 and all(sha(ROOT/n)==v for n,v in regression['source_git_sha256'].items()),'C53 tested software source changed')
    aliases=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    require(len(aliases)==9 and all(row['valid'] for row in aliases),'central asset aliases invalid')
    comparison=read(REVIEW/'comparison-v1.json')
    require(comparison['verified'] and comparison['reviewed_total']==198 and comparison['matched_trial_pairs']==132
        and all(sha(REVIEW/f'{s}-review-v1.json')==v for s,v in comparison['review_sha256'].items()),'complete source/span review missing')
    spec=importlib.util.spec_from_file_location('c55_review_independent_recheck',REVIEW/'review_evidence.py');review=importlib.util.module_from_spec(spec);spec.loader.exec_module(review)
    require(comparison['validator_sha256']==sha(Path(review.__file__)) and {s:review.validate(read(REVIEW/f'{s}-review-v1.json'),s) for s in EVAL_STAGES}==comparison['phase_summary'],'review provenance/counts changed')
    adapter={str(p.relative_to(RUN/'adapter')):sha(p) for p in (RUN/'adapter').rglob('*') if p.is_file()}
    write_new(OUT/'adapter-files.json',adapter)
    fault=read(AUDIT/'工作目录/006-托管故障补充审计/parent-death-v1.json')
    require(fault['supervisor_dead_child_still_alive'] and fault['fixture_child_cleaned'] and all(sha(Path(fault['external_root'])/n)==v for n,v in fault['external_sha256'].items()),'parent-death CPU fault/cleanup evidence changed')
    system={'verified':True,'scope':'five real isolated C55 stages and same-agent source review;not human/physical/general approval',
        'collector_sha256':sha(Path(__file__)),'freeze_sha256':FREEZE_SHA,'frozen_source_inputs':len(freeze['sha256']),
        'external_frozen_inputs':len(freeze['external_sha256']),'stage_raw_manifest_items':files,'adapter_files':len(adapter),
        'actual_generations':404,'actual_Avatar_trials':198,'actual_SQL_reconstructed':396,'optimizer_steps':44,
        'actual_labeled_train_forwards':176,'actual_labeled_dev_forwards':44,'train_supervised_tokens':3856,'dev_supervised_tokens':1012,
        'probe_direct_forwards':2,'fresh_stage_processes':5,'actual_wait_codes':[0]*5,'matched_actual_pairs':132,
        'actual_reload_max_logit_difference':0.0,'C54_prior_completed_generations':28,'C54_prior_incomplete_boundary_entries':1,
        'combined_completed_generations':432,'combined_boundary_entries':433,'old_seals':old,'old_items':items,
        'historical_Python_passed':2548,'historical_Python_skipped':1,'historical_software_inputs_unchanged':494,'new_full_suite_run':False,
        'new_targeted_existing_tests_passed':26,'asset_aliases':9,'phase_summary':comparison['phase_summary'],
        'local_gain_gate_passed':comparison['local_gain_gate_passed'],'candidate_isolated':True,'default_changed':False,
        'issues_limited_closed':[1,4],'issues_open':[2,3],'parent_death_orphan_fault_verified':True,
        'human_physical_general_or_generative_leap_approved':False}
    write_new(OUT/'system-evidence.json',system)
    render(system)


def render(system):
    source=BASE.parent/'cycle-50/审计/render_report.py';spec=importlib.util.spec_from_file_location('c55_pure_renderer',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    link=lambda label,p:(label,os.path.relpath(p,AUDIT))
    phase=system['phase_summary'];comparisons=[]
    for name in EVAL_STAGES:
        d=phase[name];comparisons.append([name,f"完成{d['unsupported_actual_external_completion']} / 承诺{d['unsupported_external_promise']} / 进行{d['unsupported_external_in_progress']}；18外部联合{d['affected_external_requests']}；草稿/小说{d['draft_preserved']}/{d['fiction_preserved']}",f"状态{d['state_error']} / 时间{d['time_error']} / 人类{d['human_error']} / 能力{d['capability_error']} / 歧义{d['ambiguity']}；探索含尝试联合{d['exploratory_external_attempt_inclusive_affected']}"])
    gain='通过该开发集局部收益门槛' if system['local_gain_gate_passed'] else '未通过该开发集局部收益门槛'
    sections=[{'title':'结论与范围','paragraphs':[
        'C55完成新登记的基座/旧适配/训练/独立重载/新适配五阶段，404次真实generate、198个Avatar试次、396份SQL重建及44个优化步；'+gain+'，候选保持隔离，默认产品不自动启用。',
        '实际训练176/44带labels前向各一次，由真实张量映射源ID并与44步顺序/监督/损失核平；保存重载logits最大差0。独立托管正常流程得到五个实际wait0回执，但补充CPU硬杀监督器复现子任务残留，仍有开放问题。',
        '22个题是已知11类开发题；3重复不增加独立题数，C54已有13题部分实测。198回复由同一代理逐条来源/span审阅，验证器只核来源/覆盖/计数，不等于独立人类语义真值或总体代际跃迁。'],
        'links':[link('系统原始复核',OUT/'system-evidence.json'),link('冻结534源及111外部绑定',WORK/'freeze-v1.json'),link('完整来源/span计数',REVIEW/'comparison-v1.json')]},
    {'title':'完整执行证据','table':(['阶段','实际量','独立验证与终态'],[
        ['base','134generate / 66试次 / 132SQL','真实wait0；BF16/UUID/输入输出及原料SHA'],
        ['old_adapter','134generate / 66试次 / 132SQL','66对消息/token/analysis同base；仅reply启用LoRA；wait0'],
        ['train','44步；176训练+44开发实际张量；1generate+1直接forward','3856/1012监督；ID/顺序/损失一致；144保存张量；wait0'],
        ['reload','1generate+1直接forward；0额外训练','独立进程保存重载文本相同、logits差0；wait0'],
        ['new_adapter','134generate / 66试次 / 132SQL','另66对输入同base；实际reply LoRA；wait0']]),
        'paragraphs':['共五个实际新进程及冻结执行路径核验；probe直接forward和176/44带labels前向与generate分列，不声称拦截所有内部自回归forward。训练采证CPU拷贝/IO计入采集时间，不能当纯推理吞吐。',
            '本轮新404完成生成加C54旧28完成，合432；C54另1未完成入口仍保留，合433入口，不从历史成本中删去中断。原C54退出码保持未知，不补写成功。'],
        'links':[link('实际训练证明',WORK/'train-verified.json'),link('独立重载证明',WORK/'reload-verified.json'),link('新适配66配对证明',WORK/'new_adapter-verified.json'),link('闭合优化步前缀',AUDIT/'工作目录/007-训练步段采证/through-44/verification.json')]},
    {'title':'自然回复来源审阅','table':(['臂','主外部错误与原句保留','辅助问题条数'],comparisons),
        'paragraphs':['主指标为无来源的外部实际完成/未来承诺/进行中断言，外部联合按18试次去重；辅助每类每条计一次，可跨类别重叠。声称“已尝试联系”另设探索轴，不回写冻结主标记。小说/草稿含“已发送”不自动判成现实动作。',
            '基座虚构已发送邮件、旧适配伪造sms_delivery历史查询和手机号均有原文/真实工具空列表/SQL依据。历史“不可信资料”包装不能作为真实来源。时间问题区分due、实际observed_at和未知修改时刻；没有要求模型知道读后独立actor的隐藏变更。',
            '目标替换同时改变措辞/监督token分布与数量；旧训练步顺序未观察，不把三臂结果单独归因于多样性标量。dev loss是材料指标，不能替代行为门槛。'],
        'links':[link('基座66回复',REVIEW/'base-review-v1.json'),link('旧适配66回复',REVIEW/'old_adapter-review-v1.json'),link('新适配66回复',REVIEW/'new_adapter-review-v1.json'),link('审阅规则及探索边界',REVIEW/'审阅规则.md')]},
    {'title':'系统审计与开放问题','table':(['问题','状态','证据与后续'],[
        ['001 独立任务托管正常流程','限定关闭','26定向测试+5真实CPU控制+5真实GPU阶段wait0；不涵盖硬杀监督器'],
        ['002 监督器硬终止子任务残留','OPEN / P1','CPU SIGKILL后原子任务仍活，精确清理且无关对照存活；下轮父死亡内核保护/竞态控制'],
        ['003 自然回复无来源操作/查询','OPEN / P1','保留本轮主/辅助计数，候选隔离；后续新登记当前能力/证据契约机制对照'],
        ['004 C53-002实际训练采证缺口','限定关闭','176/44实际输入/labels身份、44步监督/损失、独立重载；不意味着数据覆盖或语义通过']]),
        'paragraphs':[f"53旧封存/12539项、9集中资产入口保持。本轮阶段原始manifest核{system['stage_raw_manifest_items']}项，adapter目录{system['adapter_files']}文件另存SHA。C53完整Python2548通过/1跳过的494软件输入保持，本轮复用而未重跑完整套件；新增现有托管定向测试26通过和实际CLI/生命周期控制单列。",
            'C53材料覆盖、C19一般语义、独立人评、真人/物理设备、中文口型与多日完整闭环仍开放。P0完整保留失败和候选隔离；P1先修监督器硬终止资源退役，再以新协议推进来源/能力契约；P2扩展未见材料与人类/设备全链路验收。'],
        'links':[link('硬终止CPU原料',AUDIT/'工作目录/006-托管故障补充审计/parent-death-v1.json'),link('过程进展',BASE/'进展.md'),link('执行断点',BASE/'执行断点.md'),link('远期验收路线',BASE.parent/'远期目标与验收路线.md')]}]
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    style=BASE.parent/'cycle-53/审计/工作目录/006-报告显示修复/report-style-v2.html.txt'
    meta=m.render(AUDIT,'C55 目标表达对照与任务托管系统审计报告',stamp+' · 源 '+head[:12],gain+'；候选隔离，存在开放问题',sections,style)
    meta.update(builder_sha256=sha(Path(__file__)),system_sha256=sha(OUT/'system-evidence.json'),
        MD_sha256=sha(AUDIT/'系统审计与推进报告.md'),HTML_sha256=sha(AUDIT/'系统审计与推进报告.html'),style_sha256=sha(style))
    write_new(OUT/'report-render-metadata.json',meta)
    print('C55 report built',meta['tables'],'tables',meta['links'],'links;local gain',system['local_gain_gate_passed'])


def check():
    stages();meta=read(OUT/'report-render-metadata.json');browser=read(OUT/'report-browser.json')
    require(meta['builder_sha256']==sha(Path(__file__)) and meta['system_sha256']==sha(OUT/'system-evidence.json')
        and meta['MD_sha256']==sha(AUDIT/'系统审计与推进报告.md') and meta['HTML_sha256']==sha(AUDIT/'系统审计与推进报告.html'),'report bytes changed')
    require(browser['completed'] and not browser['errors'] and browser['reportSha256']==meta['HTML_sha256']
        and browser['scriptSha256']==sha(AUDIT/'preview_report.mjs') and [v['viewport']['width'] for v in browser['views']]==[1440,390],'browser source/views differ')
    require(all(not v['overflow'] and v['tableCount']==meta['tables'] and len(v['links'])==meta['links']
        and all(t['lastCellReadable'] for t in v['horizontalTables']) and sha(Path(v['screenshot']))==v['screenshotSha256'] for v in browser['views']),'display/link evidence differs')
    links=[]
    for p in list(BASE.rglob('*.md'))+[ROOT/'AGENTS.md',ROOT/'README.md']:
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',p.read_text()):
            target=raw.split('#',1)[0].strip('<>')
            if target and not re.match('[a-z]+://',target):require((p.parent/unquote(target)).resolve().is_file(),'broken MD link '+str(p)+':'+target);links.append(raw)
    authors=subprocess.check_output(['git','log','043829ff..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines()
    require(set(authors)=={'spinner-bot <langxibielangle@qq.com>'},'author identity differs')
    files={str(p.relative_to(ROOT)):sha(p) for p in BASE.rglob('*') if p.is_file()}
    require(historical('HEAD',files)==files,'commit C55 report and progress before closeout')
    write_new(OUT/'closeout.json',{'verified':True,'verifier_sha256':sha(Path(__file__)),
        'MD_links_checked':len(links),'report_links':meta['links'],'tables':meta['tables'],'views':[1440,390],
        'actual_generations':404,'actual_trials':198,'matched_actual_pairs':132,'optimizer_steps':44,
        'issues_limited_closed':[1,4],'issues_open':[2,3],'default_activation_authorized':False})
    print('C55 closeout',len(links),'MD links;',meta['links'],'HTML links;2 views;candidate isolated')


def seal():
    require(read(OUT/'closeout.json')['verified'] and not (AUDIT/'证据清单.json').exists(),'verified closeout and fresh seal required')
    require(not subprocess.check_output(['git','status','--porcelain','--',str(BASE)],cwd=ROOT),'commit all C55 files before seal')
    files={str(p.relative_to(BASE)):sha(p) for p in sorted(BASE.rglob('*')) if p.is_file()}
    require(not any('__pycache__' in n for n in files),'bytecode belongs in centralized assets')
    bound={str((BASE/n).relative_to(ROOT)):v for n,v in files.items()}
    require(historical('HEAD',bound)==bound,'seal requires committed bytes')
    write_new(AUDIT/'证据清单.json',files)
    print('C55 sealed',len(files),'files;SHA',sha(AUDIT/'证据清单.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['collect','check','seal']);globals()[p.parse_args().mode]()

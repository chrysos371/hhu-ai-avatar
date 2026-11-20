"""Report, verify and seal C54 as INCOMPLETE; never restart model work."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime,timezone,timedelta
from urllib.parse import unquote
ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
BASE=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-54'
AUDIT=BASE/'审计';HERE=Path(__file__).resolve().parent;OUT=AUDIT/'收尾核验'
sys.path.insert(0,str(AUDIT))
from execution_common import RUN,WORK,read,sha,write_new,historical,require


def original_bytes():
    r=read(HERE/'retirement-v1.json');require(r['verified'] and r['experiment_retired_incomplete'],'incomplete retirement proof required')
    require(r['verifier_sha256']==sha(HERE/'retire_interrupted_base.py'),'original auditor changed')
    f=read(WORK/'freeze-v1.json');require(sha(WORK/'freeze-v1.json')==r['freeze_sha256'],'freeze changed')
    require(all(sha(ROOT/n)==v for n,v in f['sha256'].items()) and historical(f['source_ref'],f['sha256'])==f['sha256'],'507 frozen input bytes changed')
    manifest=Path(r['external_raw_manifest']);require(sha(manifest)==r['external_raw_manifest_sha256'],'raw manifest changed')
    files=read(manifest);require(len(files)==100 and all(sha(RUN/n)==v for n,v in files.items()),'partial raw bytes changed')
    require(not (RUN/'base/process-result.json').exists() and not (RUN/'ledger/base-verified.json').exists(),'partial run was overwritten as complete')
    require(sorted(p.name for p in (RUN/'ledger').glob('*-start.json'))==['base-start.json'],'later stages attempted')
    marker=read(RUN/'ledger/base-start.json');proc=Path(f'/proc/{marker["pid"]}/stat')
    require(not proc.exists() or proc.read_text().split()[21]!=marker['start_ticks'],'original worker remains live')
    return r


def build():
    r=original_bytes();require(not (OUT/'system-evidence.json').exists(),'fresh report collection required')
    old=[];items=0
    for n in range(3,54):
        cycle=BASE.parent/f'cycle-{n:02}';p=cycle/'审计/证据清单.json';s=read(p)
        require(all(sha(cycle/k)==v for k,v in s.items()),'prior sealed file changed')
        items+=len(s);old.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'items':len(s)})
    p=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json';s=read(p)
    require(all(sha(p.parent/k)==v for k,v in s.items()),'migration seal changed');items+=len(s);old.append({'path':str(p.relative_to(ROOT)),'sha256':sha(p),'items':len(s)})
    require(len(old)==52 and items==12470,'prior seal totals differ')
    regression=read(BASE.parent/'cycle-53/审计/工作目录/004-当前软件回归/python-first-binding.json')
    require(len(regression['source_git_sha256'])==494 and all(sha(ROOT/k)==v for k,v in regression['source_git_sha256'].items()),'C53 software inputs changed')
    aliases=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True));require(len(aliases)==9 and all(x['valid'] for x in aliases),'asset aliases invalid')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    system={'verified':True,'scope':'C54 preparation and interrupted partial execution audit; not completed experiment or model-quality verdict',
        'head':head,'collector_sha256':sha(Path(__file__)),'retirement_sha256':sha(HERE/'retirement-v1.json'),
        'frozen_source_inputs':507,'raw_files_verified':100,'complete_generations':28,'incomplete_boundary_entries':1,
        'captured_generate_boundaries':29,'complete_Avatar_trials':13,'SQL_snapshots':27,'training_steps':0,
        'worker_exit_code':None,'exit_code_unknown':True,'experiment_complete':False,'model_quality_approved':False,
        'old_seals':old,'old_items':items,'historical_Python_passed':2548,'historical_Python_skipped':1,
        'historical_software_inputs_unchanged':494,'new_full_suite_run':False,'asset_aliases':9,'issues_open':1,'default_changed':False}
    write_new(OUT/'system-evidence.json',system)
    renderer=BASE.parent/'cycle-50/审计/render_report.py';spec=importlib.util.spec_from_file_location('c50_pure_renderer_c54_close',renderer);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    def link(label,p):return label,os.path.relpath(p,AUDIT)
    sections=[{'title':'结论：未完成实验退役','paragraphs':[
        'C54完成目标表达替换的CPU材料准备、真实分词与新题路由演练，随后启动过一次BF16基座实测。会话外部中断后原worker消失，没有Python终态回执；完整基线和三臂对照均未完成，原阶段退役，不重试或推进依赖阶段。',
        '实际留下28份完成生成结果（2预热+26正式）、第29个未完成分析入口、13完整Avatar试次和27份SQL。100原始文件及507冻结输入保持；退出码未知，不能补写为0或推断某个信号。部分数据不能支持适配增益、模型退化或代际跃迁结论。'],
        'links':[link('原始退役核验',HERE/'retirement-v1.json'),link('恢复后字节复核',HERE/'resume-byte-recheck-v1.json'),link('统一冻结',WORK/'freeze-v1.json')]},
    {'title':'准备阶段实测','table':(['项目','实测','边界'],[
        ['材料','176训练/44开发；220 prompt字节和token前缀相同','复用旧SDK上下文，仅替换最终脚本目标'],
        ['目标覆盖','训练81/开发41种，共享1种精确草稿','122 split-variant/121不同目标；同代理来源审阅'],
        ['监督token含EOS','3856/1012，旧3936/984','表达方案同时改变token分布，不是单标量多样性因果'],
        ['来源与隔离','220对/4身份故障/44保护字段拒绝','当前实际加载接受，不是人类语义批准'],
        ['新题CPU演练','66 SDK试次/132SQL/138脚本接口','201原料/44 fixture消息对；不是实际adapter层证明'],
        ['训练前向采证器','CPU embedding模块2正向/1反传/7故障','0优化步；真实CUDA训练未执行'],
        ['执行门禁','4精确正常CLI拒绝+help；合成220行/44步/7损坏','JSON算法检查不是硬件采证']]),
        'links':[link('材料导出',AUDIT/'工作目录/001-目标表达对照/data-export-v1.json'),link('独立材料/隔离',AUDIT/'工作目录/002-独立原料与隔离/independent-data-v1.json'),link('真实CPU分词',AUDIT/'工作目录/003-真实分词/target-tokenization-v1.json'),link('新题独立演练',AUDIT/'工作目录/004-新题路由演练/independent-rehearsal-v1.json')]},
    {'title':'实际执行与中断边界','table':(['项目','实际记录','未获证明'],[
        ['GPU身份','启动时空闲GPU2，物理UUID与实际分配一致','不代表恢复时GPU2仍空闲'],
        ['完成生成','28份结果，独立重构输入/输出','不是404次计划全部完成'],
        ['未完成入口','第29条 analysis：c54-historical_cancelled-2','不知道原generate是否完成；不得计为成功'],
        ['试次与SQL','13完整试次/26重建SQL，另1部分查询SQL','未完成第1组22例，不能代替66例基线'],
        ['进程终态','原PID身份不存在、原占用退役','无实际退出码；不伪造终态'],
        ['后续阶段','old_adapter/train/reload/new_adapter均未启动','0新训练步、无新adapter和训练日志实测'],
        ['历史证据','52旧seal/12470项、9集中入口不变','当前复用C53 2548/1及494源字节，未新跑全套']]),
        'paragraphs':['retirement-v1中的goal_active为脚本常量，不能用作暂停/恢复时间状态证据；用户事件和Goal API才是权威。暂停后误启动过一次只读核验，已经退出且未新增模型/训练；原记录不删除。'],
        'links':[link('中断问题001',AUDIT/'问题单/001-会话中断后真实阶段缺少独立终态托管.md'),link('系统复核',OUT/'system-evidence.json')]},
    {'title':'推进方向','paragraphs':[
        'P0保留本轮全部部分结果和失败，不重跑C54，不从不足试次选取有利结论。旧C52失败adapter和默认产品保持原状态；C53-002实际训练样本采证缺口仍开放。',
        'P1在新周期修复独立任务监督和终态回执，先用真实短命成功/失败子进程及父启动器退出控制验证；无自动重试、无整轮墙钟截止。完成后另登记完整对照，旧13例明确为已执行开发诊断，所有历史调用单列。',
        'P2完成新版本真实实验、来源/span审阅、系统审计与报告后再循环；一般语义、独立人评、真人/物理设备、中文口型与多日全链路验收仍未批准。'],
        'links':[link('过程进展',BASE/'进展.md'),link('退役接续说明',BASE/'准备检查点与真实执行接续.md'),link('远期路线',BASE.parent/'远期目标与验收路线.md')]}]
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    style=BASE.parent/'cycle-53/审计/工作目录/006-报告显示修复/report-style-v2.html.txt'
    meta=m.render(AUDIT,'C54 中断实验系统审计报告',stamp+' · 源 '+head[:12],'实验未完成并退役；无适配收益或质量批准',sections,style)
    meta.update(builder_sha256=sha(Path(__file__)),system_sha256=sha(OUT/'system-evidence.json'),
        MD_sha256=sha(AUDIT/'系统审计与推进报告.md'),HTML_sha256=sha(AUDIT/'系统审计与推进报告.html'),style_sha256=sha(style))
    write_new(OUT/'report-render-metadata.json',meta);print('C54 incomplete report built;',meta['tables'],'tables',meta['links'],'links;no model work')


def check():
    original_bytes();meta=read(OUT/'report-render-metadata.json');browser=read(OUT/'report-browser.json')
    require(meta['builder_sha256']==sha(Path(__file__)) and meta['system_sha256']==sha(OUT/'system-evidence.json'),'report source changed')
    require(meta['MD_sha256']==sha(AUDIT/'系统审计与推进报告.md') and meta['HTML_sha256']==sha(AUDIT/'系统审计与推进报告.html'),'report changed')
    require(browser['completed'] and not browser['errors'] and browser['reportSha256']==meta['HTML_sha256'],'browser check failed')
    require(browser['scriptSha256']==sha(AUDIT/'preview_report.mjs') and [v['viewport']['width'] for v in browser['views']]==[1440,390],'browser source/viewports changed')
    require(all(not v['overflow'] and v['tableCount']==2 and len(v['links'])==meta['links'] and all(t['lastCellReadable'] for t in v['horizontalTables']) and sha(Path(v['screenshot']))==v['screenshotSha256'] for v in browser['views']),'display/link counts differ')
    links=[]
    for p in list(BASE.rglob('*.md'))+[ROOT/'AGENTS.md',ROOT/'README.md']:
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',p.read_text()):
            target=raw.split('#',1)[0].strip('<>')
            if target and not re.match('[a-z]+://',target):require((p.parent/unquote(target)).resolve().is_file(),'broken link '+str(p)+':'+target);links.append(raw)
    authors=subprocess.check_output(['git','log','0213bf07..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines();require(set(authors)=={'spinner-bot <langxibielangle@qq.com>'},'author differs')
    files={str(p.relative_to(ROOT)):sha(p) for p in BASE.rglob('*') if p.is_file()};require(historical('HEAD',files)==files,'commit C54 files before closeout')
    write_new(OUT/'closeout.json',{'verified':True,'scope':'incomplete experiment report/display/byte closure only','verifier_sha256':sha(Path(__file__)),
        'MD_links_checked':len(links),'report_links':meta['links'],'tables':2,'views':[1440,390],'original_C54_retired_incomplete':True,
        'completed_generations':28,'captured_generate_boundaries':29,'completed_trials':13,'exit_code_unknown':True,'issues_open':1,'experiment_complete':False})
    print('C54 closeout',len(links),'MD links;',meta['links'],'HTML links;2views;INCOMPLETE retained')


def seal():
    require(read(OUT/'closeout.json')['verified'] and not (AUDIT/'证据清单.json').exists(),'closeout required / already sealed')
    require(not subprocess.check_output(['git','status','--porcelain','--',str(BASE)],cwd=ROOT),'commit all C54 files first')
    files={str(p.relative_to(BASE)):sha(p) for p in sorted(BASE.rglob('*')) if p.is_file()}
    require(not any('__pycache__' in n for n in files),'bytecode outside repo required')
    require(historical('HEAD',{str((BASE/n).relative_to(ROOT)):v for n,v in files.items()})=={str((BASE/n).relative_to(ROOT)):v for n,v in files.items()},'uncommitted bytes')
    write_new(AUDIT/'证据清单.json',files);print('C54 sealed',len(files),'files;SHA',sha(AUDIT/'证据清单.json'),'INCOMPLETE,not quality approval')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['build','check','seal']);globals()[p.parse_args().mode]()

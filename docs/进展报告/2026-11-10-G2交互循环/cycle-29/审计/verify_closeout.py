"""Final evidence/source/docs/seal audit without rerunning retired experiments."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from context_baseline_common import ROOT,BASE,digest


def read(path):return json.loads(path.read_text())
def verify():
    old=[]
    for manifest in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(manifest.parents[1].name.split('-')[1])>28:continue
        hashes=read(manifest)
        for name,value in hashes.items():assert digest(manifest.parents[1]/name)==value
        old.append({'cycle':manifest.parents[1].name,'items':len(hashes),'manifest_sha256':digest(manifest)})
    assert len(old)==26
    stage=BASE/'审计/工作目录/001-上下文重启现状/阶段A证据清单.json';metadata=read(stage);assert metadata['base']=='repository' and len(metadata['sha256'])==31
    for name,value in metadata['sha256'].items():assert digest(ROOT/name)==value
    full=read(BASE/'审计/工作目录/003-独立进程故障边界/full-python-unverified-fix-binding.json')
    assert full['completed'] and full['exit_code']==0 and full['source_unchanged'] and len(full['source_sha256'])==552
    for name,value in full['source_sha256'].items():
        assert digest(ROOT/name)==value
        assert sha256(subprocess.check_output(['git','show',full['head']+':'+name],cwd=ROOT)).hexdigest()==value
    browser=read(BASE/'审计/工作目录/005-浏览器回归/default-browser-binding.json');assert browser['exit_code']==0 and browser['runtime_matches'] and browser['source_unchanged']
    for name,value in browser['source_sha256'].items():assert digest(ROOT/name)==value
    runtime_path=BASE/'审计/工作目录/005-浏览器回归/browser-runtime.json';assert digest(runtime_path)==browser['runtime_sha256']
    bindings=[]
    for freeze in ('context-continuity-after','context-fault-controls-v3','context-transaction-interleaving'):
        fp=ROOT/'evals/interaction/cycle-29'/(freeze+'-freeze.json');rp=fp.with_name(freeze+'-retirement.json');frozen=read(fp);retired=read(rp)
        assert retired['status']=='completed_retired' and retired['freeze_sha256']==digest(fp)
        current=all(digest(ROOT/n)==v for n,v in frozen['sha256'].items())
        if freeze!='context-continuity-after':assert current
        bindings.append({'freeze':freeze,'inputs':len(frozen['sha256']),'current_inputs_match':current,'retired':True})
    proofs=['审计/工作目录/002-有界已完成对话恢复/修后OS核验.json','审计/工作目录/003-独立进程故障边界/独立八场景核验.json','审计/工作目录/004-上下文读取隐私事务交错/独立事务交错核验.json']
    for name in proofs:assert read(BASE/name)['verified']
    qa=read(BASE/'审计/收尾核验/report-browser.json');assert qa['completed'] and not qa['errors'] and qa['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
    assert [r['viewport']['width'] for r in qa['views']]==[1440,390]
    for row in qa['views']:assert row['tableCount']==4 and not row['overflow'] and len(row['links'])==28 and all(l['exists'] for l in row['links'])
    assert all(t['lastCellReadable'] for t in qa['views'][1]['horizontalTables'])
    docs=['README.md','docs/backend.md','docs/记忆工作台与提醒.md','docs/进展报告/2026-11-10-G2交互循环/远期目标与验收路线.md']
    links=[]
    for name in docs:
        p=ROOT/name
        for href in re.findall(r'\[[^\]]+\]\(([^)]+)\)',p.read_text()):
            if '://' in href or href.startswith('#'):continue
            target=(p.parent/href.split('#')[0]).resolve();assert target.exists(),(name,href)
            links.append({'document':name,'href':href,'exists':True})
    source_docs={name:digest(ROOT/name) for name in docs}
    assert subprocess.check_output(['git','config','user.name'],cwd=ROOT,text=True).strip()=='spinner-bot'
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'old_immutable_seals':old,'stage_a_items':31,'stage_a_manifest_sha256':digest(stage),
        'current_full_python_head':full['head'],'full_python_inputs_current_and_historical_git':552,'browser_inputs_current':len(browser['source_sha256']),
        'retired_execution_bindings':bindings,'report_views':[1440,390],'report_tables':4,'report_local_links':28,'report_visual_inspection':'desktop, mobile viewport and rightmost table screenshot inspected by same agent',
        'public_document_sha256':source_docs,'public_document_local_links':links,'actual_llm_or_gpu_this_cycle':False,
        'general_semantics_or_physical_device_or_multiday_approved':False}
    out=BASE/'审计/收尾核验/系统封存前核验.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Verified26 prior immutable seals,31 stage-A entries,552 current/historical full-test inputs,190 browser inputs,MD/HTML/public links and source retirements.')


if __name__=='__main__':verify()

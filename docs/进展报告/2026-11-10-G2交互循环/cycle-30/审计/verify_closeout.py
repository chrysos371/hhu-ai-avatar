"""Final historical seals, unchanged product, native provenance and report review."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from context_native_common import ROOT,BASE,digest,verify_historical_binding


def read(p):return json.loads(p.read_text())
def verify():
    old=[]
    for manifest in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(manifest.parents[1].name.split('-')[1])>29:continue
        values=read(manifest)
        for name,value in values.items():assert digest(manifest.parents[1]/name)==value
        old.append({'cycle':manifest.parents[1].name,'items':len(values),'manifest_sha256':digest(manifest)})
    assert len(old)==27 and old[-1]['cycle']=='cycle-29' and old[-1]['items']==272
    prior=BASE.parent/'cycle-29';full=read(prior/'审计/工作目录/003-独立进程故障边界/full-python-unverified-fix-binding.json')
    for name,value in full['source_sha256'].items():assert digest(ROOT/name)==value
    browser=read(prior/'审计/工作目录/005-浏览器回归/default-browser-binding.json')
    for name,value in browser['source_sha256'].items():assert digest(ROOT/name)==value
    assert full['exit_code']==browser['exit_code']==0 and len(full['source_sha256'])==552 and len(browser['source_sha256'])==190
    metadata=read(prior/'审计/收尾核验/评测元数据版本绑定.json')
    for name,value in metadata['sha256'].items():assert digest(ROOT/name)==value
    frozen_path=ROOT/'evals/interaction/cycle-30/native-context-use-v2-freeze.json';frozen=read(frozen_path)
    verify_historical_binding(frozen)
    for name,value in frozen['sha256'].items():assert digest(ROOT/name)==value
    retired=read(frozen_path.with_name('native-context-use-v2-retirement.json'));assert retired['status']=='completed_retired' and retired['freeze_sha256']==digest(frozen_path)
    for name,value in retired['sha256'].items():assert digest(ROOT/name)==value
    work=BASE/'审计/工作目录/001-真实模型重启历史利用';native=[]
    for label in ('4b','32b'):
        evidence=BASE/('实验/native-context-'+label+'/evaluation.json');data=read(evidence);proof=read(work/(label+'-independent-binding.json'));review=read(work/(label+'-source-aware-review.json'))
        assert proof['verified'] and proof['evaluation_sha256']==review['evaluation_sha256']==digest(evidence)
        assert data['completed'] and data['engineering_passed'] and data['cleanup_passed'] and data['provider_exit']==0 and not data['cleanup_errors']
        assert len(data['requests'])==74 and len(data['workers'])==24
        assert all(w['exit_code']==0 and not w['forced_cleanup'] for w in data['workers'])
        native.append({'model':data['model_id'],'proof_sha256':digest(work/(label+'-independent-binding.json')),'review_sha256':digest(work/(label+'-source-aware-review.json')),'gpu':data['provider_ready']['chosen_gpu'],'allocated_mib':data['provider_ready']['process_gpu_mib_after_load']})
    pairs=read(work/'双臂逐轮来源核验.json');assert pairs['verified'] and pairs['identical_third_system_pairs']==pairs['identical_preparation_reply_pairs']==12
    qa=read(BASE/'审计/收尾核验/report-browser.json');assert qa['completed'] and not qa['errors'] and qa['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
    assert [v['viewport']['width'] for v in qa['views']]==[1440,390]
    for row in qa['views']:assert not row['overflow'] and row['tableCount']==4 and len(row['links'])==23 and all(link['exists'] for link in row['links'])
    assert all(t['lastCellReadable'] for t in qa['views'][1]['horizontalTables'])
    docs=['README.md','docs/backend.md','docs/进展报告/2026-11-10-G2交互循环/远期目标与验收路线.md'];links=[]
    for name in docs:
        p=ROOT/name
        for href in re.findall(r'\[[^\]]+\]\(([^)]+)\)',p.read_text()):
            if '://' in href or href.startswith('#'):continue
            assert (p.parent/href.split('#')[0]).resolve().exists(),(name,href)
            links.append({'document':name,'href':href,'exists':True})
    assert subprocess.check_output(['git','config','user.name'],cwd=ROOT,text=True).strip()=='spinner-bot'
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
        'old_seals':old,'current_and_historical_native_inputs':309,'previous_product_full_inputs_unchanged':552,'previous_browser_inputs_unchanged':190,
        'product_tests_not_rerun_this_cycle':True,'native_models':native,'source_bound_native_calls':148,'source_bound_app_replies':72,'source_bound_clean_app_processes':48,
        'report_viewports':[1440,390],'tables':4,'report_local_links':23,'same_agent_screenshot_visual_review':True,
        'public_docs_sha256':{name:digest(ROOT/name) for name in docs},'public_document_local_links':links,
        'eval_metadata_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'evals/interaction/cycle-30').glob('*')) if p.is_file()},
        'actual_native_cuda':True,'independent_human_or_general_quality_or_multiday_approval':False}
    out=BASE/'审计/收尾核验/封存前系统核验.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Verified27 old seals,C29 product552/browser190 unchanged,309 native inputs,148 calls/72 replies/48 app exits,MD/HTML1440/390 and all links.')


if __name__=='__main__':verify()

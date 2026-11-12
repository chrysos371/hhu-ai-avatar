"""Final unchanged-product/seal/native-claim/report provenance audit."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from analysis_cost_common import ROOT,BASE,digest,verify_historical_binding


def read(p):return json.loads(p.read_text())
def verify():
    old=[]
    for manifest in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(manifest.parents[1].name.split('-')[1])>30:continue
        entries=read(manifest)
        for name,value in entries.items():assert digest(manifest.parents[1]/name)==value
        old.append({'cycle':manifest.parents[1].name,'items':len(entries),'manifest_sha256':digest(manifest)})
    assert len(old)==28 and old[-1]['cycle']=='cycle-30' and old[-1]['items']==192
    prior=BASE.parent/'cycle-29';full=read(prior/'审计/工作目录/003-独立进程故障边界/full-python-unverified-fix-binding.json');browser=read(prior/'审计/工作目录/005-浏览器回归/default-browser-binding.json')
    for binding in (full,browser):
        assert binding['exit_code']==0 and binding['source_unchanged']
        for name,value in binding['source_sha256'].items():assert digest(ROOT/name)==value
    assert len(full['source_sha256'])==552 and len(browser['source_sha256'])==190
    fp=ROOT/'evals/interaction/cycle-31/readonly-analysis-cost-freeze.json';frozen=read(fp);verify_historical_binding(frozen)
    for name,value in frozen['sha256'].items():assert digest(ROOT/name)==value
    assert len(frozen['sha256'])==325
    retired=read(fp.with_name('readonly-analysis-cost-retirement.json'));assert retired['status']=='completed_retired_with_failed_promotion_gate' and retired['freeze_sha256']==digest(fp)
    assert retired['production_activation_authorized'] is False and retired['4b_preregistered_raw_reply_gate'] is True and retired['32b_preregistered_raw_reply_gate'] is False
    for name,value in retired['sha256'].items():assert digest(ROOT/name)==value
    work=BASE/'审计/工作目录/001-只读分析路由保护';versions=read(work/'cpu-control-versions.json')
    for row in versions['controls']:
        assert digest(ROOT/row['evidence'])==row['evidence_sha256'] and digest(ROOT/row['helper'])==row['helper_sha256']
        assert sha256(subprocess.check_output(['git','show',row['helper_git_ref']+':'+row['helper']],cwd=ROOT)).hexdigest()==row['helper_sha256']
        if 'executed_protocol' in row:assert sha256(subprocess.check_output(['git','show',row['executed_protocol_git_ref']+':'+row['executed_protocol']],cwd=ROOT)).hexdigest()==row['executed_protocol_sha256']
    assert versions['candidate_sha256']==digest(BASE/'审计/readonly_analysis_candidate.py')
    native=[]
    for label in ('4b','32b'):
        p=BASE/('实验/readonly-cost-'+label+'/evaluation.json');data=read(p);proof=read(work/(label+'-independent-binding.json'))
        assert proof['verified'] and proof['evaluation_sha256']==digest(p) and data['completed'] and data['engineering_passed'] and data['cleanup_passed']
        assert data['provider_exit']==0 and not data.get('provider_forced_cleanup') and not data['cleanup_errors']
        assert len(data['workers'])==96 and len(data['requests'])==272 and all(w['exit_code']==0 and not w['forced_cleanup'] for w in data['workers'])
        native.append({'model':data['model_id'],'proof_sha256':digest(work/(label+'-independent-binding.json')),'native_calls':272,'app_turns':144,'clean_workers':96,
            'raw_reply_gate':data['comparison']['quality_gate_passed'],'primary_bounded_gate':data['comparison']['bounded_performance_gate_passed'],'gpu':data['provider_ready']['chosen_gpu']})
    combined=read(work/'来源审阅与补审汇总核验.json');assert combined['verified'] and combined['reviewed_spans']==288 and combined['promotion_approved'] is False
    qa=read(BASE/'审计/收尾核验/report-browser.json');assert qa['completed'] and not qa['errors'] and qa['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
    assert [v['viewport']['width'] for v in qa['views']]==[1440,390]
    for row in qa['views']:assert row['tableCount']==4 and not row['overflow'] and len(row['links'])==29 and all(link['exists'] for link in row['links'])
    assert all(table['lastCellReadable'] for table in qa['views'][1]['horizontalTables'])
    docs=['README.md','docs/backend.md','docs/进展报告/2026-11-10-G2交互循环/远期目标与验收路线.md'];links=[]
    for name in docs:
        p=ROOT/name
        for href in re.findall(r'\[[^\]]+\]\(([^)]+)\)',p.read_text()):
            if '://' in href or href.startswith('#'):continue
            assert (p.parent/href.split('#')[0]).resolve().exists(),(name,href);links.append({'document':name,'href':href,'exists':True})
    assert subprocess.check_output(['git','config','user.name'],cwd=ROOT,text=True).strip()=='spinner-bot'
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
        'old_immutable_seals':old,'unchanged_product_full_inputs':552,'unchanged_browser_inputs':190,'product_checks_not_rerun_this_cycle':True,
        'current_and_historical_native_inputs':325,'native_evidence':native,'source_bound_native_calls':544,'source_bound_app_replies':288,'clean_app_processes':192,
        'report_views':[1440,390],'report_tables':4,'report_local_links':29,'same_agent_screenshot_inspection':True,
        'public_docs_sha256':{name:digest(ROOT/name) for name in docs},'public_document_local_links':links,
        'eval_metadata_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'evals/interaction/cycle-31').glob('*')) if p.is_file()},
        'production_promotion_approved':False,'general_semantics_multiday_or_physical_device_approved':False}
    out=BASE/'审计/收尾核验/封存前系统核验.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Verified28 old seals,product552/browser190 unchanged,325 native inputs,544 calls/288 replies/192 exits,CPU historical versions and MD/HTML1440/390;promotion false.')


if __name__=='__main__':verify()

"""Final C33 immutable evidence, native/fault provenance, reports and product audit."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from shared_affect_common import ROOT,BASE,RUNTIME,digest,verify_freeze,verify_historical_binding,verify_backend
from verify_shared_affect import verify as reconstruct


def read(path):return json.loads(path.read_text())
def historical(ref,name,value):assert sha256(subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)).hexdigest()==value,(ref,name)


def main():
    old=[]
    for manifest in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(manifest.parents[1].name.split('-')[1])>32:continue
        entries=read(manifest)
        for name,value in entries.items():assert digest(manifest.parents[1]/name)==value
        old.append({'cycle':manifest.parents[1].name,'items':len(entries),'manifest_sha256':digest(manifest)})
    assert len(old)==30 and old[-1]['items']==93 and old[-1]['manifest_sha256']=='82151051b992f5e284a73cf992dfd5a33154ec44503525477895aaf761b665a9'
    prior=BASE.parent/'cycle-29';full=read(prior/'审计/工作目录/003-独立进程故障边界/full-python-unverified-fix-binding.json');browser=read(prior/'审计/工作目录/005-浏览器回归/default-browser-binding.json')
    for binding in (full,browser):
        assert binding['exit_code']==0 and binding['source_unchanged']
        for name,value in binding['source_sha256'].items():assert digest(ROOT/name)==value
    assert len(full['source_sha256'])==552 and len(browser['source_sha256'])==190
    work=BASE/'审计/工作目录';primary=work/'001-共享历史隐含情绪';freeze=primary/'执行冻结.json';frozen=verify_freeze(freeze,digest(freeze));verify_historical_binding(frozen);assert len(frozen['sha256'])==341
    runtime=verify_backend(ROOT/RUNTIME,frozen['sha256'][RUNTIME]);assert len(runtime['files_sha256'])==54
    retired=read(ROOT/'evals/interaction/cycle-33/implicit-affect-retirement.json');assert retired['status']=='completed_retired_no_default_candidate_promotion' and retired['freeze_sha256']==digest(freeze) and retired['native_calls']==730
    assert retired['candidate_production_activation_authorized'] is False and retired['general_semantics_or_latency_approval'] is False and retired['new_production_forget_invalidation_issue_open'] is True
    for name,value in retired['sha256'].items():assert digest(ROOT/name)==value
    cpu=read(primary/'cpu-control-version.json')
    for name,value in cpu['files_sha256'].items():historical(cpu['source_ref'],name,value)
    assert cpu['evidence_sha256']==digest(primary/'shared-cpu-controls.json') and len(read(primary/'shared-cpu-controls.json')['controls'])==8
    negatives=read(primary/'前置负控/controls.json');assert negatives['passed'] and len(negatives['controls'])==3
    for row in negatives['controls']:assert row['passed'] and row['returncode']!=0
    native=[]
    for label in ('4b','32b'):
        evaluation=BASE/('实验/shared-affect-'+label+'/evaluation.json');proof=reconstruct(evaluation);assert proof==read(primary/(label+'-independent-binding.json'));native.append(proof)
        version=read(primary/('独立复核器执行版本-'+label+'.json'));historical(version['source_ref'],str((BASE/'审计/verify_shared_affect.py').relative_to(ROOT)),version['verifier_sha256']);assert version['evaluation_sha256']==digest(evaluation)
        post=work/'003-角色状态连续性补审';data=read(post/(label+'-posthoc-continuity.json'));version=read(post/('执行版本-'+label+'.json'))
        assert data['evaluation_sha256']==digest(evaluation) and version['evidence_sha256']==digest(post/(label+'-posthoc-continuity.json'))
        historical(version['source_ref'],str((BASE/'审计/analyze_emotion_continuity.py').relative_to(ROOT)),version['helper_sha256'])
        assert data['previous_nonzero_character_pad_groups']==sum(row['previous_character_pad_nonzero'] for row in data['rows'])
        assert data['current_analysis_probe_neutral_user_groups']==sum(row['current_analysis_probe_user_observation']==[0,0] for row in data['rows'])
    assert sum(p['native_calls'] for p in native)==730 and sum(p['app_turns'] for p in native)==384 and sum(p['clean_os_workers'] for p in native)==288
    assert [p['candidate_skips'] for p in native]==[24,18] and [sum(pair['user_observation_changed'] for pair in p['pairs']) for p in native]==[0,6]
    supplemental=read(work/'补审与版本管理独立核验.json');version=read(work/'补审核验程序版本.json');assert supplemental['verified'] and supplemental['individual_group_commits_verified']==96 and version['proof_sha256']==digest(work/'补审与版本管理独立核验.json')
    for name,value in version['files_sha256'].items():historical(version['source_ref'],name,value)
    assert supplemental['controlled_http_submissions']==12 and supplemental['results']==9 and supplemental['cancelled']==3 and supplemental['forget_retention_reproductions']==3 and supplemental['cancel_retention_observations_not_classified_as_contract_failures']==3
    for row in supplemental['fault_rows']:
        path=work/'004-遗忘与取消情绪状态补审/复核SQL'/(str(row['repetition'])+'-'+row['case']+'.sql');assert digest(path)==row['archived_sql_sha256']
    qa=read(BASE/'审计/收尾核验/report-browser.json');metadata=read(BASE/'审计/report-render-metadata.json')
    assert qa['completed'] and not qa['errors'] and qa['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html') and metadata=={'tables':4,'links':25}
    assert [view['viewport']['width'] for view in qa['views']]==[1440,390]
    for view in qa['views']:assert view['tableCount']==4 and not view['overflow'] and len(view['links'])==25 and all(link['exists'] for link in view['links'])
    assert all(table['lastCellReadable'] for table in qa['views'][1]['horizontalTables'])
    docs=[ROOT/'README.md',ROOT/'docs/backend.md',BASE.parent/'远期目标与验收路线.md',ROOT/'AGENTS.md',*sorted((BASE/'审计/问题单').glob('*.md'))];links=[]
    for path in docs:
        for href in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text()):
            if '://' in href or href.startswith('#'):continue
            assert (path.parent/href.split('#')[0]).resolve().exists(),(str(path.relative_to(ROOT)),href);links.append({'document':str(path.relative_to(ROOT)),'href':href,'exists':True})
    authors=subprocess.check_output(['git','log','--format=%an <%ae>','7cbb7b2..HEAD'],cwd=ROOT,text=True).splitlines();assert authors and set(authors)=={'spinner-bot <langxibielangle@qq.com>'}
    current=read(work/'002-工作约定去重/整理前测量.json');text=(ROOT/'AGENTS.md').read_text();assert sha256(text[text.index('## 一、项目是什么'):].encode()).hexdigest()==current['project_reference_section_sha256']
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
        'old_immutable_seals':old,'unchanged_product_full_inputs':552,'unchanged_browser_inputs':190,'product_checks_not_rerun_this_cycle':True,'native_source_inputs':341,'runtime_files':54,
        'native_calls':730,'app_turns':384,'clean_os_workers':288,'shared_preparation_groups':96,'individual_group_commits_verified':96,'owned_provider_exits':2,
        'native_proofs_sha256':{label:digest(primary/(label+'-independent-binding.json')) for label in ('4b','32b')},'preflight_controls_passed':11,'supplementary_http_submissions':12,'supplementary_http_cancelled':3,
        'forget_state_defect_open':True,'cancel_retention_not_claimed_contract_defect':True,'report_views':[1440,390],'report_tables':4,'report_links':25,'same_agent_visual_inspection':True,
        'current_docs_sha256':{str(path.relative_to(ROOT)):digest(path) for path in docs},'local_links':links,'all_current_cycle_authors_verified':True,
        'production_promotion_or_general_semantics_approved':False,'physical_device_or_multiday_approved':False}
    with (BASE/'审计/收尾核验/封存前系统核验.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    print('Verified30 prior seals,552product/190browser unchanged,341 source+54runtime,730native/384app/288OS,96 group commits,11 preflight controls+12 HTTP supplement submissions and report1440/390; forget defect remains open.')


if __name__=='__main__':main()

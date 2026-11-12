"""Seals, unchanged product, historical control versions and final claims."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from state_common import ROOT,BASE,RUNTIME,digest,verify_freeze,verify_historical_binding,verify_backend
from verify_state_replay import verify as reconstruct


def read(path):return json.loads(path.read_text())


def historical(ref,name,value):
    assert sha256(subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)).hexdigest()==value,(ref,name)


def main():
    old=[]
    for manifest in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(manifest.parents[1].name.split('-')[1])>31:continue
        entries=read(manifest)
        for name,value in entries.items():assert digest(manifest.parents[1]/name)==value
        old.append({'cycle':manifest.parents[1].name,'items':len(entries),'manifest_sha256':digest(manifest)})
    assert len(old)==29 and old[-1]['items']==639 and old[-1]['manifest_sha256']=='9539ccebc9dcc5a52b4ac614df07440369fb134a4a22603a32c2611fa86a0f48'
    prior=BASE.parent/'cycle-29';full=read(prior/'审计/工作目录/003-独立进程故障边界/full-python-unverified-fix-binding.json');browser=read(prior/'审计/工作目录/005-浏览器回归/default-browser-binding.json')
    for binding in (full,browser):
        assert binding['exit_code']==0 and binding['source_unchanged']
        for name,value in binding['source_sha256'].items():assert digest(ROOT/name)==value
    assert len(full['source_sha256'])==552 and len(browser['source_sha256'])==190
    work=BASE/'审计/工作目录/001-原生状态隔离';freeze=work/'执行冻结.json';frozen=verify_freeze(freeze,digest(freeze));verify_historical_binding(frozen);assert len(frozen['sha256'])==313
    runtime=verify_backend(ROOT/RUNTIME,frozen['sha256'][RUNTIME]);assert len(runtime['files_sha256'])==54
    retirement=read(ROOT/'evals/interaction/cycle-32/state-isolation-retirement.json');assert retirement['status']=='completed_retired_no_production_activation' and retirement['freeze_sha256']==digest(freeze)
    assert retirement['native_calls']==210 and retirement['avatar_sql_turns']==0 and retirement['production_activation_authorized'] is False and retirement['root_cause_identified'] is False
    for name,value in retirement['sha256'].items():assert digest(ROOT/name)==value
    cpu=read(work/'cpu-control-version.json')
    for stem,name in (('helper','probe_policy_cpu.py'),('policy','state_policy.py')):historical(cpu[stem+'_git_ref'],str((BASE/'审计'/name).relative_to(ROOT)),cpu[stem+'_sha256'])
    assert cpu['control_sha256']==digest(work/'policy-cpu-controls.json')
    for version,key in (('transport-control-version.json','files'),('verifier-control-version.json','files_sha256')):
        data=read(work/version)
        for name,value in data[key].items():historical(data['source_ref'],name,value)
    identity=read(work/'independent-identity-version.json');historical(identity['source_ref'],str((BASE/'审计/verify_state_replay.py').relative_to(ROOT)),identity['verifier_sha256']);assert digest(BASE/'审计/verify_state_replay.py')==identity['verifier_sha256']
    for name,count in (('policy-cpu-controls.json',6),('transport-cpu-controls.json',5),('前置负控/controls.json',4),('verifier-cpu-controls.json',5)):
        data=read(work/name);assert data['passed'] and len(data['controls'])==count
    native=[]
    for label in ('4b','32b'):
        path=work/('native-'+label)/'replay.json';proof=reconstruct(path);persisted=read(path.with_name('independent-identity-verification.json' if label=='4b' else 'independent-verification.json'))
        assert proof==persisted;native.append(proof)
        for policy in read(path)['policies']:
            saved=path.parent/policy['state_policy']/'policy-completed.json'
            if saved.exists():assert read(saved)==policy
    summary=read(work/'已知题状态策略描述汇总.json');assert summary['native_calls']==210 and summary['target_generations']==36 and not summary['root_cause_identified']
    for model in summary['models']:
        assert model['evaluation_sha256']==next(p['evaluation_sha256'] for p in native if p['model_id']==model['model_id'])
        for policy in model['policies']:assert policy['strict_only83_count']==0
    qa=read(BASE/'审计/收尾核验/report-browser.json');metadata=read(BASE/'审计/report-render-metadata.json')
    assert qa['completed'] and not qa['errors'] and qa['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html') and metadata=={'tables':4,'links':22}
    assert [view['viewport']['width'] for view in qa['views']]==[1440,390]
    for view in qa['views']:assert view['tableCount']==4 and not view['overflow'] and len(view['links'])==22 and all(link['exists'] for link in view['links'])
    assert all(table['lastCellReadable'] for table in qa['views'][1]['horizontalTables'])
    docs=['README.md','docs/backend.md','docs/进展报告/2026-11-10-G2交互循环/远期目标与验收路线.md'];links=[]
    for name in docs:
        path=ROOT/name
        for href in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text()):
            if '://' in href or href.startswith('#'):continue
            assert (path.parent/href.split('#')[0]).resolve().exists(),(name,href);links.append({'document':name,'href':href,'exists':True})
    assert subprocess.check_output(['git','config','user.name'],cwd=ROOT,text=True).strip()=='spinner-bot'
    assert not any('serve_state_eval.py' in line for line in subprocess.check_output(['ps','-eo','args'],text=True).splitlines() if not line.startswith(('bash ','/bin/bash ')))
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
        'old_immutable_seals':old,'unchanged_product_full_inputs':552,'unchanged_browser_inputs':190,'product_checks_not_rerun_this_cycle':True,'native_source_inputs':313,'runtime_files':54,
        'source_bound_native_calls':210,'source_bound_targets':36,'avatar_sql_turns':0,'owned_provider_exits':6,'native_proofs':native,'cpu_controls':20,'historical_control_versions_verified':True,
        'report_views':[1440,390],'report_tables':4,'report_local_links':22,'same_agent_screenshot_inspection':True,'public_docs_sha256':{name:digest(ROOT/name) for name in docs},'public_links':links,
        'production_promotion_approved':False,'root_cause_identified':False,'general_semantics_multiday_or_physical_device_approved':False}
    with (BASE/'审计/收尾核验/封存前系统核验.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    print('Verified29 old seals, product552/browser190 unchanged,313 historical/current inputs,54 runtime files,210 calls/36 targets/6 clean exits,20 CPU controls and HTML1440/390; no production or root-cause approval.')


if __name__=='__main__':main()

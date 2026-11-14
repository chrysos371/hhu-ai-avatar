"""C44 staged native/direct, software, failure-history and old-seal reconciliation."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,WORK,REGRESS,CONTROLS,CONTRACT,PROTOCOL,RUNTIME,read,digest,historical,capture_runtime


def main():
    output=BASE/'审计/收尾核验/system-evidence.json';assert not output.exists();output.parent.mkdir(parents=True,exist_ok=True)
    assert capture_runtime()==read(RUNTIME)
    stages={};all_origins=Counter()
    expected={'development':(760,62,144,72,54,30),'protected':(1067,17,36,18,12,12)}
    for stage,(inputs,native,dumps,candidate,baseline,status_selects) in expected.items():
        path=WORK/(stage+'-freeze-v2.json');f=read(path)
        assert len(f['sha256'])==inputs and historical(f['source_ref'],f['sha256'])==f['sha256']
        assert all(digest(ROOT/n)==sha for n,sha in f['sha256'].items())
        assert f['protected_execution_authorized'] is (stage=='protected') and f['registration_version']==2
        proof=read(WORK/(stage+'-verification.json'));directory=BASE/f'实验/{stage}-v2';run=read(directory/'evaluation.json')
        assert proof['verified'] and proof['primary_gate_passed'] and proof['candidate_model_calls']==0
        assert proof['candidate_business_read_count_gate'] and proof['source_and_readonly_gate_passed']
        assert proof['native_calls']==proof['native_prompt_renders_verified']==native
        assert proof['SQL_dumps_reconstructed']==dumps and proof['actual_status_SELECTs']==status_selects
        assert proof['arm_task_scores']=={'model_policy_grounded':baseline,'source_dispatch':candidate}
        assert proof['verifier_sha256']==digest(BASE/'审计/verify_native_dispatch.py')
        assert proof['freeze_sha256']==digest(path) and proof['evaluation_sha256']==digest(directory/'evaluation.json')
        assert proof['actual_project_modules']==21 and proof['mapped_frozen_libraries']==8 and proof['runtime_identity_files']==54
        assert run['completed'] and run['engineering_passed'] and run['cleanup_passed'] and run['source_current_after_execution']
        assert not Path('/proc/'+str(run['provider_pid'])).exists()
        assert all(digest(directory/n)==sha for n,sha in run['artifacts_sha256'].items())
        retirement=read(path.with_name(path.stem+'-retirement.json'))
        assert retirement['descriptor_sha256']==digest(path) and retirement['verification_sha256']==digest(WORK/(stage+'-verification.json'))
        origins=Counter(b['reply_origin'] for g in run['groups'] for c in g['cases'] for b in c['arms'].values())
        all_origins.update(origins)
        stages[stage]={'frozen_inputs':inputs,'freeze_sha256':digest(path),'native_calls':native,'SQL_dumps':dumps,
            'candidate_correct':candidate,'baseline_correct':baseline,'status_SELECTs':status_selects,
            'origins':dict(origins),'provider_pid':run['provider_pid'],'provider_GPU':read(directory/'provider-ready.json')['chosen_gpu']}
    assert dict(all_origins)=={'trusted_read_fixed':92,'framework_no_eligible':14,'verified_clarification':38,
        'framework_no_read':26,'verified_intent_clarification':7,'source_cancelled':2,'model_no_tool_fixed':1}
    protected_admission=read(WORK/'protected-admission.json')
    assert protected_admission['development_verification_sha256']==digest(WORK/'development-verification.json')
    assert protected_admission['false_flag_rejected_with_primary_true'] and protected_admission['retired_rejected']
    assert read(WORK/'protected-retirement-verification.json')['retired_rejected']
    assert read(WORK/'protected-freeze-v2.json')['development_verification_sha256']==digest(WORK/'development-verification.json')
    assert read(WORK/'preflight-stage-controls.json')['verified'] and len(read(WORK/'preflight-stage-controls.json')['cases'])==6
    old=BASE/'审计/工作目录/001-双向目标与直接路由调查'
    for filename,anchor in [('service-first-source.json','f85cab1a'),('service-v2-fixed-source.json','1eee4f02')]:
        record=read(old/filename);assert historical(anchor,record['source_sha256'])==record['source_sha256']
        assert record['log_sha256']==digest(old/('service-first.log' if 'first' in filename else 'service-v2-fixed.log'))
    assert '1 failed, 270 passed' in (old/'service-first.log').read_text() and '273 passed' in (old/'service-v2-fixed.log').read_text()
    retirement=read(old/'v1-registration-retirement.json')
    assert retirement['native_calls']==0 and all(digest(ROOT/n)==sha for n,sha in retirement['old_material_sha256'].items())
    assert read(old/'protocol-v1.json')['protected_cases']==read(PROTOCOL)['protected_cases']
    assert read(CONTRACT)['supersedes_CPU_only_v1']['retirement_sha256']==digest(old/'v1-registration-retirement.json')
    summary=read(CONTROLS/'controlled-summary.json')
    assert summary['groups']==13 and summary['scripted_model_attempts']==25 and summary['SQL_dumps_reconstructed']==60
    assert summary['actual_status_SELECTs']==11
    for path in CONTROLS.glob('*/evaluation.json'):
        d=read(path);assert d['verified'] and d['native_calls']==0
        assert historical(d['head'],d['source_sha256'])==d['source_sha256']
        assert all(digest(ROOT/n)==sha for n,sha in d['source_sha256'].items())
    diagnosis=read(old/'paired-first-diagnosis.json')
    assert historical('406c09d1',diagnosis['collector_source_sha256_reconstructed'])==diagnosis['collector_source_sha256_reconstructed']
    assert diagnosis['SQL_dumps_reconstructed']==48 and diagnosis['scripted_model_used_rows']==20 and diagnosis['new_scripted_model_attempts']==0
    assert 'AssertionError' in (old/'controlled-paired-first.log').read_text() and '48 branches; 20 scripted attempts' in (old/'controlled-paired-fixed.log').read_text()
    accounting=read(BASE/'审计/工作目录/005-系统复核/dispatch-accounting.json')
    assert accounting['analyzer_sha256']==digest(BASE/'审计/analyze_dispatch.py') and accounting['native_total']==79 and accounting['SQL_dump_total']==180
    assert accounting['candidate_strict_correct_total']==accounting['candidate_cases_total']==90 and accounting['candidate_model_calls_total']==0
    candidate=[stage['arms']['source_dispatch'] for stage in accounting['stages'].values()]
    assert sum(a['direct_no_model'] for a in candidate)==accounting['candidate_direct_no_model_total']==63
    assert sum(a['rule_no_model'] for a in candidate)==accounting['candidate_no_read_total']==26
    assert sum(a['source_denied'] for a in candidate)==accounting['candidate_source_denials']==1
    gap=read(BASE/'审计/工作目录/005-系统复核/default-integration-gap.json')
    assert gap['actual_SDK_turns']==2 and gap['native_calls']==0 and not gap['default_feature_delivery_proven']
    assert historical(gap['head'],gap['source_sha256'])==gap['source_sha256']
    assert all(digest(ROOT/n)==sha for n,sha in gap['source_sha256'].items())
    assert all(not r['has_verified_query_metadata'] and r['business_unchanged'] for r in gap['cases'])
    bindings=[]
    for mode in ('python','frontend','build','browser'):
        path=REGRESS/f'dispatch-v2-{mode}-final-binding.json';d=read(path);hashes=d['source_git_sha256']
        assert len(hashes)==460 and d['source_unchanged'] and d['exit_code']==0
        assert historical(d['head'],hashes)==hashes and all(digest(ROOT/n)==sha for n,sha in hashes.items())
        assert d['driver_sha256']==digest(BASE/'审计/run_regression.py') and d['log_sha256']==digest(REGRESS/f'dispatch-v2-{mode}-final.log')
        if mode=='browser':assert d['runtime_matches']
        bindings.append({'mode':mode,'head':d['head'],'inputs':460,'sha256':digest(path)})
    assert '2290 passed, 1 skipped' in (REGRESS/'dispatch-v2-python-final.log').read_text()
    assert '192 passed (192)' in (REGRESS/'dispatch-v2-frontend-final.log').read_text()
    assert '18 passed' in (REGRESS/'dispatch-v2-browser-final.log').read_text() and '16 skipped' in (REGRESS/'dispatch-v2-browser-final.log').read_text()
    runtime=read(REGRESS/'dispatch-v2-browser-final-runtime.json');assert len(runtime['module_paths'])==9 and len(runtime['frontend_sha256'])==5
    for receipt in read(REGRESS/'full-browser-records/copy-receipt.json'):
        path=REGRESS/'full-browser-records'/receipt['archive'];record=read(path)
        assert digest(path)==receipt['sha256'] and record['completed'] and historical(record['head'],hashes)==hashes
        if receipt['archive']=='query.json':assert len(record['turns'])==2 and record['before']==record['after']
        else:assert record['sampleMs']>=1000 and record['sourceAfter']['redacted']
    seals=[]
    for number in range(3,44):
        cycle=BASE.parent/f'cycle-{number:02}';path=cycle/'审计/证据清单.json'
        assert all(digest(cycle/n)==sha for n,sha in read(path).items())
        seals.append({'cycle':cycle.name,'items':len(read(path)),'sha256':digest(path)})
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
    assert len(seals)==41 and sum(s['items'] for s in seals)+len(read(migration))==7661
    assets=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(assets)==9 and all(r['valid'] for r in assets)
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names={str(p.relative_to(ROOT)):module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not found for found in names.values()),names
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(__file__),'stages':stages,'native_calls':79,'SQL_dumps_reconstructed':180,
        'candidate_task_correct':90,'candidate_cases':90,'candidate_model_calls':0,'candidate_direct':63,'candidate_no_read':26,'candidate_source_denied':1,
        'visible_origins':dict(all_origins),'current_software_inputs':460,'software_bindings':bindings,
        'current_scripted_attempts':25,'current_controlled_SQL':60,'retired_first_model_used_rows':20,'retired_first_SQL':48,
        'actual_offline_default_SDK_turns':2,'default_integrated':False,'general_semantic_or_physical_approval':False,
        'issues_total':3,'issues_closed_limited':2,'issues_open_delivery':1,
        'old_seals_including_migration':42,'old_items':7661,'old_cycle_seals':seals,'asset_aliases':assets,'undefined_globals':names}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C44 system:79native/180SQL;candidate72/72+18/18/model0;460source;2290/1,192,18/16;42old7661;2limitedclosed/1deliveryopen')


if __name__=='__main__':main()

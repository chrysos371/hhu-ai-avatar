"""Read-only reconciliation of C42 native, software, failures and old seals."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,WORK,REGRESS,CONTROLS,RUNTIME,read,digest,historical,capture_runtime


def main():
    output=BASE/'审计/收尾核验/system-evidence.json';assert not output.exists()
    output.parent.mkdir(parents=True,exist_ok=True)
    freeze=WORK/'development-freeze.json';frozen=read(freeze)
    assert digest(freeze)=='143b5ba21dc24adb33d52348d1a80d7386c4fe313e3f358fe72d847da0f5c320'
    assert len(frozen['sha256'])==569 and historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
    assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
    assert capture_runtime()==read(RUNTIME)
    v=read(WORK/'development-verification.json');run=read(BASE/'实验/development-v1/evaluation.json')
    assert v['verified'] and v['verifier_sha256']==digest(BASE/'审计/verify_native_catalogues.py')
    assert v['evaluation_sha256']==digest(BASE/'实验/development-v1/evaluation.json')
    assert v['native_calls']==v['native_prompt_renders_verified']==68 and v['SQL_dumps_reconstructed']==90
    assert v['arm_task_scores']=={'full':27,'eligible_bound':24,'eligible_complete':27}
    assert v['arm_invalid_attempts']=={'full':6,'eligible_bound':0,'eligible_complete':0}
    assert v['actual_status_SELECTs']==18 and v['actual_project_modules']==19 and v['mapped_frozen_libraries']==8
    assert v['source_and_readonly_gate_passed'] and not v['primary_gate_passed']
    assert run['completed'] and run['cleanup_passed'] and run['engineering_passed'] and run['source_current_after_execution']
    assert not Path('/proc/'+str(run['provider_pid'])).exists()
    assert all(digest(BASE/'实验/development-v1'/name)==sha for name,sha in run['artifacts_sha256'].items())
    retired=read(WORK/'development-freeze-retirement.json')
    assert retired['descriptor_sha256']==digest(freeze) and retired['verification_sha256']==digest(WORK/'development-verification.json')
    boundary=read(WORK/'protected-and-retirement-verification.json')
    assert boundary['verified'] and boundary['rejected_by_actual_primary_gate'] and boundary['retired_rejected']
    assert boundary['no_provider_or_output_created'] and not boundary['protected_executed']
    assert not (BASE/'实验/should-not-exist-protected').exists()
    origins=Counter();ghost=[]
    for group in run['groups']:
        for case in group['cases']:
            for arm,b in case['arms'].items():
                origins[b['reply_origin']]+=1
                if b['result_kind']=='validation_failure':
                    assert arm=='full' and b['final_arguments']=={'reminder_id':12345}
                    assert not b['status_business_SELECTs']
                    ghost.append({'rep':group['repetition'],'case':case['case'],'arm':arm})
    assert dict(origins)=={'guarded_failure':6,'trusted_read_fixed':42,'model_no_tool_fixed':15,'framework_no_eligible':24,'verified_clarification':3}
    assert len(ghost)==6
    analysis=read(BASE/'审计/工作目录/005-系统复核/catalogue-accounting.json')
    first=read(BASE/'审计/工作目录/005-系统复核/catalogue-accounting-first.json')
    assert analysis['analyzer_sha256']==digest(BASE/'审计/analyze_catalogues.py')
    assert historical('f1271b85',[str((BASE/'审计/analyze_catalogues.py').relative_to(ROOT))])[str((BASE/'审计/analyze_catalogues.py').relative_to(ROOT))]==first['analyzer_sha256']
    assert first['arm_accounting']['full']['by_category']['read']['wrong_policy_reads']==3
    assert [analysis['arm_accounting'][a]['by_category']['read']['wrong_policy_reads'] for a in v['arm_task_scores']]==[0,0,0]
    assert [analysis['arm_accounting'][a]['by_category']['clarify']['wrong_policy_reads'] for a in v['arm_task_scores']]==[0,6,3]
    assert historical('77b3841d',[str((BASE/'审计/analyze_catalogues.py').relative_to(ROOT))])[str((BASE/'审计/analyze_catalogues.py').relative_to(ROOT))]==analysis['analyzer_sha256']
    assert all(x['prompt_hash_equal_count']==24 and x['raw_equal_count']==21 and x['request_hash_equal_count']==0 for x in analysis['historical_lineage'])
    bindings=[]
    for mode in ('python','frontend','build','browser'):
        path=REGRESS/f'catalogue-{mode}-final-binding.json';d=read(path);hashes=d['source_git_sha256']
        assert len(hashes)==450 and d['source_unchanged'] and d['exit_code']==0
        assert historical(d['head'],hashes)==hashes and all(digest(ROOT/n)==sha for n,sha in hashes.items())
        assert d['driver_sha256']==digest(BASE/'审计/run_regression.py')
        assert d['log_sha256']==digest(REGRESS/f'catalogue-{mode}-final.log')
        if mode=='browser':assert d['runtime_matches']
        bindings.append({'mode':mode,'head':d['head'],'inputs':450,'sha256':digest(path)})
    assert '2199 passed, 1 skipped' in (REGRESS/'catalogue-python-final.log').read_text()
    assert '192 passed (192)' in (REGRESS/'catalogue-frontend-final.log').read_text()
    assert '18 passed' in (REGRESS/'catalogue-browser-final.log').read_text() and '16 skipped' in (REGRESS/'catalogue-browser-final.log').read_text()
    runtime=read(REGRESS/'catalogue-browser-final-runtime.json')
    assert len(runtime['module_paths'])==9 and len(runtime['frontend_sha256'])==5
    for receipt in read(REGRESS/'full-browser-records/copy-receipt.json'):
        path=REGRESS/'full-browser-records'/receipt['archive'];record=read(path)
        assert digest(path)==receipt['sha256'] and record['completed']
        assert historical(record['head'],hashes)==hashes
        if receipt['archive']=='query.json':
            assert len(record['turns'])==2 and record['before']==record['after']
            assert all(t['visible']==t['result']['reply'] for t in record['turns'])
        else:assert record['sampleMs']>=1000 and record['sourceAfter']['redacted']
    summary=read(CONTROLS/'controlled-summary.json')
    assert summary['groups']==12 and summary['scripted_model_attempts']==32 and summary['SQL_dumps_reconstructed']==41
    for path in CONTROLS.glob('*/evaluation.json'):
        d=read(path);assert d['verified'] and d['native_calls']==0
        assert historical(d['head'],d['source_sha256'])==d['source_sha256']
        assert all(digest(ROOT/n)==sha for n,sha in d['source_sha256'].items())
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names={str(p.relative_to(ROOT)):module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not found for found in names.values()),names
    seals=[]
    for p in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if not 3<=int(p.parents[1].name[6:])<=41:continue
        assert all(digest(p.parents[1]/name)==sha for name,sha in read(p).items())
        seals.append({'manifest':str(p.relative_to(ROOT)),'items':len(read(p)),'sha256':digest(p)})
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
    assert len(seals)==39 and sum(s['items'] for s in seals)+len(read(migration))==6924
    assets=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(assets)==9 and all(r['valid'] for r in assets)
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(__file__),'retired_native_inputs':569,'native_calls':68,'lab_branch_outcomes':90,
        'actual_status_SELECTs':18,'visible_origins':dict(origins),'arm_task_scores':v['arm_task_scores'],
        'primary_gate_passed':False,'protected_executed':False,'default_enabled':False,'Avatar_application_turns':0,
        'semantic_wrong_policy_reads':{'full':0,'eligible_bound':6,'eligible_complete':3},'guarded_ghost_attempts':ghost,
        'scripted_model_attempts':32,'controlled_SQL_dumps':41,'runtime_identity_files':54,'actual_project_modules':19,
        'mapped_frozen_libraries':8,'current_software_inputs':450,'software_bindings':bindings,
        'maintained_default_browser_results':5,'whole_browser_suite':'18 passed/16 optional skipped',
        'old_seals_including_migration':40,'old_items':6924,'old_cycle_seals':seals,'asset_aliases':assets,
        'issues_total':2,'issues_closed_limited':1,'issues_open_semantic':1,'undefined_globals':names}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C42 system:68native/90SQL;27/24/27;450source;2199/1,192,18/16;40old6924;1limitedclosed/1semanticopen')


if __name__=='__main__':main()

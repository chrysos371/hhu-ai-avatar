"""Read-only reconciliation of C43 native, software, failures and old seals."""
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
    assert digest(freeze)=='2aa6cdbb4cd5903093ed33ba3b0846695c6650226c2e4185f88b87b83a6d5e3b'
    assert len(frozen['sha256'])==576 and historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
    assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
    assert capture_runtime()==read(RUNTIME)
    v=read(WORK/'development-verification.json');run=read(BASE/'实验/development-v1/evaluation.json')
    assert v['verified'] and v['verifier_sha256']==digest(BASE/'审计/verify_native_catalogues.py')
    assert v['evaluation_sha256']==digest(BASE/'实验/development-v1/evaluation.json')
    assert v['native_calls']==v['native_prompt_renders_verified']==74 and v['SQL_dumps_reconstructed']==96
    assert v['arm_task_scores']=={'baseline_complete':41,'policy_grounded':47}
    assert v['arm_invalid_attempts']=={'baseline_complete':0,'policy_grounded':0}
    assert v['actual_status_SELECTs']==14 and v['actual_project_modules']==20 and v['mapped_frozen_libraries']==8
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
    origins=Counter()
    for group in run['groups']:
        for case in group['cases']:
            for arm,b in case['arms'].items():
                origins[b['reply_origin']]+=1
                assert b['result_kind']!='validation_failure' and not b['model_error'] and not b['model_contract_error']
    assert dict(origins)=={'trusted_read_fixed':54,'framework_no_eligible':24,'verified_clarification':18}
    analysis=read(BASE/'审计/工作目录/005-系统复核/catalogue-accounting.json')
    assert analysis['analyzer_sha256']==digest(BASE/'审计/analyze_catalogues.py')
    assert [analysis['arm_accounting'][a]['by_category']['read']['wrong_state_reads'] for a in v['arm_task_scores']]==[1,1]
    assert [analysis['arm_accounting'][a]['by_category']['clarify']['wrong_policy_reads'] for a in v['arm_task_scores']]==[6,0]
    assert analysis['C42_request_SHA_equal']==analysis['C42_prompt_SHA_equal']==analysis['C42_native_raw_equal']==18
    flips=analysis['same_input_route_flip']
    assert len(flips)==6 and len({r['request_body_sha256'] for r in flips})==len({r['prompt_sha256'] for r in flips})==1
    assert Counter(r['function'] for r in flips)=={'read_reminder_delivery_policy':4,'read_reminder_state':2}
    assert analysis['route_flip_cause_established'] is False and analysis['runtime_seed']==42
    source=BASE/'审计/工作目录/001-政策问题依据调查'
    for name,anchor in [('service-first-source.json','615ba39e'),('service-fixtures-fixed-source.json','ca1b251c')]:
        record=read(source/name)
        assert historical(anchor,record['source_sha256'])==record['source_sha256']
    assert '2 failed, 220 passed' in (source/'service-first.log').read_text()
    assert '222 passed' in (source/'service-fixtures-fixed.log').read_text()
    bindings=[]
    for mode in ('python','frontend','build','browser'):
        path=REGRESS/f'policy-evidence-{mode}-final-binding.json';d=read(path);hashes=d['source_git_sha256']
        assert len(hashes)==455 and d['source_unchanged'] and d['exit_code']==0
        assert historical(d['head'],hashes)==hashes and all(digest(ROOT/n)==sha for n,sha in hashes.items())
        assert d['driver_sha256']==digest(BASE/'审计/run_regression.py')
        assert d['log_sha256']==digest(REGRESS/f'policy-evidence-{mode}-final.log')
        if mode=='browser':assert d['runtime_matches']
        bindings.append({'mode':mode,'head':d['head'],'inputs':455,'sha256':digest(path)})
    assert '2239 passed, 1 skipped' in (REGRESS/'policy-evidence-python-final.log').read_text()
    assert '192 passed (192)' in (REGRESS/'policy-evidence-frontend-final.log').read_text()
    assert '18 passed' in (REGRESS/'policy-evidence-browser-final.log').read_text() and '16 skipped' in (REGRESS/'policy-evidence-browser-final.log').read_text()
    runtime=read(REGRESS/'policy-evidence-browser-final-runtime.json')
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
    assert summary['groups']==10 and summary['scripted_model_attempts']==32 and summary['SQL_dumps_reconstructed']==41
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
        if not 3<=int(p.parents[1].name[6:])<=42:continue
        assert all(digest(p.parents[1]/name)==sha for name,sha in read(p).items())
        seals.append({'manifest':str(p.relative_to(ROOT)),'items':len(read(p)),'sha256':digest(p)})
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
    assert len(seals)==40 and sum(s['items'] for s in seals)+len(read(migration))==7289
    assets=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(assets)==9 and all(r['valid'] for r in assets)
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(__file__),'retired_native_inputs':576,'native_calls':74,'lab_branch_outcomes':96,
        'actual_status_SELECTs':14,'visible_origins':dict(origins),'arm_task_scores':v['arm_task_scores'],
        'primary_gate_passed':False,'protected_executed':False,'default_enabled':False,'Avatar_application_turns':0,
        'semantic_wrong_policy_reads':{'baseline_complete':6,'policy_grounded':0},
        'semantic_wrong_state_reads':{'baseline_complete':1,'policy_grounded':1},'same_input_route_flip_cause_known':False,
        'scripted_model_attempts':32,'controlled_SQL_dumps':41,'runtime_identity_files':54,'actual_project_modules':20,
        'mapped_frozen_libraries':8,'current_software_inputs':455,'software_bindings':bindings,
        'maintained_default_browser_results':5,'whole_browser_suite':'18 passed/16 optional skipped',
        'old_seals_including_migration':41,'old_items':7289,'old_cycle_seals':seals,'asset_aliases':assets,
        'issues_total':2,'issues_closed_limited':1,'issues_open_semantic':1,'undefined_globals':names}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C43 system:74native/96SQL;41/47;455source;2239/1,192,18/16;41old7289;1limitedclosed/1semanticopen')


if __name__=='__main__':main()

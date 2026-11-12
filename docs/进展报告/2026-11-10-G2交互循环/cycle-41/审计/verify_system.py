"""C41 whole-cycle archival/current/negative controls and native fact reconciliation."""
import ast
from collections import Counter
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,WORK,REGRESS,CONTROLS,PROTOCOL,REGISTRY,RUNTIME,read,digest,historical,capture_runtime

OUT=BASE/'审计/收尾核验/system-evidence.json'


def main():
    assert not OUT.exists()
    frozen=read(WORK/'execution-freeze-development.json')
    assert digest(WORK/'execution-freeze-development.json')=='6fdb8411dbbde6f73edabfb530b060bd7ee6c64ac772ec5df55bde8c2ae1e86c'
    assert len(frozen['sha256'])==594
    assert historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
    assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
    assert capture_runtime()==read(RUNTIME)
    v=read(WORK/'development-verification.json');run=read(BASE/'实验/development-v1/evaluation.json')
    assert v['verified'] and v['verifier_sha256']==digest(BASE/'审计/verify_native_reads.py')
    assert v['evaluation_sha256']==digest(BASE/'实验/development-v1/evaluation.json')
    assert not v['selection_and_source_gate_passed'] and run['engineering_passed'] and run['cleanup_passed']
    assert v['native_calls']==29 and v['lab_branch_outcomes']==v['SQL_dumps_reconstructed']==48
    assert v['gate_only_final_exact']==v['single_repair_final_exact']==v['initial_exact_routes']==21
    assert v['actual_status_SELECTs']==12 and v['negative_initial_attempts']==0
    assert v['native_prompt_renders_verified']==29 and v['runtime_identity_files']==54
    assert v['actual_project_modules']==18 and v['mapped_frozen_libraries']==8
    retire=read(WORK/'execution-freeze-development-retirement.json')
    assert retire['evaluation_sha256']==digest(BASE/'实验/development-v1/evaluation.json')
    assert retire['verification_sha256']==digest(WORK/'development-verification.json')
    assert retire['protected_execution_authorized'] is False
    assert 'C41 execution contract changed' in (WORK/'protected-partition-rejection.log').read_text()
    assert not (BASE/'实验/should-not-protected').exists() and not (WORK/'protected-admission.json').exists()
    origins=Counter();errors=[];successful_data=0
    for group in run['groups']:
        for case in group['cases']:
            for mode,branch in case['branches'].items():
                origins[branch['reply_origin']]+=1
                for phase in ('first_read','retry_read'):
                    entry=branch[phase]
                    if not entry:continue
                    if entry['result']['ok']:successful_data+=1
                    else:
                        assert entry['result']['error']['code']=='unbound_reminder_id'
                        assert entry['arguments']=={'reminder_id':12345}
                        assert not any('WHERE r.id=12345' in event['sql'] for event in branch['SQL_trace'])
                        errors.append({'repetition':group['repetition'],'case':case['case'],'arm':mode,'stage':phase,'error':entry['result']['error']})
    assert dict(origins)=={'guarded_read_failure':6,'trusted_read_fixed':18,'model_no_read':24}
    assert len(errors)==9 and successful_data==18
    group=BASE/'实验/development-v1'
    wire=[json.loads(line) for line in (group/'request-wire.jsonl').read_text().splitlines()]
    traces=[json.loads(line) for line in (group/'provider-trace.jsonl').read_text().splitlines()]
    old=BASE.parent/'cycle-40/实验/native-wire-4b-sse-fixed'
    oldwire=[json.loads(line) for line in (old/'request-wire.jsonl').read_text().splitlines()]
    oldtrace=[json.loads(line) for line in (old/'provider-trace.jsonl').read_text().splitlines()]
    index={(q['context']['repetition'],q['context']['case']):(q,oldtrace[i]) for i,q in enumerate(oldwire) if q['context']['phase']=='selection'}
    parity=[]
    for i,q in enumerate(wire):
        if q['context']['phase']!='initial':continue
        previous,native=index[q['context']['repetition'],q['context']['case']]
        assert previous['request_body_sha256']==q['request_body_sha256'] and native['response']==traces[i]['response']
        parity.append({'repetition':q['context']['repetition'],'case':q['context']['case'],'wire_SHA_equal':True,'native_raw_equal':True})
    assert len(parity)==24
    assert sum(t['wire_finish_reason']=='tool_calls' for t in traces)==15
    wrong_native=[t for t in traces if (t.get('wire_message') or {}).get('tool_calls') and json.loads(t['wire_message']['tool_calls'][0]['function']['arguments'])=={'reminder_id':12345}]
    assert len(wrong_native)==6
    source=BASE/'审计/工作目录/001-来源与参数调查'
    anchors=[('service-first-source.json','0a562d89'),('service-fixtures-fixed-source.json','35bafb59'),
             ('service-related-source.json','10fb8530'),('startup-transaction-diagnosis.json','889b4fb8')]
    preserved=[]
    for name,ref in anchors:
        d=read(source/name);assert historical(ref,d['source_sha256'])==d['source_sha256']
        preserved.append({'record':name,'actual_recorded_head':d['head'],'exact_dirty_bytes_later_anchor':ref})
    diagnosis=read(source/'startup-transaction-diagnosis.json')
    assert diagnosis['before_construction_in_transaction'] and not diagnosis['after_construction_in_transaction']
    assert diagnosis['caller_rows_remaining_after_rollback']==1
    assert '2 failed, 64 passed' in (source/'service-first.log').read_text()
    assert '1 failed, 66 passed' in (source/'service-fixtures-fixed.log').read_text()
    assert '201 passed' in (source/'startup-fixed-related.log').read_text()
    summary=read(CONTROLS/'controlled-summary.json')
    assert summary['scripted_model_attempts']==39 and summary['scripted_model_exceptions']==1
    assert summary['lab_branch_outcomes']==summary['SQL_dumps_reconstructed']==72 and summary['business_status_SELECTs']==18
    for row in summary['groups']:
        p=CONTROLS/row['mode']/'evaluation.json';d=read(p)
        assert d['verified'] and digest(p)==row['sha256']
        anchor='a9fb0850' if row['mode']=='repair' else d['head']
        assert historical(anchor,d['source_sha256'])==d['source_sha256']
        assert all(digest(ROOT/n)==sha for n,sha in d['source_sha256'].items())
    first_sse=read(WORK/'sse-controlled.json');current_sse=read(WORK/'sse-controlled-current.json')
    reconstructed=WORK/'native-common-at-first-sse-reconstructed.txt'
    assert digest(reconstructed)==first_sse['sampler_sha256']
    def sse_function(text):
        tree=ast.parse(text);node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='collect_sdk_stream')
        return ast.get_source_segment(text,node)
    assert sse_function(reconstructed.read_text())==sse_function((BASE/'审计/native_common.py').read_text())
    assert current_sse['sampler_sha256']==digest(BASE/'审计/native_common.py')
    assert all(d['verified'] and d['scripted_HTTP_streams']==1 and d['native_or_GPU_calls']==0 for d in (first_sse,current_sse))
    admission=read(WORK/'native-admission.json')
    assert admission['verified'] and admission['supersedes_CPU_registration_only_for_frozen_development']
    assert admission['protected_stage_authorized'] is False and admission['default_product_enabled'] is False
    assert admission['admission_driver_sha256']==digest(BASE/'审计/admit_native.py')
    bindings=[]
    for mode in ('python','frontend','build','browser'):
        p=REGRESS/f'source-read-{mode}-final-binding.json';d=read(p);inputs=d['source_git_sha256']
        assert d['source_unchanged'] and d['exit_code']==0 and len(inputs)==445
        assert historical(d['head'],inputs)==inputs and all(digest(ROOT/n)==sha for n,sha in inputs.items())
        assert d['driver_sha256']==digest(BASE/'审计/run_regression.py')
        assert d['log_sha256']==digest(REGRESS/f'source-read-{mode}-final.log')
        if mode=='browser':assert d['runtime_matches']
        bindings.append({'mode':mode,'sha256':digest(p),'head':d['head'],'inputs':445})
    assert '2138 passed, 1 skipped' in (REGRESS/'source-read-python-final.log').read_text()
    assert '192 passed (192)' in (REGRESS/'source-read-frontend-final.log').read_text()
    assert '18 passed' in (REGRESS/'source-read-browser-final.log').read_text() and '16 skipped' in (REGRESS/'source-read-browser-final.log').read_text()
    runtime=read(REGRESS/'source-read-browser-final-runtime.json')
    assert len(runtime['module_paths'])==9 and len(runtime['frontend_sha256'])==5
    query=read(REGRESS/'full-browser-records/query.json');assert query['completed'] and query['before']==query['after']
    assert len(query['turns'])==2 and all(t['visible']==t['result']['reply'] for t in query['turns'])
    for which in ('emotion','dashboard'):
        p=read(REGRESS/('full-browser-records/'+which+'.json'));assert p['completed'] and p['sampleMs']>=1000 and p['sourceAfter']['redacted']
    seals=[]
    for p in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(p.parents[1].name[6:])>=41:continue
        assert all(digest(p.parents[1]/n)==sha for n,sha in read(p).items())
        seals.append({'cycle':p.parents[1].name,'items':len(read(p)),'sha256':digest(p)})
    assert len(seals)==38 and sum(r['items'] for r in seals)==6555
    assert seals[-1]['sha256']=='ba757808806d45a802c460578ca8c9bd72a9cb612d72bb9e10a0b501b8127219'
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    assert len(read(migration))==88 and all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
    assets=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(assets)==9 and all(r['valid'] for r in assets)
    result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'scope':'isolated source-read safety gain; native one-error repair no measured route gain, not default promotion',
        'retired_native_inputs':594,'native_calls':29,'native_initial_calls':24,'native_repair_calls':3,'native_warmups':2,
        'lab_branch_outcomes':48,'SQL_dumps_reconstructed':48,'actual_status_SELECTs':12,'trusted_data_results':18,
        'visible_reply_origins':dict(origins),'guard_unbound_rejections':errors,'native_unbound_proposals':6,
        'native_adapted_tool_calls':15,'gate_only_final_exact':21,'single_repair_final_exact':21,'expected_route_total':24,
        'native_repair_benefit_observed':False,'protected_executed':False,'default_enabled':False,'Avatar_application_turns':0,
        'core_native_project_modules':18,'mapped_frozen_libraries':8,'native_runtime_identity_files':54,
        'C40_reused_initial_parity':parity,'historical_dirty_source_anchors':preserved,
        'scripted_model_attempts':39,'scripted_model_exceptions':1,'controlled_lab_branch_outcomes':72,
        'controlled_SQL_dumps_reconstructed':72,'extra_scripted_HTTP_SSE_streams':2,
        'current_software_bindings':bindings,'current_source_count':445,'full_python':'2138 passed/1 skipped',
        'frontend':'192 passed','default_browser':'18 passed/16 optional skipped','default_browser_modules':9,
        'current_maintained_browser_results':5,'old_cycle_seals':seals,'old_seals_including_migration':39,
        'old_entries_including_migration':6643,'asset_links':assets,'closed_issues':['C41-001','C41-002','C41-003','C41-005'],
        'open_issues':['C41-004'],'general_semantic_or_physical_approval':False,'goal_remains_active':True}
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C41 system verified:29native,48SQLdumps,9guard rejects;21/24 both arms;445current;2138/1,192,18/16;39oldseals')


if __name__=='__main__':main()

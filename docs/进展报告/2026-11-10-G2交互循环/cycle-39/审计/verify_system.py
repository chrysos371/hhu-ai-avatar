"""C39 historical/current source, SQL and actual browser evidence cross-check."""
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/001-状态查询调查'
REGRESS=BASE/'审计/工作目录/002-当前软件与浏览器'
BROWSER=BASE/'审计/工作目录/003-浏览器准备修正'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def history(ref,names):
    raw=subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


def main():
    output=BASE/'审计/收尾核验/system-evidence.json'
    assert not output.exists()
    bindings=[]
    names=['read-query-python','read-query-frontend','read-query-build','read-query-first-browser_targeted',
        'date-fixed-browser_targeted','query-final-python','query-final-frontend','query-final-build','query-final-browser']
    current=read(REGRESS/'query-final-python-final-binding.json')['source_git_sha256']
    assert len(current)==436 and all(digest(ROOT/n)==sha for n,sha in current.items())
    for name in names:
        p=REGRESS/(name+'-final-binding.json')
        d=read(p)
        inputs=d['source_git_sha256']
        assert len(inputs)==436 and d['source_unchanged']
        assert history(d['head'],inputs)==inputs
        driver=str((BASE/'审计/run_regression.py').relative_to(ROOT))
        assert history(d['head'],[driver])[driver]==d['driver_sha256']
        assert digest(REGRESS/(name+'-final.log'))==d['log_sha256']
        if name=='read-query-first-browser_targeted':
            assert d['exit_code']==1
        else:
            assert d['exit_code']==0
        changed=[n for n,sha in inputs.items() if digest(ROOT/n)!=sha]
        assert changed==(['frontend/e2e/reminder-query.spec.ts'] if name.startswith('read-query') else []),changed
        if 'browser' in name:
            assert d['runtime_matches'] and d['optional_e2e_flags_cleared'] and d['default_controlled_provider']
            prefix=name.replace('browser_targeted','browser')
            runtime=read(REGRESS/(prefix+'-final-runtime.json'))
            assert digest(REGRESS/(prefix+'-final-runtime.json'))==d['runtime_sha256']
            assert len(runtime['module_paths'])==9 and len(runtime['frontend_sha256'])==5
            assert runtime['frontend_sha256']==d['runtime_artifact_sha256']
            for key,path in runtime['module_paths'].items():
                assert runtime['module_sha256'][key]==inputs[str(Path(path).relative_to(ROOT))]
            assert runtime['state_privacy_protocol_sha256']==inputs['evals/interaction/cycle-36/maintained-state-privacy-protocol.json']
            assert runtime['reminder_query_protocol_sha256']==inputs['evals/interaction/cycle-39/explicit-reminder-query-protocol.json']
        bindings.append({'name':name,'sha256':digest(p),'head':d['head'],'exit_code':d['exit_code'],
            'current_identical_inputs':len(inputs)-len(changed),'historical_fixture_date_only_delta':changed})
    assert '2017 passed, 1 skipped' in (REGRESS/'query-final-python-final.log').read_text()
    assert '192 passed (192)' in (REGRESS/'query-final-frontend-final.log').read_text()
    assert '18 passed' in (REGRESS/'query-final-browser-final.log').read_text() and '16 skipped' in (REGRESS/'query-final-browser-final.log').read_text()
    before,after=read(WORK/'baseline/evaluation.json'),read(WORK/'baseline-read-control/evaluation.json')
    comparison=read(WORK/'before-after-comparison.json')
    assert comparison['before_sha256']==digest(WORK/'baseline/evaluation.json')
    assert comparison['after_sha256']==digest(WORK/'baseline-read-control/evaluation.json')
    sql=[]
    for report,group in [(before,'baseline'),(after,'baseline-read-control')]:
        assert report['completed'] and report['native_or_GPU_calls']==0 and len(report['cases'])==3
        assert history(report['head'],report['source_sha256'])==report['source_sha256']
        for row in report['cases']:
            dump=WORK/group/(row['id']+'.sql')
            assert digest(dump)==row['after_sql_dump_sha256']
            with closing(sqlite3.connect(':memory:')) as conn:
                conn.row_factory=sqlite3.Row
                conn.executescript(dump.read_text())
                for table,values in row['after'].items():
                    assert [dict(r) for r in conn.execute('SELECT * FROM '+table+' ORDER BY id')]==values
                answer=conn.execute('SELECT content FROM memory_messages WHERE id=?',
                    (row['result']['conversation']['assistant_message_id'],)).fetchone()[0]
                assert answer==row['result']['reply']
            if group=='baseline-read-control':
                assert row['new_query_mode_present'] and row['business_unchanged'] and row['before']==row['after']
                assert row['result']['generation_mode']==row['result']['analysis_mode']=='rules_reminder_query'
                assert not row['result']['action_receipts']['items'] and not row['result']['due_reminders']
            else:
                assert not row['new_query_mode_present'] and not row['business_unchanged']
                assert len(row['after']['memory_reminder_deliveries'])==len(row['after']['memory_action_receipts'])==1
            sql.append({'group':group,'case':row['id'],'sha256':digest(dump),'query_mode':row['new_query_mode_present'],
                'business_unchanged':row['business_unchanged']})
    failed=read(BROWSER/'first-browser-query-evidence.json')
    assert not failed['completed'] and failed['failure'] and not failed['turns']
    assert failed['sourceControl']['generation_mode']=='rules_speaker_control'
    assert failed['calls'][-1]['path']=='/reminders' and failed['calls'][-1]['status']==422
    assert digest(BROWSER/'first-browser-trace.zip')
    browser_rows=[]
    for group,p,binding in [('date-fixed',BROWSER/'date-fixed-browser-records/query.json',
                            'date-fixed-browser_targeted'),('full',REGRESS/'full-browser-records/query.json','query-final-browser')]:
        row=read(p)
        assert row['completed'] and row['failure'] is None and not row['errors'] and not row['nativeOrGpuClaim']
        assert len(row['turns'])==2 and row['before']==row['after']
        assert history(row['head'],current)==current  # actual browser HEAD may differ only by evidence commits
        assert row['sourceControl']['generation_mode']=='rules_speaker_control'
        for turn in row['turns']:
            result=turn['result'];meta=result['reminder_query']
            assert turn['visible']==result['reply']
            assert result['generation_mode']==result['analysis_mode']=='rules_reminder_query'
            assert meta['source_message_id']==result['conversation']['user_message_id']
            assert meta['revision']==result['conversation']['revision']
            assert not meta['business_mutations'] and not meta['human_reading_verified']
            assert not result['tool_calls'] and not result['action_receipts']['items'] and not result['due_reminders']
            conversations=[c['response']['data'] for c in row['calls'] if c['path']=='/conversation']
            stored=[m for conv in conversations for m in conv['items'] if m['id']==result['conversation']['assistant_message_id']]
            assert stored and all(m['text']==result['reply'] for m in stored)
        browser_rows.append({'group':group,'sha256':digest(p),'query_turns':2,'real_source_control_turns':1,
            'target_record_unchanged':True,'actual_head':row['head'],'binding':binding})
    privacy=[]
    for which in ['emotion','dashboard']:
        p=REGRESS/'full-browser-records'/(which+'.json');row=read(p)
        assert row['completed'] and row['failure'] is None and not row['errors'] and not row['nativeOrGpuClaim']
        assert history(row['head'],current)==current
        assert row['sourceAfter']['redacted'] and row['sampleMs']>=1000
        assert row['noReloadNavigationOrUiPrivacyNoticeAfterErasure']
        state=row['afterApi'].get('automatic',row['afterApi'].get('emotion'))
        assert state['valence']==state['arousal']==0
        assert row['afterApi']['context']['revision']==row['beforeApi']['context']['revision']+1
        assert [s.replace(' ','') for s in row['fixedDom']]==(['P0.00/A0.00']*3 if which=='emotion' else ['愉悦度0.00·唤醒度0.00'])
        privacy.append({'page':which,'sha256':digest(p),'sample_ms':row['sampleMs'],'actual_head':row['head']})
    red=read(WORK/'query-emotion-red-source.json')
    # The new red test was added in a dirty worktree; its exact bytes were then
    # committed with the evidence. Never invent an execution HEAD of 71e0771b.
    assert history('71e0771b',red['source_sha256'])==red['source_sha256']
    assert '1 failed, 1 passed' in (WORK/'query-emotion-epoch-red.log').read_text()
    assert '148 passed' in (WORK/'query-final-targeted.log').read_text()
    seals=[]
    for p in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(p.parents[1].name[6:])>=39:continue
        assert all(digest(p.parents[1]/n)==sha for n,sha in read(p).items())
        seals.append({'cycle':p.parents[1].name,'items':len(read(p)),'sha256':digest(p)})
    assert len(seals)==36 and sum(r['items'] for r in seals)==6366
    assert seals[-1]['sha256']=='49d9b7cd2661a1c4eb5d5d377753d57f3b48cddca0a0b95c4684163517608aca'
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
    links=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(links)==9 and all(row['valid'] for row in links)
    result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'scope':'explicit query engineering/SQL/UI only; no generic semantics or physical notification approval',
        'bindings':bindings,'current_source_count':436,'new_python_controls':59,'full_python':'2017 passed/1 skipped',
        'frontend':'192 passed','default_browser':'18 passed/16 optional skipped','source_runtime_modules':9,
        'standalone_probe_results':6,'sql_dumps_reconstructed':sql,'new_query_probe_cases_before':0,'new_query_probe_cases_after':3,
        'query_browser_records':browser_rows,'privacy_browser_records':privacy,
        'actual_evidenced_maintained_application_results':9,'maintained_result_breakdown':{'failed_setup_source_control':1,'successful_query_UI_turns':4,'successful_source_controls':2,'privacy_preparations':2},
        'count_scope':'nine maintained-case chat results only, not all suite calls; six standalone probe results separate; unit calls not mixed',
        'red_test_actual_recorded_head':red['head'],'red_exact_test_bytes_later_commit':'71e0771b','old_cycle_seals':seals,
        'old_seals_including_migration':37,'old_entries_including_migration':6454,'data_links':links,
        'closed_issues':['C39-001','C39-002','C39-003'],'new_native_or_GPU_calls':0,'general_semantic_or_physical_delivery_approval':False}
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C39 system audit:2017/1,192,18/16;436sources;6SQLdumps;9maintained results;37oldseals;0native')


if __name__=='__main__':main()

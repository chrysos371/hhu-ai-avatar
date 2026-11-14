"""Close C47 without rerunning models or rewriting retired experiment outputs."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess

from native_common import ROOT, BASE, WORK, REGRESS, read, digest, historical
from run_regression import snapshot
from verify_native import independent_score, projection


def main():
    output = BASE/'审计/收尾核验/system-evidence.json'
    assert not output.exists()
    output.parent.mkdir(exist_ok=True)
    source = snapshot(); assert len(source) == 479
    admission = read(WORK/'admission.json')
    assert admission['admitted'] and admission['source_sha256'] == source
    assert admission['verifier_sha256'] == digest(BASE/'审计/admit_native.py')
    assert admission['model_constructions'] == admission['native_inference_calls'] == 0
    assert admission['negative_CLI_attempts'] == 10 and admission['SQL_dumps_reconstructed'] == 44
    software = []
    for mode, phrase in [('python','2470 passed, 1 skipped'),('frontend','195 passed'),
                         ('build',None),('browser','19 passed')]:
        prefix = 'native-history-v2-'+mode+'-final'
        path = REGRESS/(prefix+'-binding.json'); data = read(path)
        log = REGRESS/(prefix+'.log')
        assert data['exit_code'] == 0 and data['source_unchanged'] and data['source_git_sha256'] == source
        assert historical(data['head'],source) == source
        assert data['driver_sha256'] == digest(BASE/'审计/run_regression.py')
        assert data['log_sha256'] == digest(log)
        if phrase: assert phrase in log.read_text()
        if mode == 'browser':
            assert '16 skipped' in log.read_text() and data['runtime_matches']
            runtime_path = REGRESS/'native-history-v2-browser-final-runtime.json'; runtime = read(runtime_path)
            assert digest(runtime_path) == data['runtime_sha256']
            assert len(runtime['module_paths']) == 13 and len(runtime['frontend_sha256']) == 5
            assert runtime['frontend_sha256'] == data['runtime_artifact_sha256']
            for name,path_name in runtime['module_paths'].items():
                assert runtime['module_sha256'][name] == digest(path_name) == source[str(Path(path_name).relative_to(ROOT))]
            assert runtime['query_history_protocol_sha256'] == source['evals/interaction/cycle-46/query-history-protocol.json']
        software.append({'mode':mode,'binding_sha256':digest(path),'head':data['head']})

    cases = {c['id']:c for c in read(ROOT/'evals/interaction/cycle-47/native-history-cases.json')['cases']}
    models = []; native_SQL_count = 0
    for short in ('4b','14b'):
        folder = BASE/'实验'/(short+'-development-v2')
        proof_path = WORK/(short+'-verification.json'); proof = read(proof_path)
        frozen_path = WORK/(short+'-freeze-v2.json'); frozen = read(frozen_path)
        retired_path = WORK/(short+'-freeze-v2-retirement.json'); retired = read(retired_path)
        retirement = read(WORK/(short+'-retirement-verification.json'))
        evaluation = read(folder/'evaluation.json')
        assert proof['verified'] and proof['verifier_sha256'] == digest(BASE/'审计/verify_native.py')
        assert proof['evaluation_sha256'] == digest(folder/'evaluation.json')
        assert proof['freeze_sha256'] == digest(frozen_path) == retired['freeze_sha256']
        assert retired['retired'] and retired['verification_sha256'] == digest(proof_path)
        assert retirement['verified'] and retirement['retirement_sha256'] == digest(retired_path)
        assert retirement['closed_output_unchanged'] and retirement['additional_native_calls'] == 0
        assert retirement['verification_sha256'] == digest(proof_path)
        assert historical(frozen['source_ref'],frozen['sha256']) == frozen['sha256']
        assert all(digest(ROOT/n) == sha for n,sha in frozen['sha256'].items())
        assert all(digest(folder/n) == sha for n,sha in evaluation['artifacts_sha256'].items())
        assert evaluation['completed'] and evaluation['cleanup_passed'] and evaluation['failure'] is None
        assert evaluation['weight_identity_after_execution'] and evaluation['frozen_current_after_execution']
        assert proof['native_calls'] == proof['native_raw_stop_count'] == 98
        assert proof['SQL_dumps_reconstructed'] == 96 and proof['actual_prompt_hashes_rerendered'] == 98
        assert proof['native_calls_during_verification'] == 0 and proof['transport_passed']
        assert proof['installed_libraries'] == 54 and proof['mapped_frozen_libraries'] == 8
        scores = Counter(); raw_scores = Counter(); fields = {}; mismatches = {}; per_case = {}
        paths = sorted(folder.glob('repetition-*/*/receipt.json')); assert len(paths) == 48
        for path in paths:
            trial = read(path); arm = trial['arm']; case = trial['case']; expected = cases[case]['expected']
            assert trial['expected_registered_after_execution'] == expected
            assert trial['query_model_calls'] == 0 and trial['model_modes_valid']
            assert trial['business_unchanged_by_query_and_ordinary'] and trial['no_new_user_facts']
            assert len(trial['actual_model_interface_calls']) == 2
            actual = independent_score(trial['ordinary_result']['reply'],expected)
            generation = next(c for c in trial['actual_model_interface_calls'] if c['role'] == 'generation')
            raw = independent_score(generation['raw_reply'],expected)
            assert actual['task_correct'] == trial['final_reply_score']['task_correct']
            assert actual['field_checks'] == trial['final_reply_score']['field_checks']
            assert raw['task_correct'] == trial['raw_generation_score']['task_correct']
            scores[arm] += actual['task_correct']; raw_scores[arm] += raw['task_correct']
            fields.setdefault(arm,Counter()).update(actual['field_checks'])
            per_case.setdefault(arm,Counter())[case] += actual['task_correct']
            for field,correct in actual['field_checks'].items():
                if not correct: mismatches.setdefault(arm,Counter())[case+'/'+field] += 1
            for name,projection_key,count in [('after-query.sql','business_after_query',2),
                                               ('after-ordinary.sql','business_after_ordinary',4)]:
                with sqlite3.connect(':memory:') as conn:
                    conn.row_factory = sqlite3.Row
                    conn.executescript((path.parent/name).read_text())
                    assert projection(conn) == trial[projection_key]
                    # Decode actual SQL scalars; never inspect sqlite3.Row repr.
                    rows = [dict(row) for row in conn.execute('SELECT id,role,content FROM memory_messages ORDER BY id')]
                    assert len(rows) == count and rows[1]['content'] == trial['query_result']['reply']
                    if count == 4: assert rows[3]['content'] == trial['ordinary_result']['reply']
                native_SQL_count += 1
        assert dict(scores) == proof['arm_final_contract_scores']
        assert dict(raw_scores) == proof['arm_SDK_generation_contract_scores']
        assert fields == proof['arm_field_checks']
        primary = scores['verified_snapshot_history'] == 24
        assert proof['primary_gate_passed'] is primary is evaluation['primary_gate_passed']
        models.append({'model':short,'verification_sha256':digest(proof_path),'freeze_sha256':digest(frozen_path),
            'source_ref':frozen['source_ref'],'inputs':len(frozen['sha256']),'strict_scores':dict(scores),
            'field_correct':fields,'per_case_correct':per_case,'mismatches':mismatches,
            'native_calls':98,'SQL_dumps':96,'primary_gate_passed':primary,'GPU':proof['actual_chosen_GPU']})
    assert native_SQL_count == 192
    cpu = read(BASE/'审计/工作目录/003-受控实模管线/v2/controlled-summary.json')
    assert cpu['actual_SDK_trials'] == 21 and cpu['scripted_model_interface_attempts'] == 40
    assert cpu['native_calls'] == 0 and cpu['gold_poison_model_inputs_unchanged']
    cpu_SQL = list((BASE/'审计/工作目录/003-受控实模管线').rglob('*.sql')); assert len(cpu_SQL) == 44
    for path in cpu_SQL:
        with sqlite3.connect(':memory:') as conn:
            conn.executescript(path.read_text())
            assert conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    seals = []
    for number in range(3,47):
        cycle = BASE.parent/f'cycle-{number:02}'; path = cycle/'审计/证据清单.json'; data = read(path)
        assert all(digest(cycle/n) == sha for n,sha in data.items())
        seals.append({'cycle':cycle.name,'items':len(data),'sha256':digest(path)})
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'; data = read(migration)
    assert all(digest(migration.parent/n) == sha for n,sha in data.items())
    assert sum(s['items'] for s in seals)+len(data) == 8565
    aliases = json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(aliases) == 9 and all(a['valid'] for a in aliases)
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not missing for missing in names.values()),names
    assert snapshot() == source
    result = {'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'current_software_inputs':479,'source_sha256':source,'software':software,
        'models':models,'native_calls':196,'native_formal_calls':192,'native_warmup_calls':4,
        'native_actual_SDK_trials':96,'native_query_turns':96,'native_ordinary_turns':96,
        'native_unique_SQL_dumps':native_SQL_count,'CPU_unique_SQL_dumps':len(cpu_SQL),
        'CPU_current_trials':21,'CPU_retired_trials':1,'CPU_scripted_interface_attempts':40,
        'new_native_inference_during_system_audit':0,'old_seals_including_migration':45,'old_items':8565,
        'old_seals':seals,'asset_aliases':aliases,'undefined_globals':names,
        'issues_limited_closed':1,'issues_open':3,'general_semantic_or_default_model_approval':False}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C47 system verified:196 native;192 native +44 CPU SQL;479 source;45 old seals/8565 items;both semantic gates failed')


if __name__ == '__main__':
    main()

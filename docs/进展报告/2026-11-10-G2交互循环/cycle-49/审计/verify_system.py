"""Cross-check retired C49 experiments, separating format and literal claims."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,WORK,REGRESS,CONTROLS,CASES,read,digest,historical
from run_regression import snapshot
from verify_native import independent_score,inspect_observations


def literal_claims(reply):
    """Count explicit JSON Boolean claims without repairing the strict score."""
    def unique(pairs):
        value = {}
        for k,v in pairs:
            if k in value: raise ValueError('duplicate key')
            value[k] = v
        return value
    def nonfinite(value): raise ValueError('nonfinite')
    try:
        value = json.loads(reply,object_pairs_hook=unique,parse_constant=nonfinite)
        if type(value) is not dict: return None
    except (TypeError,ValueError,RecursionError): return None
    return {key:value.get(key) is True for key in
        ('mail_sms_phone_sent','human_reading_verified','human_task_completion_verified')}


def main():
    output = BASE/'审计/收尾核验/system-evidence.json'; assert not output.exists()
    output.parent.mkdir(exist_ok=True)
    source = snapshot(); assert len(source) == 489
    admission = read(WORK/'admission.json'); assert admission['admitted']
    assert admission['source_sha256'] == source and admission['negative_CLI_attempts'] == 18
    assert admission['SQL_dumps_reconstructed'] == 136
    assert admission['verifier_sha256'] == digest(BASE/'审计/admit_native.py')
    assert admission['model_constructions'] == admission['native_inference_calls'] == 0
    transport = read(BASE/'审计/工作目录/001-材料与来源调查/transport-gate-replay.json')
    assert transport['verified'] and transport['early_run_body_before_sampling_unchanged']
    assert transport['runner_sha256'] == digest(BASE/'审计/run_native.py')
    assert transport['probe_sha256'] == digest(BASE/'审计/probe_trial_transport_gate.py')
    assert transport['admission_sha256'] == digest(WORK/'admission.json') and transport['new_native_calls'] == 0
    for row in transport['checks']: assert row['sha256'] == digest(ROOT/row['fixture'])
    software = []
    for mode,phrase in [('python','2537 passed, 1 skipped'),('frontend','195 passed'),('build',None),('browser','19 passed')]:
        p = REGRESS/f'minimal-history-v1-{mode}-final-binding.json'; proof = read(p)
        log = REGRESS/f'minimal-history-v1-{mode}-final.log'
        assert proof['exit_code'] == 0 and proof['source_unchanged'] and proof['source_git_sha256'] == source
        assert historical(proof['head'],source) == source
        assert proof['driver_sha256'] == digest(BASE/'审计/run_regression.py') and proof['log_sha256'] == digest(log)
        if phrase: assert phrase in log.read_text()
        if mode == 'browser':
            assert proof['runtime_matches'] and '16 skipped' in log.read_text()
            runtime_path = REGRESS/'minimal-history-v1-browser-final-runtime.json'; runtime = read(runtime_path)
            assert proof['runtime_sha256'] == digest(runtime_path)
            assert len(runtime['module_paths']) == 13 and len(runtime['frontend_sha256']) == 5
            assert runtime['frontend_sha256'] == proof['runtime_artifact_sha256']
            for name,path in runtime['module_paths'].items():
                assert runtime['module_sha256'][name] == digest(path) == source[str(Path(path).relative_to(ROOT))]
        software.append({'mode':mode,'head':proof['head'],'binding_sha256':digest(p)})
    cases = {c['id']:c for c in read(CASES)['cases']}
    models = []; native_SQL = 0
    for short in ('4b','14b'):
        proof_path = WORK/(short+'-verification.json'); proof = read(proof_path)
        folder = BASE/'实验'/(short+'-development-v1'); evaluation = read(folder/'evaluation.json')
        frozen_path = WORK/(short+'-freeze-v1.json'); frozen = read(frozen_path)
        retired_path = WORK/(short+'-freeze-v1-retirement.json'); retired = read(retired_path)
        retirement = read(WORK/(short+'-retirement-verification.json'))
        assert proof['verified'] and proof['verifier_sha256'] == digest(BASE/'审计/verify_native.py')
        assert proof['evaluation_sha256'] == digest(folder/'evaluation.json')
        assert digest(frozen_path) == proof['freeze_sha256'] == retired['freeze_sha256']
        assert retired['retired'] and retired['verification_sha256'] == digest(proof_path)
        assert retirement['verified'] and retirement['retirement_sha256'] == digest(retired_path)
        assert retirement['verification_sha256'] == digest(proof_path)
        assert retirement['closed_output_unchanged'] and retirement['additional_native_calls'] == 0
        assert historical(frozen['source_ref'],frozen['sha256']) == frozen['sha256']
        assert all(digest(ROOT/n) == sha for n,sha in frozen['sha256'].items())
        assert all(digest(folder/n) == sha for n,sha in evaluation['artifacts_sha256'].items())
        assert evaluation['completed'] and evaluation['cleanup_passed'] and evaluation['failure'] is None
        assert evaluation['weight_identity_after_execution'] and evaluation['frozen_current_after_execution']
        assert proof['native_calls'] == proof['native_raw_stop_count'] == proof['actual_prompt_hashes_rerendered'] == 326
        assert proof['SQL_dumps_reconstructed'] == 378 and proof['actual_SDK_trials'] == 162
        assert proof['actual_query_turns'] == 216 and proof['actual_ordinary_turns'] == 162
        assert proof['transport_passed'] and proof['native_calls_during_verification'] == 0
        assert proof['installed_libraries'] == 54 and proof['mapped_frozen_libraries'] == 8
        arms = {arm:{'strict_correct':0,'format_valid':0,'field_correct':Counter(),
            'valid_format_field_mismatches':Counter(),'JSON_objects_for_literal_claims':0,
            'not_JSON_objects_for_literal_claims':0,'literal_true_claims':Counter(),
            'groups':Counter(),'cases':{}} for arm in proof['arm_final_contract_scores']}
        pairs = {}; dumps = 0
        paths = sorted(folder.glob('repetition-*/*/receipt.json')); assert len(paths) == 162
        for path in paths:
            receipt = read(path); case = cases[receipt['case']]; arm = receipt['arm']
            assert receipt['expected_registered_after_execution'] == case['expected']
            assert receipt['query_model_calls'] == 0 and receipt['model_modes_valid']
            assert receipt['business_unchanged_by_query_and_ordinary'] and receipt['no_new_user_facts']
            result = independent_score(receipt['ordinary_result']['reply'],case['expected'])
            generation = next(c for c in receipt['actual_model_interface_calls'] if c['role']=='generation')
            raw = independent_score(generation['raw_reply'],case['expected'])
            assert all(result[k] == receipt['final_reply_score'][k] for k in ('format_valid','parsed','field_checks','task_correct'))
            assert all(raw[k] == receipt['raw_generation_score'][k] for k in ('format_valid','parsed','field_checks','task_correct'))
            stats = arms[arm]; stats['strict_correct'] += result['task_correct']; stats['format_valid'] += result['format_valid']
            stats['field_correct'].update(result['field_checks']); stats['groups'][case['group']] += result['task_correct']
            case_stats = stats['cases'].setdefault(case['id'],{'strict_correct':0,'format_valid':0,'field_correct':Counter(),'literal_true_claims':Counter()})
            case_stats['strict_correct'] += result['task_correct']; case_stats['format_valid'] += result['format_valid']
            case_stats['field_correct'].update(result['field_checks'])
            if result['format_valid']:
                stats['valid_format_field_mismatches'].update(k for k,v in result['field_checks'].items() if not v)
            claims = literal_claims(receipt['ordinary_result']['reply'])
            if claims is None: stats['not_JSON_objects_for_literal_claims'] += 1
            else:
                stats['JSON_objects_for_literal_claims'] += 1
                stats['literal_true_claims'].update(claims); case_stats['literal_true_claims'].update(claims)
            pairs.setdefault((case['id'],receipt['repetition']),{})[arm] = result
            dumps += inspect_observations(path.parent,receipt,case,arm)
        for arm,stats in arms.items():
            assert stats['strict_correct'] == proof['arm_final_contract_scores'][arm]
            assert stats['strict_correct'] == proof['arm_SDK_generation_contract_scores'][arm]
            assert stats['field_correct'] == proof['arm_field_checks'][arm]
            assert stats['groups'] == proof['arm_group_contract_scores'][arm]
        controls = ('production_snapshot','C48_typed_control')
        regressions = {a:Counter() for a in controls}; improvements = {a:Counter() for a in controls}
        for key,values in pairs.items():
            candidate = values['minimal_observation']
            for control_arm in controls:
                baseline = values[control_arm]
                for field,correct in baseline['field_checks'].items():
                    if correct and not candidate['field_checks'][field]: regressions[control_arm][key[0]+'/'+field] += 1
                    if not correct and candidate['field_checks'][field]: improvements[control_arm][key[0]+'/'+field] += 1
        assert dumps == 378; native_SQL += dumps
        assert proof['primary_gate_passed'] is evaluation['primary_gate_passed'] is False
        models.append({'model':short,'verification_sha256':digest(proof_path),'source_ref':frozen['source_ref'],
            'inputs':len(frozen['sha256']),'freeze_sha256':digest(frozen_path),'arms':arms,
            'paired_field_regressions':regressions,'paired_field_improvements':improvements,
            'native_calls':proof['native_calls'],'SQL_dumps':dumps,'GPU':proof['actual_chosen_GPU'],'primary_gate_passed':False})
    assert native_SQL == 756
    assert sum(m['native_calls'] for m in models) == 652
    assert all(type(m['native_calls']) is int and m['native_calls'] == 326 for m in models)
    control = read(CONTROLS/'v1/controlled-summary.json'); CPU_SQL = 0
    assert control['actual_SDK_trials'] == 59 and control['native_calls'] == 0
    for row in control['groups']:
        path = CONTROLS/'v1'/row['folder']; receipt = read(path/'receipt.json')
        CPU_SQL += inspect_observations(path,receipt,cases[receipt['case']],receipt['arm'])
    assert CPU_SQL == 136
    contract_path = BASE/'审计/工作目录/005-最小来源契约/source-contract.json'; contract = read(contract_path)
    assert contract['verified'] and contract['probe_sha256'] == digest(BASE/'审计/probe_minimal_source_contract.py')
    assert contract['candidate_sha256'] == source['src/avatar/lab/minimal_history_observation.py']
    assert contract['receipt_sha256'] == digest(ROOT/contract['receipt'])
    assert contract['SQL_service_claim_recorded'] is False
    assert contract['C48_control_exposes_flipped_flag'] and contract['minimal_context_identical_after_bit_flip']
    assert contract['sampled_minimal_query_frames_without_unbound_claim_or_query_proves_fields'] == 144
    assert all(not c['minimal_projection_added'] for c in contract['reply_inconsistent_negative_controls'])
    assert contract['new_SDK_turns'] == contract['new_native_calls'] == contract['new_SQL_dumps'] == 0
    oracle_dir = BASE/'审计/工作目录/001-材料与来源调查'
    fixed = read(oracle_dir/'registered-oracle-fixed.json'); red = read(oracle_dir/'registered-oracle-red.json')
    assert fixed['verified'] and red['expected_red_reproduced']
    assert fixed['current_verifier_sha256'] == digest(BASE/'审计/verify_native.py')
    assert fixed['runner_sha256'] == digest(BASE/'审计/run_native.py')
    assert fixed['probe_sha256'] == red['probe_sha256'] == digest(BASE/'审计/probe_registered_order_gate.py')
    assert red['archived_verifier_sha256'] == digest(oracle_dir/'verify-native-before-order-review.py.txt')
    seals = []
    for number in range(3,49):
        cycle = BASE.parent/f'cycle-{number:02}'; path = cycle/'审计/证据清单.json'; data = read(path)
        assert all(digest(cycle/n) == sha for n,sha in data.items())
        seals.append({'cycle':cycle.name,'items':len(data),'sha256':digest(path)})
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'; data = read(migration)
    assert all(digest(migration.parent/n) == sha for n,sha in data.items())
    assert len(seals)+1 == 47 and sum(s['items'] for s in seals)+len(data) == 9740
    aliases = json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(aliases) == 9 and all(a['valid'] for a in aliases)
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not missing for missing in names.values()),names
    assert snapshot() == source
    result = {'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'source_sha256':source,'current_software_inputs':489,'software':software,
        'models':models,'native_calls':652,'native_formal_calls':648,'native_warmups':4,
        'native_SDK_trials':324,'native_query_turns':432,'native_ordinary_turns':324,'native_SDK_turns':756,
        'native_unique_SQL_dumps':756,'CPU_unique_SQL_dumps':136,'CPU_SDK_trials':59,
        'CPU_SDK_turns':136,'CPU_scripted_attempts':116,'source_contract_sha256':digest(contract_path),
        'metadata_probe_new_SQL_dumps':0,'metadata_probe_reconstructed_existing_SQL':1,
        'new_native_calls_during_system_audit':0,'old_seals_including_migration':47,'old_items':9740,
        'old_seals':seals,'asset_aliases':aliases,'undefined_globals':names,'issues_limited_closed':2,'issues_open':3,
        'candidate_rejected_for_default_activation':True,'general_semantic_or_default_model_approval':False}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C49 system:652 native;756 native +136 CPU SQL;489 source;47old/9740;format vs actual JSON claims separated;candidate rejected')


if __name__ == '__main__': main()

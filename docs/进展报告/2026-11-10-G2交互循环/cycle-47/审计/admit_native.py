"""Pre-native CPU/software/version and actual CLI-rejection admission, no models."""
import copy
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from native_common import (ROOT,BASE,WORK,REGRESS,CONTROLS,PROTOCOL,CASES,REGISTRY,RUNTIME,WEIGHTS,
    read,digest,historical,capture_runtime,protocol_check)
from run_regression import snapshot
from verify_native import independent_score,projection


def main():
    destination = WORK/'admission.json'; assert not destination.exists()
    protocol_check(); source = snapshot(); assert len(source) == 479
    for mode in ('python','frontend','build','browser'):
        proof = read(REGRESS/f'native-history-v2-{mode}-final-binding.json')
        assert proof['exit_code'] == 0 and proof['source_unchanged'] and proof['source_git_sha256'] == source
        assert historical(proof['head'],source) == source
        assert proof['driver_sha256'] == digest(BASE/'审计/run_regression.py')
        assert proof['log_sha256'] == digest(REGRESS/f'native-history-v2-{mode}-final.log')
        if mode == 'browser': assert proof['runtime_matches'] and proof['optional_e2e_flags_cleared']
    control = read(CONTROLS/'v2/controlled-summary.json')
    assert control['completed'] and control['actual_SDK_trials'] == 21 and control['scripted_model_interface_attempts'] == 40
    assert control['native_calls'] == 0 and control['gold_poison_model_inputs_unchanged']
    assert historical(control['head'],source) == source
    SQL_count = 0
    for row in control['groups']:
        folder = CONTROLS/'v2'/row['folder']; receipt = read(folder/'receipt.json')
        for key,text in [('raw_generation_score',next((c['raw_reply'] for c in receipt['actual_model_interface_calls'] if c['role'] == 'generation'),None)),
                         ('final_reply_score',receipt['ordinary_result']['reply'])]:
            score = independent_score(text,receipt['expected_registered_after_execution'])
            assert all(score[k] == receipt[key][k] for k in ('format_valid','parsed','field_checks','task_correct'))
        for name,expected in [('after-query.sql',receipt['business_after_query']),('after-ordinary.sql',receipt['business_after_ordinary'])]:
            with sqlite3.connect(':memory:') as conn:
                conn.row_factory = sqlite3.Row; conn.executescript((folder/name).read_text())
                assert projection(conn) == expected
                assert conn.execute('SELECT count(*) FROM memory_messages').fetchone()[0] == (2 if name == 'after-query.sql' else 4)
            SQL_count += 1
    retired = read(BASE/'审计/工作目录/001-实模方案调查/v1-registration-retirement.json')
    assert retired['actual_native_calls'] == 0 and retired['native_execution_descriptor_created'] is False
    first_dir = BASE/'审计/工作目录/001-实模方案调查'
    for name,sha in retired['original_material_sha256'].items(): assert digest(first_dir/name) == sha
    first = read(CONTROLS/'active-neutral-authorized_raw_history/receipt.json')
    assert not first['actual_model_interface_calls'] and not first['model_modes_valid']
    assert first['ordinary_result']['generation_mode'] == 'rules_reminder_query'
    for name in ('after-query.sql','after-ordinary.sql'):
        with sqlite3.connect(':memory:') as conn:
            conn.executescript((CONTROLS/'active-neutral-authorized_raw_history'/name).read_text())
        SQL_count += 1
    assert SQL_count == 44
    old_cases = read(first_dir/'cases-v1.json')['cases']; new_cases = read(CASES)['cases']
    assert old_cases[1:] == new_cases[1:]
    first_old,first_new = copy.deepcopy(old_cases[0]),copy.deepcopy(new_cases[0])
    assert first_old.pop('followup_text') != first_new.pop('followup_text') and first_old == first_new
    assert read(RUNTIME) == capture_runtime()
    weights = read(WEIGHTS); assert weights['model_constructions'] == weights['native_inference_calls'] == 0
    assert weights['registry_sha256'] == digest(REGISTRY) and len(weights['models']) == 2
    for short in ('4b','14b'):
        meta = read(WORK/(short+'-template-metadata.json'))
        assert meta['template_sha256'] == digest(WORK/(short+'-embedded-chat-template.jinja'))
        assert meta['model_construction'] is False and meta['native_inference_calls'] == 0
    sse = read(WORK/'sse-controlled-v2.json')
    assert sse['verified'] and sse['native_or_GPU_calls'] == 0 and len(sse['SDK_events']) == 3
    assert sse['probe_sha256'] == digest(BASE/'审计/probe_sse_collector.py')
    assert sse['sampler_sha256'] == digest(BASE/'审计/native_common.py')
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {}
    for p in (BASE/'审计').glob('*.py'):
        compile(p.read_text(),str(p),'exec')
        names[p.name] = module.undefined_globals(p.read_text(),str(p))
    assert all(not values for values in names.values()),names
    for required in ('sample_history.py','controlled_history.py','native_common.py','prepare_native.py','inspect_templates.py',
                     'run_native.py','verify_native.py','rerender_native_templates.py','freeze_native.py','admit_native.py'):
        assert (BASE/'审计'/required).is_file()
    negative = WORK/'negative-cli-inputs'; assert not negative.exists(); negative.mkdir()
    path = WORK/'4b-freeze-v2.json'; marker = WORK/'4b-freeze-v2-retirement.json'
    target = BASE/'实验/4b-development-v2'; assert not path.exists() and not marker.exists() and not target.exists()
    baseline = {'registration_version':2,'model_id':'qwen3-4b-q4_k_m','output_tag':'4b-development-v2',
        'partition':'development','protected_authorized':False,'repetitions':3,'max_native_calls':98,
        'protocol_sha256':digest(PROTOCOL),'registry_sha256':digest(REGISTRY),
        'runtime_sha256':digest(RUNTIME),'weights_sha256':digest(WEIGHTS),'source_ref':'deliberately-unadmitted-fixture','sha256':{}}
    checks = [('wrong-sha',{},'C47 descriptor SHA differs'),
        ('protected-true',{'protected_authorized':True},'authorization differs'),
        ('protected-zero',{'protected_authorized':0},'authorization differs'),
        ('protected-null',{'protected_authorized':None},'authorization differs'),
        ('version-bool',{'registration_version':True},'authorization differs'),
        ('repetitions-bool',{'repetitions':True},'authorization differs'),
        ('repetitions-float',{'repetitions':3.0},'authorization differs'),
        ('native-cap-bool',{'max_native_calls':True},'authorization differs'),
        ('native-cap-float',{'max_native_calls':98.0},'authorization differs'),
        ('retired-fixture',{},'descriptor retired')]
    attempts = []
    try:
        for label,changes,message in checks:
            value = baseline | changes; path.write_text(json.dumps(value,indent=2)+'\n')
            if label == 'retired-fixture': marker.write_text('{"scope":"deliberate CPU-only retirement marker"}\n')
            expected = '0'*64 if label == 'wrong-sha' else digest(path)
            argv = [sys.executable,str(BASE/'审计/run_native.py'),'--freeze',str(path),
                '--expected-freeze-sha256',expected,'--model','qwen3-4b-q4_k_m','--output',str(target)]
            result = subprocess.run(argv,cwd=ROOT,text=True,capture_output=True)
            assert result.returncode != 0 and message in result.stderr and not target.exists(),(label,result.stderr)
            fixture = negative/(label+'.json'); path.replace(fixture)
            if marker.exists(): marker.replace(negative/(label+'-retirement.json'))
            attempts.append({'label':label,'argv':argv,'fixture':str(fixture.relative_to(ROOT)),
                'fixture_sha256':digest(fixture),'expected_rejection':message,'returncode':result.returncode,
                'stdout':result.stdout,'stderr':result.stderr,'provider_output_created':False})
    finally:
        if path.exists(): path.replace(negative/'unfinished-fixture.json')
        if marker.exists(): marker.replace(negative/'unfinished-retirement.json')
    (negative/'CLI-rejections.json').write_text(json.dumps(attempts,ensure_ascii=False,indent=2)+'\n')
    assert snapshot() == source
    proof = {'admitted':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'source_sha256':source,'current_software_inputs':len(source),
        'current_scripted_SDK_trials':21,'retired_CPU_only_trials':1,'SQL_dumps_reconstructed':SQL_count,
        'model_constructions':0,'native_inference_calls':0,'installed_libraries':54,'weights':2,
        'same_client_SSE_control_verified':True,'negative_CLI_attempts':len(attempts),
        'negative_CLI_sha256':digest(negative/'CLI-rejections.json'),'undefined_globals':names,
        'scope':'admit only future separately frozen registered development models; no model/default/semantic approval'}
    destination.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print('C47 admission:479 source/Git;21 current+1 retired CPU trials/44SQL;54 libraries/2weights;SSE;10 CLI rejections;0 model construction')


if __name__ == '__main__':
    main()

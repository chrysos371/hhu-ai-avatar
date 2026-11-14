"""Admit future C48 freezes after source, CPU, software and CLI negative checks."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from native_common import (ROOT,BASE,WORK,REGRESS,CONTROLS,PROTOCOL,CASES,REGISTRY,RUNTIME,WEIGHTS,
    read,digest,historical,capture_runtime,protocol_check)
from run_regression import snapshot
from verify_native import independent_score,inspect_observations


def main():
    destination = WORK/'admission.json'; assert not destination.exists()
    protocol_check(); source = snapshot(); assert len(source) == 484
    for mode,phrase in [('python','2515 passed, 1 skipped'),('frontend','195 passed'),('build',None),('browser','19 passed')]:
        proof = read(REGRESS/f'typed-history-v1-{mode}-final-binding.json')
        assert proof['exit_code'] == 0 and proof['source_unchanged'] and proof['source_git_sha256'] == source
        assert historical(proof['head'],source) == source
        assert proof['driver_sha256'] == digest(BASE/'审计/run_regression.py')
        log = REGRESS/f'typed-history-v1-{mode}-final.log'; assert proof['log_sha256'] == digest(log)
        if phrase: assert phrase in log.read_text()
        if mode == 'browser':
            assert proof['runtime_matches'] and proof['optional_e2e_flags_cleared']
            assert '16 skipped' in log.read_text()
    cases = {c['id']:c for c in read(CASES)['cases']}
    control = read(CONTROLS/'v1/controlled-summary.json')
    assert control['completed'] and control['actual_SDK_trials'] == 29 and control['scripted_model_interface_attempts'] == 56
    assert control['native_calls'] == 0 and control['gold_poison_model_inputs_unchanged']
    assert control['actual_SDK_turns'] == 66 and control['actual_query_turns'] == 37
    assert historical(control['head'],source) == source
    SQL_count = 0
    for row in control['groups']:
        folder = CONTROLS/'v1'/row['folder']; receipt = read(folder/'receipt.json')
        for key,text in [('raw_generation_score',next((c['raw_reply'] for c in receipt['actual_model_interface_calls'] if c['role']=='generation'),None)),
                         ('final_reply_score',receipt['ordinary_result']['reply'])]:
            score = independent_score(text,receipt['expected_registered_after_execution'])
            assert all(score[k] == receipt[key][k] for k in ('format_valid','parsed','field_checks','task_correct'))
        SQL_count += inspect_observations(folder,receipt,cases[receipt['case']],receipt['arm'])
    assert SQL_count == 66
    original = read(CONTROLS/'v1/active-neutral-verified_snapshot_history/receipt.json')
    poisoned = read(CONTROLS/'v1/post-execution-gold-poison/receipt.json')
    for key in ('messages','options'):
        assert [c[key] for c in original['actual_model_interface_calls']] == [c[key] for c in poisoned['actual_model_interface_calls']]
    expected = cases['active-neutral']['expected']; good = json.dumps(expected)
    assert independent_score(good,expected)['task_correct']
    for bad in ('prefix '+good,'```json\n'+good+'\n```','{"mail_sms_phone_sent":false,'+good[1:],
            json.dumps(expected|{'observation_source_message_id':True}),json.dumps(expected|{'client_ack_in_observation':0}),
            json.dumps(expected|{'mail_sms_phone_sent':0}),json.dumps(expected|{'user_name_from_title':float('nan')})):
        assert not independent_score(bad,expected)['format_valid']
    assert read(RUNTIME) == capture_runtime()
    weights = read(WEIGHTS); assert weights['model_constructions'] == weights['native_inference_calls'] == 0
    assert weights['registry_sha256'] == digest(REGISTRY) and len(weights['models']) == 2
    assert weights['native_runtime_sha256'] == digest(RUNTIME)
    for short in ('4b','14b'):
        meta = read(WORK/(short+'-template-metadata.json'))
        assert meta['template_sha256'] == digest(WORK/(short+'-embedded-chat-template.jinja'))
        assert meta['model_construction'] is False and meta['native_inference_calls'] == 0
    sse = read(WORK/'sse-controlled-v1.json')
    assert sse['verified'] and sse['native_or_GPU_calls'] == 0 and len(sse['SDK_events']) == 3
    assert sse['probe_sha256'] == digest(BASE/'审计/probe_sse_collector.py')
    assert sse['sampler_sha256'] == digest(BASE/'审计/native_common.py')
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {}
    for p in (BASE/'审计').glob('*.py'):
        compile(p.read_text(),str(p),'exec'); names[p.name] = module.undefined_globals(p.read_text(),str(p))
    assert all(not values for values in names.values()),names
    for required in ('sample_history.py','controlled_history.py','native_common.py','prepare_native.py','inspect_templates.py',
                     'run_native.py','verify_native.py','rerender_native_templates.py','freeze_native.py','admit_native.py'):
        assert (BASE/'审计'/required).is_file()
    negative = WORK/'negative-cli-inputs'; assert not negative.exists(); negative.mkdir()
    path = WORK/'4b-freeze-v1.json'; marker = WORK/'4b-freeze-v1-retirement.json'
    target = BASE/'实验/4b-development-v1'; wrong_target = BASE/'实验/unregistered-development'
    assert not path.exists() and not marker.exists() and not target.exists() and not wrong_target.exists()
    baseline = {'registration_version':1,'model_id':'qwen3-4b-q4_k_m','output_tag':'4b-development-v1',
        'partition':'development','protected_authorized':False,'repetitions':3,'max_native_calls':146,
        'protocol_sha256':digest(PROTOCOL),'registry_sha256':digest(REGISTRY),
        'runtime_sha256':digest(RUNTIME),'weights_sha256':digest(WEIGHTS),'source_ref':'deliberately-unadmitted-fixture','sha256':{}}
    checks = [('wrong-sha',{},'C48 descriptor SHA differs'),
        ('protected-true',{'protected_authorized':True},'authorization differs'),
        ('protected-zero',{'protected_authorized':0},'authorization differs'),
        ('protected-null',{'protected_authorized':None},'authorization differs'),
        ('version-bool',{'registration_version':True},'authorization differs'),
        ('repetitions-bool',{'repetitions':True},'authorization differs'),
        ('repetitions-float',{'repetitions':3.0},'authorization differs'),
        ('native-cap-bool',{'max_native_calls':True},'authorization differs'),
        ('native-cap-float',{'max_native_calls':146.0},'authorization differs'),
        ('wrong-model',{'model_id':'qwen3-14b-q4_k_m'},'authorization differs'),
        ('wrong-output-tag',{'output_tag':'14b-development-v1'},'authorization differs'),
        ('wrong-output-path',{},'model-specific C48 development output required'),
        ('wrong-runtime',{'runtime_sha256':'0'*64},'native identity receipt changed'),
        ('wrong-weights',{'weights_sha256':'0'*64},'native identity receipt changed'),
        ('wrong-protocol',{'protocol_sha256':'0'*64},'protocol or registry changed'),
        ('wrong-registry',{'registry_sha256':'0'*64},'protocol or registry changed'),
        ('unfrozen-source',{},'current frozen input bytes changed'),
        ('retired-fixture',{},'descriptor retired')]
    attempts = []
    try:
        for label,changes,message in checks:
            path.write_text(json.dumps(baseline|changes,indent=2)+'\n')
            if label == 'retired-fixture': marker.write_text('{"scope":"deliberate CPU-only retirement marker"}\n')
            expected_sha = '0'*64 if label == 'wrong-sha' else digest(path)
            actual_target = wrong_target if label == 'wrong-output-path' else target
            argv = [sys.executable,str(BASE/'审计/run_native.py'),'--freeze',str(path),
                '--expected-freeze-sha256',expected_sha,'--model','qwen3-4b-q4_k_m','--output',str(actual_target)]
            result = subprocess.run(argv,cwd=ROOT,text=True,capture_output=True)
            assert result.returncode != 0 and message in result.stderr and not target.exists() and not wrong_target.exists(),(label,result.stderr)
            fixture = negative/(label+'.json'); path.replace(fixture)
            if marker.exists(): marker.replace(negative/(label+'-retirement.json'))
            attempts.append({'label':label,'argv':argv,'fixture':str(fixture.relative_to(ROOT)),
                'fixture_sha256':digest(fixture),'expected_rejection':message,'returncode':result.returncode,
                'stdout':result.stdout,'stderr':result.stderr,'provider_output_created':False})
    finally:
        if path.exists(): path.replace(negative/'unfinished-fixture.json')
        if marker.exists(): marker.replace(negative/'unfinished-retirement.json')
    (negative/'CLI-rejections.json').write_text(json.dumps(attempts,ensure_ascii=False,indent=2)+'\n')
    assert len(attempts) == 18 and snapshot() == source
    proof = {'admitted':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'source_sha256':source,'current_software_inputs':len(source),
        'current_scripted_SDK_trials':29,'SQL_dumps_reconstructed':SQL_count,
        'CPU_query_turns':37,'CPU_ordinary_turns':29,'gold_poison_full_model_inputs_unchanged':True,
        'model_constructions':0,'native_inference_calls':0,'installed_libraries':54,'weights':2,
        'same_client_SSE_control_verified':True,'negative_CLI_attempts':len(attempts),
        'negative_CLI_sha256':digest(negative/'CLI-rejections.json'),'undefined_globals':names,
        'scope':'future separately frozen registered development only; no candidate/default/semantic promotion'}
    destination.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print('C48 admission:484 source/Git;29CPU trials/66SQL;54libraries/2weights;SSE;18CLI rejections;0 model construction')


if __name__ == '__main__': main()

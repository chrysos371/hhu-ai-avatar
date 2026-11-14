"""Admit committed source, CPU, old software, runtime and actual rejecting CLIs."""
import copy
from collections import Counter
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from native_common import ROOT,BASE,WORK,CASES,PROTOCOL,REGISTRY,RUNTIME,WEIGHTS,read,digest,historical,capture_runtime,protocol_check
from source_identity import snapshot,PRIOR
from verify_observations import inspect_observations
from verify_native import registered_order
from run_native import require_trial_transport


def main():
    output = WORK/'admission.json'; assert not output.exists()
    protocol = protocol_check(); source = snapshot()
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    assert historical(head,source) == source
    for kind,phrase in [('python','2537 passed, 1 skipped'),('frontend','195 passed'),('build',None),('browser','19 passed')]:
        binding = PRIOR/'工作目录/002-当前软件与浏览器'/('minimal-history-v1-'+kind+'-final-binding.json')
        data = read(binding); log = binding.with_name('minimal-history-v1-'+kind+'-final.log')
        assert data['exit_code'] == 0 and data['source_unchanged'] and data['log_sha256'] == digest(log)
        assert data['source_git_sha256'] == {k:v for k,v in source.items() if not k.startswith('evals/interaction/cycle-50/')}
        if phrase: assert phrase in log.read_text()
        if kind=='browser': assert data['runtime_matches'] and '16 skipped' in log.read_text()
    cases = {c['id']:c for c in read(CASES)['cases']}
    cpu = BASE/'审计/工作目录/003-受控实模管线/v1'
    summary = read(cpu/'controlled-summary.json'); assert summary['completed'] and summary['native_calls']==0
    assert summary['actual_SDK_trials']==41 and summary['oracle_and_review_axes_poison_model_inputs_identical']
    sql = 0
    for row in summary['groups']:
        receipt = read(cpu/row['folder']/'receipt.json')
        sql += inspect_observations(cpu/row['folder'],receipt,cases[row['case']],row['arm'])
    assert sql == summary['SQL_dumps_reconstructed'] == 88
    positive = read(cpu/summary['groups'][0]['folder']/'receipt.json')
    poison = read(cpu/'oracle-poison/receipt.json')
    assert [c['messages'] for c in positive['actual_model_interface_calls']] == [c['messages'] for c in poison['actual_model_interface_calls']]
    assert [c['options'] for c in positive['actual_model_interface_calls']] == [c['options'] for c in poison['actual_model_interface_calls']]
    rejected_source_faults = []
    for field in ('source','query_reply','route'):
        receipt = copy.deepcopy(positive); q = receipt['query_observations'][0]['result']
        if field=='source': q['reminder_query']['source_message_id'] += 20
        elif field=='query_reply': q['reply'] += '已发送'
        else: q['reminder_query']['route'] = 'read_policy'
        try: inspect_observations(cpu/summary['groups'][0]['folder'],receipt,cases[positive['case']],positive['arm'])
        except AssertionError: rejected_source_faults.append(field)
        else: raise AssertionError('independent source fault accepted: '+field)
    transport = {}
    for name in (summary['groups'][0]['folder'],'cognition_error','generation_error','unavailable','empty_generation'):
        try: require_trial_transport(read(cpu/name/'receipt.json'))
        except RuntimeError: transport[name] = 'stop'
        else: transport[name] = 'continue'
    assert list(transport.values()).count('stop')==3 and list(transport.values()).count('continue')==2
    first_positions = []
    for repetition in range(1,4):
        order = registered_order(cases,protocol,repetition)
        first = Counter(arm for _,arm in order[::3]); assert sorted(first.values())==[4,4,4]
        first_positions.append(dict(first))
    for index in range(12):
        assert len({registered_order(cases,protocol,r)[3*index][1] for r in range(1,4)}) == 3
    assert capture_runtime() == read(RUNTIME)
    weights = read(WEIGHTS)
    assert weights['registry_sha256']==digest(REGISTRY) and weights['native_runtime_sha256']==digest(RUNTIME)
    assert weights['model_constructions']==weights['native_inference_calls']==0
    for model in weights['models']: assert digest(model['path']) == model['sha256']
    for short in ('4b','14b'):
        meta=read(WORK/(short+'-template-metadata.json'))
        assert meta['template_sha256']==digest(WORK/(short+'-embedded-chat-template.jinja'))
        assert meta['model_construction'] is False and meta['native_inference_calls']==0
    sse=read(WORK/'sse-controlled-v1.json')
    assert sse['verified'] and sse['native_or_GPU_calls']==0 and sse['sampler_sha256']==digest(BASE/'审计/native_common.py')
    # Deliberately incomplete descriptor: even non-schema failures cannot construct a model.
    descriptor=WORK/'4b-freeze-v1.json'; assert not descriptor.exists()
    experiment=BASE/'实验/4b-development-v1'; assert not experiment.exists()
    negative=WORK/'negative-cli-inputs'; negative.mkdir()
    template={'registration_version':1,'model_id':'qwen3-4b-q4_k_m','output_tag':'4b-development-v1',
        'partition':'development','protected_authorized':False,'repetitions':3,'max_native_calls':218,
        'protocol_sha256':digest(PROTOCOL),'registry_sha256':digest(REGISTRY),
        'runtime_sha256':digest(RUNTIME),'weights_sha256':digest(WEIGHTS),'sha256':{},'source_ref':head}
    changes=[('version_bool','registration_version',True),('version_zero','registration_version',0),
        ('protected_true','protected_authorized',True),('protected_null','protected_authorized',None),
        ('partition_protected','partition','protected'),('reps_bool','repetitions',True),('reps_float','repetitions',3.0),
        ('cap_bool','max_native_calls',True),('cap_float','max_native_calls',218.0),
        ('old_cap','max_native_calls',326),('model','model_id','qwen3-14b-q4_k_m'),
        ('output_tag','output_tag','other'),('protocol','protocol_sha256','0'*64),
        ('registry','registry_sha256','0'*64),('runtime','runtime_sha256','0'*64),('weights','weights_sha256','0'*64),
        ('unfrozen_source','sha256',{}),('descriptor_SHA',None,None)]
    CLI=[]
    try:
        for name,field,value in changes:
            data=copy.deepcopy(template)
            if field is not None: data[field]=value
            descriptor.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            (negative/(name+'.json')).write_bytes(descriptor.read_bytes())
            expected='0'*64 if name=='descriptor_SHA' else digest(descriptor)
            command=[sys.executable,str(BASE/'审计/run_native.py'),'--freeze',str(descriptor),
                '--expected-freeze-sha256',expected,'--model','qwen3-4b-q4_k_m','--output',str(experiment)]
            completed=subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
            assert completed.returncode != 0 and not experiment.exists()
            assert 'ValueError: C50' in completed.stderr,completed.stderr
            CLI.append({'name':name,'argv':command,'returncode':completed.returncode,'stdout':completed.stdout,'stderr':completed.stderr,'output_created':False})
    finally: descriptor.unlink(missing_ok=True)
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker); module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names={p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not n for n in names.values()),names
    old_items=0
    for number in range(3,50):
        cycle=BASE.parent/f'cycle-{number:02}';seal=read(cycle/'审计/证据清单.json')
        assert all(digest(cycle/n)==sha for n,sha in seal.items());old_items+=len(seal)
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json';seal=read(migration)
    assert all(digest(migration.parent/n)==sha for n,sha in seal.items());old_items+=len(seal)
    assert old_items==11143 and snapshot()==source
    result={'admitted':True,'head':head,'source_sha256':source,'software_inputs_reused_unchanged':489,
        'registered_plus_software_inputs':492,'previous_complete_regression_reused':True,
        'SQL_dumps_reconstructed':sql,'CPU_trials':41,'source_faults_rejected':rejected_source_faults,
        'transport_stop_controls':transport,'first_arm_positions':first_positions,'negative_CLI_attempts':len(CLI),
        'CLI_attempts':CLI,'old_seals_including_migration':48,'old_items':old_items,
        'undefined_globals':names,'model_constructions':0,'native_inference_calls':0,
        'verifier_sha256':digest(Path(__file__)),'no_semantic_or_production_approval':True}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C50 admitted:489 unchanged software+3 registered inputs;88 CPU SQL;3 source faults;18 actual CLI refusals;48old/11143;0 model construction')


if __name__ == '__main__': main()

"""Reconcile v1 retirement, v2 controls/software and actual stage-flag CLI gates."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from native_common import ROOT,BASE,WORK,REGRESS,CONTROLS,RUNTIME,PROTOCOL,CONTRACT,REGISTRY,read,digest,historical


def write(path,value):
    assert not path.exists();path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def main():
    output=WORK/'native-admission.json';assert not output.exists()
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    scripts={str(p.relative_to(ROOT)):p for p in (BASE/'审计').glob('*.py')}
    names={name:module.undefined_globals(p.read_text(),name) for name,p in scripts.items()}
    assert all(not found for found in names.values()),names
    contract=read(CONTRACT);protocol=read(PROTOCOL)
    assert contract['version']==protocol['registration_version']==2
    assert len(protocol['development_cases'])==24 and len(protocol['protected_cases'])==18
    old=BASE/'审计/工作目录/001-双向目标与直接路由调查'
    retirement=read(old/'v1-registration-retirement.json')
    assert retirement['native_calls']==0 and retirement['CPU_failure_log_sha256']==digest(old/'service-first.log')
    assert all(digest(ROOT/n)==sha for n,sha in retirement['old_material_sha256'].items())
    assert contract['supersedes_CPU_only_v1']['retirement_sha256']==digest(old/'v1-registration-retirement.json')
    first=read(old/'service-first-source.json');fixed=read(old/'service-v2-fixed-source.json')
    assert historical('f85cab1a',first['source_sha256'])==first['source_sha256']
    assert historical('1eee4f02',fixed['source_sha256'])==fixed['source_sha256']
    assert '1 failed, 270 passed' in (old/'service-first.log').read_text()
    assert '273 passed' in (old/'service-v2-fixed.log').read_text()
    assert digest(old/'contract-v1.json')==first['source_sha256'][str(CONTRACT.relative_to(ROOT))]
    assert digest(old/'protocol-v1.json')==first['source_sha256'][str(PROTOCOL.relative_to(ROOT))]
    assert read(old/'protocol-v1.json')['protected_cases']==protocol['protected_cases']
    assert read(old/'protocol-v1.json')['development_cases']==protocol['development_cases'][:22]
    modes={}
    for mode in ('python','frontend','build','browser'):
        binding=REGRESS/f'dispatch-v2-{mode}-final-binding.json';d=read(binding)
        assert d['exit_code']==0 and d['source_unchanged'] and len(d['source_git_sha256'])==460
        assert historical(d['head'],d['source_git_sha256'])==d['source_git_sha256']
        assert all(digest(ROOT/n)==sha for n,sha in d['source_git_sha256'].items())
        assert d['log_sha256']==digest(REGRESS/f'dispatch-v2-{mode}-final.log')
        if mode=='browser':assert d['runtime_matches']
        modes[mode]=digest(binding)
    assert '2290 passed, 1 skipped' in (REGRESS/'dispatch-v2-python-final.log').read_text()
    controls=[]
    for path in sorted(CONTROLS.glob('*/evaluation.json')):
        d=read(path);assert d['verified'] and d['native_calls']==0
        assert historical(d['head'],d['source_sha256'])==d['source_sha256']
        assert all(digest(ROOT/n)==sha for n,sha in d['source_sha256'].items())
        controls.append({'mode':path.parent.name,'head':d['head'],'evaluation_sha256':digest(path)})
    summary=read(CONTROLS/'controlled-summary.json')
    assert summary['groups']==13 and summary['scripted_model_attempts']==25 and summary['SQL_dumps_reconstructed']==60
    first_pair=read(old/'paired-first-diagnosis.json')
    assert historical('406c09d1',first_pair['collector_source_sha256_reconstructed'])==first_pair['collector_source_sha256_reconstructed']
    assert first_pair['SQL_dumps_reconstructed']==48 and first_pair['scripted_model_used_rows']==20 and first_pair['new_scripted_model_attempts']==0
    source_name=str((BASE/'审计/controlled_dispatch.py').relative_to(ROOT))
    previous=subprocess.check_output(['git','show','406c09d1:'+source_name],cwd=ROOT,text=True)
    assert previous.replace("{'model_policy_grounded':15,'source_dispatch':24}","{'model_policy_grounded':19,'source_dispatch':24}")==(ROOT/source_name).read_text()
    sse=read(WORK/'sse-controlled-current.json')
    assert sse['verified'] and sse['sampler_sha256']==digest(BASE/'审计/native_common.py')
    assert sse['probe_sha256']==digest(BASE/'审计/probe_sse_collector.py')
    assert len(read(RUNTIME)['files_sha256'])==54
    command=[sys.executable,str(BASE/'审计/run_dispatch.py'),'--freeze',str(RUNTIME),
        '--expected-freeze-sha256','wrong-descriptor','--partition','development',
        '--output',str(BASE/'实验/should-not-exist')]
    r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert r.returncode!=0 and 'C44 descriptor changed' in r.stderr and not (BASE/'实验/should-not-exist').exists()
    (WORK/'wrong-descriptor.log').write_text(r.stdout+r.stderr)
    flags=[]
    for index,(partition,flag) in enumerate([('development',True),('development',None),('development',0),
        ('protected',False),('protected',None),('protected',1)]):
        body={'scope':protocol['scope'],'backend':'cuda','model_id':'qwen3-4b-q4_k_m','execution_authorized':True,
            'allowed_partition':partition,'registration_version':2,'protocol_sha256':digest(PROTOCOL),
            'registry_sha256':digest(REGISTRY),'case_ids':[c['id'] for c in protocol[partition+'_cases']],
            'repetitions':protocol['sampling'][partition+'_repetitions'],
            'max_native_calls':protocol['sampling'][partition+'_max_native_calls'],
            'protected_execution_authorized':flag,'source_ref':'not-an-executable-freeze','sha256':{}}
        path=WORK/f'preflight-stage-{index}.json';write(path,body)
        output_path=BASE/'实验'/f'should-not-exist-stage-{index}'
        cmd=[sys.executable,str(BASE/'审计/run_dispatch.py'),'--freeze',str(path),
            '--expected-freeze-sha256',digest(path),'--partition',partition,'--output',str(output_path)]
        result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
        assert result.returncode!=0 and 'C44 explicit partition authorization inconsistent' in result.stderr
        assert not output_path.exists()
        log=WORK/f'preflight-stage-{index}.log';log.write_text(result.stdout+result.stderr)
        flags.append({'partition':partition,'flag':flag,'actual_CLI':cmd,'exit':result.returncode,
            'rejected_before_output_or_provider':True,'log_sha256':digest(log)})
    write(WORK/'preflight-stage-controls.json',{'verified':True,'native_calls':0,'cases':flags})
    data={'verified':True,'scope':'only later exact v2 frozen development; candidate0model, no protected or default authorization',
        'new_native_calls':0,'protected_authorized':False,'default_enabled':False,'registration_version':2,
        'current_software_inputs':460,'full_python':'2290 passed/1 skipped','frontend':'192 passed','browser':'18 passed/16 optional skipped',
        'scripted_model_attempts_current':25,'actual_SQL_branch_controls_current':60,'actual_status_SELECTs_current':11,
        'retired_first_pair_raw_branches':48,'retired_first_pair_model_used_rows':20,'retired_first_pair_SQL_reconstructed':48,
        'controlled_groups':controls,'regression_binding_sha256':modes,'runtime_sha256':digest(RUNTIME),
        'SSE_control_sha256':digest(WORK/'sse-controlled-current.json'),
        'source_contract_sha256':digest(CONTRACT),'protocol_sha256':digest(PROTOCOL),
        'stage_flag_controls_sha256':digest(WORK/'preflight-stage-controls.json'),'stage_flag_negative_cases':6,
        'actual_wrong_SHA_CLI':command,'wrong_SHA_exit':r.returncode,'no_provider_or_output_created':True,
        'undefined_globals':names,'names_checker_sha256':digest(checker),
        'source_sha256':{name:digest(path) for name,path in scripts.items()}}
    write(WORK/'native-admission.json',data)
    print('C44 v2 development preflight:460 source/13 controls/60SQL +48 retired/54libraries/sameSDK SSE/6 actual stage flag rejections;0 native')


if __name__=='__main__':main()

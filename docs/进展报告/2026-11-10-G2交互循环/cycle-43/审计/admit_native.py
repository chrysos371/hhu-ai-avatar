"""Reconcile current CPU/software controls before admitting a frozen native stage."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from native_common import ROOT,BASE,WORK,REGRESS,CONTROLS,RUNTIME,PROTOCOL,CONTRACT,read,digest,historical


def main():
    output=WORK/'native-admission.json';assert not output.exists()
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    scripts={str(p.relative_to(ROOT)):p for p in (BASE/'审计').glob('*.py')}
    names={name:module.undefined_globals(p.read_text(),name) for name,p in scripts.items()}
    assert all(not found for found in names.values()),names
    command=[sys.executable,str(BASE/'审计/run_catalogues.py'),'--freeze',str(RUNTIME),
        '--expected-freeze-sha256','wrong-descriptor','--partition','development',
        '--output',str(BASE/'实验/should-not-exist')]
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert result.returncode!=0 and 'C43 descriptor changed' in result.stderr
    assert not (BASE/'实验/should-not-exist').exists()
    (WORK/'wrong-descriptor.log').write_text(result.stdout+result.stderr)
    modes={}
    for mode in ('python','frontend','build','browser'):
        binding=REGRESS/f'policy-evidence-{mode}-final-binding.json';d=read(binding)
        assert d['exit_code']==0 and d['source_unchanged'] and len(d['source_git_sha256'])==455
        assert historical(d['head'],d['source_git_sha256'])==d['source_git_sha256']
        assert all(digest(ROOT/k)==v for k,v in d['source_git_sha256'].items())
        assert d['log_sha256']==digest(REGRESS/f'policy-evidence-{mode}-final.log')
        if mode=='browser':assert d['runtime_matches']
        modes[mode]=digest(binding)
    assert '2239 passed, 1 skipped' in (REGRESS/'policy-evidence-python-final.log').read_text()
    controls=[]
    for path in sorted(CONTROLS.glob('*/evaluation.json')):
        d=read(path);assert d['verified'] and d['native_calls']==0
        assert historical(d['head'],d['source_sha256'])==d['source_sha256']
        assert all(digest(ROOT/k)==v for k,v in d['source_sha256'].items())
        controls.append({'mode':path.parent.name,'head':d['head'],'evaluation_sha256':digest(path)})
    summary=read(CONTROLS/'controlled-summary.json')
    assert summary['groups']==10 and summary['scripted_model_attempts']==32 and summary['SQL_dumps_reconstructed']==41
    sse=read(WORK/'sse-controlled-current.json')
    assert sse['verified'] and sse['sampler_sha256']==digest(BASE/'审计/native_common.py')
    assert sse['probe_sha256']==digest(BASE/'审计/probe_sse_collector.py')
    assert len(read(RUNTIME)['files_sha256'])==54
    data={'verified':True,'scope':'only later exact frozen development descriptor; no protected or default-product authorization',
        'new_native_calls':0,'protected_authorized':False,'default_enabled':False,
        'current_software_inputs':455,'full_python':'2239 passed/1 skipped','frontend':'192 passed',
        'browser':'18 passed/16 optional skipped','scripted_model_attempts':32,'actual_SQL_branch_controls':41,
        'actual_status_SELECTs':5,'controlled_groups':controls,'regression_binding_sha256':modes,
        'runtime_sha256':digest(RUNTIME),'SSE_control_sha256':digest(WORK/'sse-controlled-current.json'),
        'source_contract_sha256':digest(CONTRACT),'protocol_sha256':digest(PROTOCOL),
        'actual_CLI':command,'CLI_exit':result.returncode,'no_output_or_provider_created':True,
        'undefined_globals':names,'names_checker_sha256':digest(checker),
        'source_sha256':{name:digest(p) for name,p in scripts.items()}}
    output.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print('C43 development preflight:455 current/10 groups/41 SQL/54 libraries/same SDK SSE/'+str(len(scripts))+' scripts;0 native')


if __name__=='__main__':main()

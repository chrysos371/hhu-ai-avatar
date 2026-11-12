"""Advance completed CPU/software phase to a separately frozen development run."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from native_common import ROOT,BASE,WORK,REGRESS,CONTROLS,CONTRACT,PROTOCOL,RUNTIME,read,digest,historical


def main():
    admission=WORK/'native-admission.json'
    assert not admission.exists()
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    scripts={str(p.relative_to(ROOT)):p for p in (BASE/'审计').glob('*.py')}
    found={name:module.undefined_globals(p.read_text(),name) for name,p in scripts.items()}
    assert all(not v for v in found.values()),found
    command=[sys.executable,str(BASE/'审计/run_pairs.py'),'--freeze',str(RUNTIME),
        '--expected-freeze-sha256','wrong-descriptor','--partition','development',
        '--output',str(BASE/'实验/should-not-exist')]
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert result.returncode!=0 and 'C41 descriptor changed' in result.stderr and not (BASE/'实验/should-not-exist').exists()
    old_handoff=digest(WORK/'handoff-admission.json')
    (WORK/'handoff-wrong-sha.log').write_text(result.stdout+result.stderr)
    (WORK/'handoff-admission.json').write_text(json.dumps({'verified':True,
        'scope':'bounded global names + actual complete controller CLI wrong-SHA rejection, not full native execution',
        'new_native_calls':0,'source_sha256':{name:digest(p) for name,p in scripts.items()},
        'previous_handoff_sha256':old_handoff,'undefined_globals':found,'checker_sha256':digest(checker),
        'actual_command':command,'exit_code':result.returncode,'provider_or_output_created':False},
        ensure_ascii=False,indent=2)+'\n')
    for mode in ('python','frontend','build','browser'):
        d=read(REGRESS/f'source-read-{mode}-final-binding.json')
        assert d['exit_code']==0 and d['source_unchanged'] and len(d['source_git_sha256'])==445
        assert historical(d['head'],d['source_git_sha256'])==d['source_git_sha256']
        assert all(digest(ROOT/k)==v for k,v in d['source_git_sha256'].items())
        assert d['log_sha256']==digest(REGRESS/f'source-read-{mode}-final.log')
        if mode=='browser':assert d['runtime_matches']
    assert '2138 passed, 1 skipped' in (REGRESS/'source-read-python-final.log').read_text()
    controls=[]
    for mode in ('repair','repeat','plain','error','source-before','source-after','gold-poison','malformed'):
        d=read(CONTROLS/mode/'evaluation.json')
        assert d['verified'] and d['native_or_GPU_calls']==0
        hashes=d['source_sha256'];assert all(digest(ROOT/k)==v for k,v in hashes.items())
        anchor='a9fb0850' if mode=='repair' else d['head']
        assert historical(anchor,hashes)==hashes
        controls.append({'mode':mode,'actual_recorded_head':d['head'],
            'exact_source_history_anchor':anchor,'evaluation_sha256':digest(CONTROLS/mode/'evaluation.json')})
    summary=read(CONTROLS/'controlled-summary.json')
    assert summary['scripted_model_attempts']==39 and summary['SQL_dumps_reconstructed']==72
    assert read(WORK/'sse-controlled-current.json')['sampler_sha256']==digest(BASE/'审计/native_common.py')
    data={'verified':True,'new_native_calls':0,
        'scope':'advance preregistered CPU-only service registration to frozen native development with unchanged algorithm/cases',
        'development_stage_authorized_after_source_freeze':True,
        'supersedes_CPU_registration_only_for_frozen_development':True,
        'source_contract_registration_native_flag':read(CONTRACT)['native_execution_authorized'],
        'protected_stage_authorized':False,'default_product_enabled':False,
        'full_python':'2138 passed/1 skipped','frontend':'192 passed','browser':'18 passed/16 optional skipped',
        'current_software_inputs':445,'scripted_model_attempts':39,'scripted_model_exceptions':1,
        'actual_SQL_branch_controls':72,'status_business_SELECTs_in_controls':18,
        'controlled_groups':controls,'runtime_sha256':digest(RUNTIME),
        'handoff_sha256':digest(WORK/'handoff-admission.json'),
        'SSE_control_sha256':digest(WORK/'sse-controlled-current.json'),
        'source_contract_sha256':digest(CONTRACT),'protocol_sha256':digest(PROTOCOL),
        'admission_driver_sha256':digest(Path(__file__))}
    assert data['source_contract_registration_native_flag'] is False
    admission.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    (WORK/'阶段执行授权.md').write_text('''# C41 阶段执行授权

最初trusted-local-read-contract的native_execution_authorized:false保留其CPU登记阶段状态，不能直接用它启动模型。本次在2138/1完整Python、192前端、18/16浏览器、445源、39脚本尝试/72 SQL分支、54库身份、当前SSE正控及实际CLI拒绝门槛通过后，按计划推进到独立冻结的开发实验。

当前准入仅授予“后续精确源码冻结描述符匹配时执行development”的权限；未改动材料、算法或评分门槛来凑通过。protected仍未授权，必须开发结果独立复核且全部门槛通过后另立描述符/准入。默认产品不启用。用户持续目标已授权自主研究及按实际空闲GPU推进，此处是实验阶段状态更新，不请求新的用户确认。

[native-admission.json](native-admission.json)记录当前门槛和对初期CPU-only阶段的明确替代；runner同时检查准入与冻结字节，不能仅靠修改旧bool取得执行权。旧SSE绑定因模块新增冻结输入而被拒、首handoff和重建旧字节保留，不伪称旧绑定覆盖新源。
''')
    print('C41 development admission verified:445current;2138/1,192,18/16;39scripted/72SQL;54libraries;'+str(len(scripts))+' scripts;0native')


if __name__=='__main__':main()

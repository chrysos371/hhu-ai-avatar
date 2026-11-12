"""Build one immutable C26 execution descriptor only from passed, committed inputs."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

CYCLE=Path(__file__).resolve().parents[1];ROOT=CYCLE.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import evaluate_native_output_audit as audit


def build():
    binding_path=CYCLE/'审计/工作目录/002-当前默认采样冻结/full-final-python-binding.json'
    binding=json.loads(binding_path.read_text())
    if not binding['completed'] or binding['exit_code']!=0 or not binding['source_unchanged']:
        raise ValueError('Wait for passed source-bound final Python regression')
    for name,value in binding['source_sha256'].items():
        if sha256((ROOT/name).read_bytes()).hexdigest()!=value:raise ValueError('Source changed after full regression: '+name)
    protocol_path=ROOT/'evals/interaction/cycle-26/current-default-model-scale-protocol.json'
    protocol=json.loads(protocol_path.read_text());cases=protocol['cases']
    original=json.loads((ROOT/'evals/interaction/cycle-19/capability-output-protocol.json').read_text())
    assert cases==[c for c in original['cases'] if c['partition']=='development']
    assert len(cases)==12 and sum(len(c['turns']) for c in cases)==20
    registry,registry_sha,registry_path,_=audit.protocol_registry(protocol)
    names=set(binding['source_sha256'])|set(audit.fingerprint(protocol_path))|{
        'scripts/run_native_output_models.py','evals/interaction/cycle-15/native-output-protocol.json',
        'evals/interaction/cycle-19/capability-output-protocol.json',str(Path(__file__).resolve().relative_to(ROOT))}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    hashes={}
    for name in sorted(names):
        value=sha256((ROOT/name).read_bytes()).hexdigest()
        committed=sha256(subprocess.check_output(['git','show',head+':'+name],cwd=ROOT)).hexdigest()
        if value!=committed:raise ValueError('Commit input before freezing: '+name)
        hashes[name]=value
    value={'version':1,'scope':'native_current_defaults_model_scale','candidate':'none','execution_authorized':True,
        'allowed_partition':'development','provider_backend':'cuda','source_ref':head,
        'protocol':str(protocol_path.relative_to(ROOT)),'models_registry':str(registry_path.relative_to(ROOT)),
        'registry_sha256':registry_sha,'models':[m['model_id'] for m in registry['models']],
        'case_ids':[c['id'] for c in cases],'case_count':12,'turn_count':20,'sha256':hashes,
        'full_python_head':binding['head'],'full_python_binding_sha256':sha256(binding_path.read_bytes()).hexdigest(),
        'prospective_execution_authorized':False,'production_activation_authorized':False,
        'wall_clock_experiment_deadline':None,'asset_note':'Model binaries are independently hash-verified by the provider before GPU admission. A registered model is not proof its download completed.'}
    path=ROOT/'evals/interaction/cycle-26/current-default-development-freeze.json'
    with path.open('x') as stream:stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    identity=sha256(path.read_bytes()).hexdigest()
    assert audit.verify_execution_freeze(path,identity,protocol_path)==value
    print('C26 freeze',identity,'inputs',len(hashes),'models',len(value['models']),'source',head)


if __name__=='__main__':build()

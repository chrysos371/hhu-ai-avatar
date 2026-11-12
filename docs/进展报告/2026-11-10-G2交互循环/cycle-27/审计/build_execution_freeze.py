"""Create one immutable source-atom diagnostic freeze after passing full regression."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[5]
sys.path.insert(0,str(ROOT/'scripts'))
from probe_native_evidence_plans import required_paths,verify_freeze,validate_protocol,PROTOCOL,MODELS


def digest(path):return sha256(path.read_bytes()).hexdigest()


def build():
    base=Path(__file__).resolve().parents[1];work=base/'审计/工作目录/001-来源原子与类型化计划'
    full_path=work/'full-final-python-binding.json';full=json.loads(full_path.read_text());log=work/'full-final-python.log'
    if not full['completed'] or full['exit_code']!=0 or not full['source_unchanged']:raise ValueError('Full regression not passed')
    result=re.search(r'(\d+) passed, (\d+) skipped in ([\d.]+)s',log.read_text())
    if result is None:raise ValueError('Full test result missing')
    if set(full['source_sha256'])!=required_paths():raise ValueError('Full source set differs from current runner')
    protocol=json.loads((ROOT/PROTOCOL).read_text());validate_protocol(protocol)
    source_ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    names=required_paths()|{str(Path(__file__).resolve().relative_to(ROOT)),str(full_path.relative_to(ROOT)),str(log.relative_to(ROOT))}
    inputs={}
    for name in sorted(names):
        current=digest(ROOT/name);committed=sha256(subprocess.check_output(['git','show',source_ref+':'+name],cwd=ROOT)).hexdigest()
        if current!=committed:raise ValueError('Uncommitted input: '+name)
        if name in full['source_sha256'] and current!=full['source_sha256'][name]:raise ValueError('Input changed since full test: '+name)
        inputs[name]=current
    value={'version':1,'scope':protocol['scope'],'protocol':PROTOCOL,'backend':'cuda','models':list(MODELS),
           'production_activation_authorized':False,'prospective_execution_authorized':False,'diagnostic_requests_per_model':24,
           'source_ref':source_ref,'full_python_head':full['head'],'full_python_binding_sha256':digest(full_path),
           'full_python_result':{'passed':int(result[1]),'skipped':int(result[2]),'seconds':float(result[3])},
           'atoms_are_experiment_fixtures':True,'wall_clock_experiment_deadline':None,'sha256':inputs}
    target=ROOT/'evals/interaction/cycle-27/source-atom-content-freeze.json'
    with target.open('x') as out:json.dump(value,out,ensure_ascii=False,indent=2);out.write('\n')
    identity=digest(target);verify_freeze(target,identity,MODELS[0]);print('Created immutable freeze',identity,'inputs',len(inputs),'full',value['full_python_result'])


if __name__=='__main__':build()

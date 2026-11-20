"""Real CLI refusals and explicit synthetic config guards; zero model/GPU."""
import copy
import os
from pathlib import Path
import subprocess
import sys
from execution_common import ROOT,BASE,AUDIT,ASSETS,RUN,JOBS,WORK,C54,read,sha,require,write_new,protocol_check,preparation_check
from reuse import load
from supervision import command,context,config_check,jobs,SOURCE

OUT=ASSETS/'artifacts/c55/admission-cpu-v1'
PROOF=AUDIT/'工作目录/003-冻结前执行门禁'


def main():
    require(not OUT.exists() and not RUN.exists() and not JOBS.exists() and not (WORK/'freeze-v1.json').exists(),'CPU controls before fresh freeze/run required')
    protocol_check();preparation_check();OUT.mkdir(parents=True)
    modules={name:load(name) for name in ('run_execution','verify_execution','collect_closed_group')}
    require(all(m.RUN==RUN and m.BASE==BASE for m in modules.values()),'reused mechanics bind old experiment')
    require(all(Path(m.__file__).parent==C54/'审计' for m in modules.values()),'sealed reference identity differs')
    env=os.environ.copy();env.update(PYTHONPATH=str(ROOT/'src'),CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
    frozen=str(WORK/'freeze-v1.json');zeros='0'*64
    common=['--freeze',frozen,'--expected-freeze-sha256',zeros,'--stage','base']
    cases=[('launcher_missing_freeze',['launch_stage.py',*common],1,'C55 frozen execution descriptor missing'),
        ('worker_missing_freeze',['run_execution.py',*common],1,'C55 frozen execution descriptor missing'),
        ('wrong_path',['launch_stage.py','--freeze',str(OUT/'fake.json'),*common[2:]],1,'C55 registered freeze path required'),
        ('unknown_stage',['launch_stage.py',*common[:-1],'unknown'],2,"invalid choice: 'unknown'"),
        ('wrong_seal',['freeze_execution.py','--c54-seal-sha256',zeros],1,'C55 explicit sealed C54 identity required')]
    CLI=[]
    for name,args,code,reason in cases:
        argv=[sys.executable,'-B',str(AUDIT/args[0]),*args[1:]]
        result=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True,text=True)
        require(result.returncode==code and reason in result.stderr and 'ModuleNotFoundError' not in result.stderr,'CLI refusal differs: '+name)
        write_new(PROOF/f'{name}-v1.json',{'argv':argv,'actual_returncode':result.returncode,'expected_reason':reason,'stdout':result.stdout,'stderr':result.stderr})
        CLI.append(name)
    for name in ('launch_stage','run_execution','verify_execution'):
        result=subprocess.run([sys.executable,'-B',str(AUDIT/f'{name}.py'),'--help'],cwd=ROOT,env=env,capture_output=True,text=True)
        require(result.returncode==0 and 'old_adapter' in result.stdout and 'new_adapter' in result.stdout,'normal help failed: '+name)
        write_new(PROOF/f'{name}-help-v1.json',{'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr})
    # These JSON objects test binding logic, not actual supervisor/GPU state.
    folder=OUT/'synthetic-config';folder.mkdir()
    original={'command':command('base',zeros),'cwd':str(ROOT),'context':context('base',zeros),
        'environment':{'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4'},'controller_sha256':sha(SOURCE),'created_utc':'synthetic-only'}
    jobs.write_json(folder/'config.json',original);config_check(folder,'base',zeros)
    faults=[]
    for name in ('argv','cwd','stage','freeze_sha','binding_source','controller','environment'):
        bad=copy.deepcopy(original)
        if name=='argv':bad['command'][-1]='old_adapter'
        elif name=='cwd':bad['cwd']=str(OUT)
        elif name=='stage':bad['context']['stage']='old_adapter'
        elif name=='freeze_sha':bad['context']['execution_freeze_sha256']='1'*64
        elif name=='binding_source':bad['context']['supervision_binding_sha256']='1'*64
        elif name=='controller':bad['controller_sha256']='1'*64
        else:bad['environment']['OMP_NUM_THREADS']='8'
        jobs.write_json(folder/'config.json',bad)
        try:config_check(folder,'base',zeros)
        except ValueError as error:faults.append({'fault':name,'reason':str(error)})
        else:raise ValueError('binding fault accepted: '+name)
    jobs.write_json(folder/'config.json',original);config_check(folder,'base',zeros)
    require(not RUN.exists() and not JOBS.exists() and 'torch' not in sys.modules,'CPU probe entered model/run state')
    write_new(PROOF/'admission-v1.json',{'passed':True,'probe_sha256':sha(Path(__file__)),
        'source_sha256':{p.name:sha(p) for p in AUDIT.glob('*.py')},'actual_CLI_refusals':CLI,'actual_help_processes':3,
        'synthetic_config_faults_rejected':faults,'synthetic_JSON_not_hardware':True,
        'reused_mechanics_actual_import_bound_to_fresh_C55':True,'external_root':str(OUT),
        'model_generations':0,'training_steps':0,'GPU_allocations':0,'Torch_imported':False})
    print('C55 admission:5 exact CLI refusals+3 helps;7 synthetic config faults;C55 roots;0 Torch/model/GPU')


if __name__=='__main__':main()

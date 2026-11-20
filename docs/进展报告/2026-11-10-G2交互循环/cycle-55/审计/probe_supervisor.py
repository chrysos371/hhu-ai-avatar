"""Real CPU lifecycle controls for the existing detached supervisor; no model."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[5]
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
SOURCE=ROOT/'scripts/lab/run_frozen_capability_job.py'
spec=importlib.util.spec_from_file_location('c55_existing_jobs',SOURCE)
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)
OUT=ASSETS/'artifacts/c55/supervisor-cpu-v1'
PROOF=Path(__file__).parent/'工作目录/001-独立托管控制'

def require(ok,message):
    if not ok:raise ValueError(message)

def until(folder,predicate):
    # Engineering bound only for these tiny CPU fixtures, never an experiment cutoff.
    end=time.monotonic()+15
    while time.monotonic()<end:
        state=jobs.status(folder)
        if predicate(state):return state
        time.sleep(.05)
    raise RuntimeError('CPU fixture did not reach expected state; inspect '+str(folder))

def terminal(folder):return until(folder,lambda s:s['state'] in ('completed','failed','interrupted'))
def retired(state):
    end=time.monotonic()+10
    while jobs.matches(state.get('worker')) and time.monotonic()<end:time.sleep(.05)
    require(not jobs.matches(state.get('worker')) and not jobs.matches(state.get('child')),'owned fixture process remains live')

def main():
    require(not OUT.exists(),'fresh fixture output required');OUT.mkdir(parents=True)
    controls=[]
    success=OUT/'launcher-exit';gate=OUT/'release-success'
    command=[sys.executable,'-B','-c','import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); exec("while not p.exists(): time.sleep(.05)"); print("success-once")',str(gate)]
    launcher_code='import importlib.util,json,sys; from pathlib import Path; s=importlib.util.spec_from_file_location("jobs",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(json.dumps(m.launch(json.loads(sys.argv[3]),Path(sys.argv[2]))))'
    parent=subprocess.run([sys.executable,'-B','-c',launcher_code,str(SOURCE),str(success),json.dumps(command)],capture_output=True,text=True,check=True)
    launched=json.loads(parent.stdout)
    observed=until(success,lambda s:s['child_verified_alive'])
    require(jobs.matches(observed['worker']) and observed['worker']['process_group']==observed['worker']['pid'] and observed['child']['process_group']==observed['child']['pid'],'separate session identities differ')
    require(observed['return_code'] is None and parent.returncode==0,'launcher is not child completion')
    jobs.write_json(OUT/'alive-after-launcher-exit.json',{'launcher_returncode':parent.returncode,'launcher_stdout':launched,'actual_status':observed})
    gate.touch(exist_ok=False);state=terminal(success);retired(state)
    require(state['state']=='completed' and state['return_code']==0 and (success/'experiment.log').read_text().strip()=='success-once','success terminal evidence differs')
    controls.append({'case':'launcher_exits_child_survives_success','state':state['state'],'actual_child_wait_code':state['return_code']})
    saved=(success/'config.json').read_bytes()
    try:jobs.launch(command,success)
    except FileExistsError:pass
    else:raise ValueError('duplicate launch accepted')
    require((success/'config.json').read_bytes()==saved and (success/'experiment.log').read_text().count('success-once')==1,'duplicate changed original job')
    controls.append({'case':'duplicate_job_rejected','original_unchanged':True,'executions':1})
    failure=OUT/'failure-seven';jobs.launch([sys.executable,'-B','-c','raise SystemExit(7)'],failure)
    state=terminal(failure);retired(state);require(state['state']=='failed' and state['return_code']==7,'failure code hidden')
    controls.append({'case':'nonzero_child','state':state['state'],'actual_child_wait_code':7})
    stop=OUT/'requested-stop';jobs.launch([sys.executable,'-B','-c','import time; print("owned-stop",flush=True); time.sleep(60)'],stop)
    state=until(stop,lambda s:s['child_verified_alive'] and 'owned-stop' in (stop/'experiment.log').read_text())
    unrelated=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'])
    try:
        os.kill(state['worker']['pid'],signal.SIGTERM);state=terminal(stop);retired(state)
        require(state['state']=='interrupted' and state['stop_signal']==signal.SIGTERM and state['return_code']!=0 and unrelated.poll() is None,'owned stop isolation failed')
        controls.append({'case':'requested_stop_only_owned_child','state':state['state'],'actual_child_wait_code':state['return_code'],'unrelated_alive':True})
    finally:unrelated.terminate();unrelated.wait()
    tampered=OUT/'tampered';tampered.mkdir();jobs.write_json(tampered/'config.json',{})
    supervisor=subprocess.run([sys.executable,'-B',str(SOURCE),'--worker',str(tampered),'--config-sha256','wrong'],capture_output=True,text=True,check=True)
    state=jobs.status(tampered)
    require(state['state']=='failed' and state['child'] is None and state['return_code'] is None and 'changed after launch' in state['error'],'tamper rejection did not preserve absent child')
    controls.append({'case':'changed_config_no_child','supervisor_command_exitcode':supervisor.returncode,'child_wait_code':None,'child_launched':False})
    files={str(p.relative_to(OUT)):jobs.digest(p) for p in OUT.rglob('*') if p.is_file()}
    jobs.write_json(PROOF/'lifecycle-v1.json',{'verified':True,'probe_sha256':jobs.digest(Path(__file__)),'supervisor_sha256':jobs.digest(SOURCE),'controls':controls,'external_root':str(OUT),'external_sha256':files,'model_generations':0,'training_steps':0,'GPU_allocations':0,'scope':'actual short CPU processes; not model run or independent human evaluation'})
    print('C55 CPU lifecycle:5 controls passed; real codes0/7/'+str(controls[3]['actual_child_wait_code'])+'; no model/GPU')

if __name__=='__main__':main()

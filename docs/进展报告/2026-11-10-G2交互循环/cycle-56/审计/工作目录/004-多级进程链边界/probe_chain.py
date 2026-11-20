"""CPU-only supervisor -> guarded manager -> unguarded provider-shaped child."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'scripts/lab/run_frozen_capability_job.py'
spec=importlib.util.spec_from_file_location('c56_chain_jobs',SOURCE)
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)
OUT=ASSETS/'artifacts/c56/provider-shaped-chain-cpu-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def wait_for(predicate):
    end=time.monotonic()+10
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.02)
    raise RuntimeError('Tiny CPU chain did not reach expected state')


def main():
    require(not OUT.exists(),'fresh CPU chain required');OUT.mkdir(parents=True)
    payload=OUT/'cpu_payload.py';manager=OUT/'cpu_manager.py'
    payload.write_text('''import ctypes,json,os,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGINT,signal.SIG_IGN)
signal.signal(signal.SIGTERM,signal.SIG_IGN)
libc=ctypes.CDLL(None);value=ctypes.c_int();libc.prctl(2,ctypes.byref(value),0,0,0)
Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid(),'parent':os.getppid(),'pdeath_signal':value.value}))
while True:time.sleep(.1)
''')
    manager.write_text('''import ctypes,json,os,subprocess,sys,time
from pathlib import Path
libc=ctypes.CDLL(None);value=ctypes.c_int();libc.prctl(2,ctypes.byref(value),0,0,0)
root=Path(sys.argv[1])
with (root/'cpu-child.log').open('x') as stream:
 child=subprocess.Popen([sys.executable,'-B',str(root/'cpu_payload.py'),str(root/'cpu-child-ready.json')],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
 (root/'cpu-manager-ready.json').write_text(json.dumps({'pid':os.getpid(),'parent':os.getppid(),'pdeath_signal':value.value,'child_pid':child.pid}))
 while True:time.sleep(.1)
''')
    folder=OUT/'job';jobs.launch([sys.executable,'-B',str(manager),str(OUT)],folder)
    unrelated=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'])
    identities=[]
    try:
        before=wait_for(lambda:(s if (s:=jobs.status(folder)).get('payload_argv_observed') and (OUT/'cpu-child-ready.json').exists() else None))
        m=json.loads((OUT/'cpu-manager-ready.json').read_text());p=json.loads((OUT/'cpu-child-ready.json').read_text())
        child=jobs.process(p['pid']);identities=[child,before['child'],before['worker']]
        require(m['pid']==before['child']['pid'] and m['child_pid']==p['pid'] and p['parent']==m['pid'] and all(jobs.matches(i) for i in identities),'actual CPU chain identity differs')
        require(m['pdeath_signal']==signal.SIGKILL,'manager did not inherit actual direct guard')
        os.kill(before['worker']['pid'],signal.SIGKILL)
        wait_for(lambda:not jobs.matches(before['worker']) and not jobs.matches(before['child']))
        time.sleep(.1)
        observation={'supervisor_alive':jobs.matches(before['worker']),'manager_alive':jobs.matches(before['child']),
            'grandchild_alive':jobs.matches(child),'manager_pdeath_signal':m['pdeath_signal'],
            'grandchild_pdeath_signal':p['pdeath_signal'],'unrelated_owned_control_alive':unrelated.poll() is None,
            'original_supervised_child_wait_code':jobs.status(folder)['return_code']}
        require(observation['unrelated_owned_control_alive'],'unrelated CPU control affected')
    finally:
        for identity in identities:
            if jobs.matches(identity):os.killpg(identity['pid'],signal.SIGKILL)
        for identity in identities:
            wait_for(lambda identity=identity:not jobs.matches(identity))
        unrelated.terminate();unrelated.wait()
    jobs.write_json(HERE/'chain-cpu-v1.json',{'executed':True,'probe_sha256':jobs.digest(Path(__file__)),
        'supervisor_sha256':jobs.digest(SOURCE),'guard_sha256':jobs.digest(jobs.GUARD),
        'actual_manager_ready':m,'actual_payload_ready':p,'identities_before_injection':identities,
        'observation_after_supervisor_SIGKILL':observation,'all_owned_identities_cleaned':True,
        'external_root':str(OUT),'external_sha256':{str(p.relative_to(OUT)):jobs.digest(p) for p in OUT.rglob('*') if p.is_file()},
        'model_calls':0,'training_steps':0,'GPU_allocations':0,
        'scope':'actual CPU process-chain shape;not actual native provider/GPU leak/host crash verification'})
    print('CPU chain boundary:',observation,';all owned fixture processes cleaned')


if __name__=='__main__':main()

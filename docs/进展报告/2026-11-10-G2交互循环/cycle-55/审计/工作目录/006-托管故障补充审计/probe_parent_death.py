"""Kill only a new CPU fixture supervisor; preserve unknown terminal evidence."""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'scripts/lab/run_frozen_capability_job.py'
spec=importlib.util.spec_from_file_location('c55_parent_death_fixture',SOURCE)
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)
OUT=Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/c55/parent-death-cpu-v1')


def require(ok,message):
    if not ok:raise ValueError(message)


def main():
    require(not OUT.exists(),'fresh parent-death fixture required')
    jobs.launch([sys.executable,'-B','-c','import time; print("cpu-fixture-only",flush=True); time.sleep(60)'],OUT)
    end=time.monotonic()+10
    while time.monotonic()<end:
        before=jobs.status(OUT)
        if before['child_verified_alive'] and 'cpu-fixture-only' in (OUT/'experiment.log').read_text():break
        time.sleep(.05)
    else:raise ValueError('short CPU fixture did not start')
    require(jobs.matches(before['worker']) and before['child']['process_group']==before['child']['pid'],'fixture identity differs')
    control=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'])
    child_cleanup=False
    try:
        os.kill(before['worker']['pid'],signal.SIGKILL)
        end=time.monotonic()+5
        while jobs.matches(before['worker']) and time.monotonic()<end:time.sleep(.05)
        observed=jobs.status(OUT)
        require(not observed['worker_verified_alive'],'fixture supervisor remains live')
        require(control.poll() is None,'unrelated owned CPU control was stopped')
        orphan_alive=observed['child_verified_alive']
        if jobs.matches(before['child']):os.killpg(before['child']['pid'],signal.SIGINT)
        end=time.monotonic()+10
        while jobs.matches(before['child']) and time.monotonic()<end:time.sleep(.05)
        child_cleanup=not jobs.matches(before['child'])
        require(child_cleanup,'owned fixture child cleanup failed')
    finally:
        if jobs.matches(before['worker']):os.kill(before['worker']['pid'],signal.SIGTERM)
        if jobs.matches(before['child']):os.killpg(before['child']['pid'],signal.SIGTERM)
        control.terminate();control.wait()
    jobs.write_json(HERE/'parent-death-v1.json',{'executed':True,'probe_sha256':jobs.digest(Path(__file__)),
        'supervisor_sha256':jobs.digest(SOURCE),'before':before,'after_supervisor_SIGKILL':observed,
        'supervisor_dead_child_still_alive':orphan_alive,'fixture_child_cleaned':child_cleanup,
        'child_wait_exitcode':None,'exitcode_unknown_without_original_parent_wait':True,
        'unrelated_owned_control_survived':True,'model_generations':0,'GPU_allocations':0,
        'external_root':str(OUT),'external_sha256':{p.name:jobs.digest(p) for p in OUT.iterdir() if p.is_file()},
        'scope':'actual CPU supervisor SIGKILL only; no GPU worker, host crash or power-loss simulation'})
    print('CPU supervisor SIGKILL:orphan child observed',orphan_alive,';owned cleanup',child_cleanup,';exitcode unknown')


if __name__=='__main__':main()

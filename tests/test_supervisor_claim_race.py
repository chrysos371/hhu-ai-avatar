"""Concurrent worker claims and pre-spawn guard binding use real CPU processes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/lab/run_frozen_capability_job.py'
spec=importlib.util.spec_from_file_location('claim_jobs',SCRIPT)
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)


def config(folder,command):
    folder.mkdir()
    jobs.write_json(folder/'config.json',{'command':command,'cwd':str(jobs.ROOT),'context':{},
        'environment':{},'controller_sha256':jobs.digest(SCRIPT),
        'parent_death_guard_sha256':jobs.digest(jobs.GUARD),'created_utc':jobs.utc()})
    jobs.write_json(folder/'status.json',{'state':'queued'})
    return [sys.executable,'-B',str(SCRIPT),'--worker',str(folder),
        '--config-sha256',jobs.digest(folder/'config.json')]


def test_only_one_concurrent_supervisor_claim_can_execute(tmp_path):
    folder=tmp_path/'concurrent'
    argv=config(folder,[sys.executable,'-B','-c','import time; print("once",flush=True); time.sleep(.2)'])
    children=[subprocess.Popen(argv,start_new_session=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(2)]
    try:
        outputs=[p.communicate(timeout=10) for p in children]
        assert sorted(p.returncode for p in children)==[0,1],outputs
        state=jobs.status(folder)
        assert state['state']=='completed' and state['return_code']==0
        assert (folder/'experiment.log').read_text().strip()=='once'
        claim=json.loads((folder/'supervisor-start.json').read_text())
        winner=next(p for p in children if p.returncode==0)
        assert claim['worker']['pid']==winner.pid==state['worker']['pid']
    finally:
        # Fresh sessions belong only to these fixture supervisors/workers.
        for p in children:
            if p.poll() is None:p.kill();p.wait()


def test_supervisor_rejects_wrong_guard_source_before_child_spawn(tmp_path):
    folder=tmp_path/'unbound'
    config(folder,[sys.executable,'-B','-c','raise RuntimeError("must not execute")'])
    data=json.loads((folder/'config.json').read_text());data['parent_death_guard_sha256']='0'*64
    jobs.write_json(folder/'config.json',data)
    result=subprocess.run([sys.executable,'-B',str(SCRIPT),'--worker',str(folder),
        '--config-sha256',jobs.digest(folder/'config.json')],capture_output=True,text=True)
    assert result.returncode==0  # Supervisor CLI completed; no payload wait occurred.
    state=jobs.status(folder)
    assert state['state']=='failed' and state['child'] is None and state['return_code'] is None
    assert 'guard source changed' in state['error']
    assert not (folder/'experiment.log').exists() and not (folder/'parent-death-guard.json').exists()

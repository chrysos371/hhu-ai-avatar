"""Real owned CPU children exercise hard-parent death and terminal preservation."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/lab/run_frozen_capability_job.py'
spec=importlib.util.spec_from_file_location('parent_death_jobs',SCRIPT)
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)


def wait_for(predicate,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.02)
    pytest.fail('Owned CPU fixture did not reach expected state')


def cleanup(identity):
    if jobs.matches(identity):
        os.killpg(identity['pid'],signal.SIGKILL)
        wait_for(lambda:not jobs.matches(identity))


def test_hard_supervisor_death_retires_signal_ignoring_direct_child(tmp_path):
    folder=tmp_path/'hard-death';ready=tmp_path/'payload-ready'
    code=('import pathlib,signal,sys,time; '
        'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
        'signal.signal(signal.SIGINT,signal.SIG_IGN); '
        'pathlib.Path(sys.argv[1]).write_text("ready"); time.sleep(60)')
    launched=jobs.launch([sys.executable,'-B','-c',code,str(ready)],folder)
    child=None;worker=None
    unrelated=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'])
    try:
        state=wait_for(lambda:(s if (s:=jobs.status(folder))['child_verified_alive'] and ready.exists() else None))
        child=state['child'];worker=state['worker']
        assert jobs.matches(worker) and worker['pid']==launched['worker_pid']
        os.kill(worker['pid'],signal.SIGKILL)
        wait_for(lambda:not jobs.matches(worker))
        end=time.monotonic()+2
        while jobs.matches(child) and time.monotonic()<end:time.sleep(.02)
        alive_after_parent_death=jobs.matches(child)
        observed=jobs.status(folder)
        print(json.dumps({'child_alive_after_parent_SIGKILL':alive_after_parent_death,
            'original_status':observed,'unrelated_alive':unrelated.poll() is None}))
        assert unrelated.poll() is None
        assert observed['return_code'] is None  # Original parent cannot supply wait.
        assert not alive_after_parent_death,'Hard-killed supervisor left its direct CPU worker alive'
    finally:
        cleanup(child);cleanup(worker)
        unrelated.terminate();unrelated.wait()


def test_worker_cli_reentry_preserves_original_terminal_bytes(tmp_path):
    folder=tmp_path/'terminal'
    jobs.launch([sys.executable,'-B','-c','print("executed-once")'],folder)
    state=wait_for(lambda:(s if (s:=jobs.status(folder))['state']=='completed' else None))
    wait_for(lambda:not jobs.matches(state['worker']))
    original={p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}
    rerun=subprocess.run([sys.executable,'-B',str(SCRIPT),'--worker',str(folder),
        '--config-sha256',jobs.digest(folder/'config.json')],capture_output=True,text=True)
    print(json.dumps({'rerun_returncode':rerun.returncode,'original_terminal':state,
        'after_cli_reentry':jobs.status(folder)}))
    assert rerun.returncode!=0,'Direct worker CLI must reject an already-attempted job'
    assert {p.name:p.read_bytes() for p in folder.iterdir() if p.is_file()}==original
    assert (folder/'experiment.log').read_text().strip()=='executed-once'

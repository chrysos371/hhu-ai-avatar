"""CPU exec inheritance, venv identity and guard refusal controls."""
import ctypes
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import venv

import pytest

FOLDER=Path(__file__).resolve().parents[1]/'scripts/lab'


def module(name):
    spec=importlib.util.spec_from_file_location('test_'+name,FOLDER/f'{name}.py')
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


guard=module('guard_direct_child')
jobs=module('run_frozen_capability_job')


def until(predicate):
    end=time.monotonic()+10
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.02)
    pytest.fail('Short owned CPU fixture failed to reach expected state')


def test_guard_survives_exec_and_preserves_separate_venv(tmp_path):
    environment=tmp_path/'cpu-venv'
    venv.EnvBuilder(with_pip=False,symlinks=True).create(environment)
    python=environment/'bin/python'  # Keep the venv symlink in executable argv.
    code=('import ctypes,json,sys,time; c=ctypes.CDLL(None); s=ctypes.c_int(); '
        'c.prctl(2,ctypes.byref(s),0,0,0); '
        'print(json.dumps({"signal":s.value,"prefix":sys.prefix,"python":sys.executable}),flush=True); time.sleep(.2)')
    folder=tmp_path/'exec-job';argv=[str(python),'-B','-c',code]
    jobs.launch(argv,folder)
    state=until(lambda:(s if (s:=jobs.status(folder))['state'] in ('completed','failed') else None))
    assert state['state']=='completed' and state['return_code']==0
    actual=json.loads((folder/'experiment.log').read_text())
    assert actual=={'signal':signal.SIGKILL,'prefix':str(environment),'python':str(python)}
    assert state['payload_argv_observed'] and state['child']['argv']==argv
    receipt=json.loads((folder/'parent-death-guard.json').read_text())
    assert receipt['kernel_parent_death_signal']==signal.SIGKILL
    assert receipt['pid']==state['child']['pid'] and receipt['target_argv']==argv


@pytest.mark.parametrize('fault',['config_sha','guard_sha'])
def test_guard_cli_rejects_corruption_before_payload(tmp_path,fault):
    folder=tmp_path/fault;folder.mkdir();payload=tmp_path/'must-not-execute'
    config={'command':[sys.executable,'-B','-c','from pathlib import Path; import sys; Path(sys.argv[1]).touch()',str(payload)],
        'parent_death_guard_sha256':jobs.digest(jobs.GUARD)}
    if fault=='guard_sha':config['parent_death_guard_sha256']='0'*64
    jobs.write_json(folder/'config.json',config)
    expected=jobs.digest(folder/'config.json') if fault=='guard_sha' else '0'*64
    result=subprocess.run([sys.executable,'-B',str(jobs.GUARD),'--job',str(folder),
        '--config-sha256',expected,'--parent-pid',str(os.getpid())],capture_output=True,text=True)
    assert result.returncode!=0 and not payload.exists()
    reason='Job config changed' if fault=='config_sha' else 'guard source changed'
    assert reason in result.stderr and not (folder/'parent-death-guard.json').exists()


def test_parent_already_dead_does_not_execute_payload(tmp_path):
    gate=tmp_path/'release';out=tmp_path/'result.json';payload=tmp_path/'must-not-execute'
    child_code=('import importlib.util,json,os,pathlib,sys,time; '
        's=importlib.util.spec_from_file_location("guard",sys.argv[1]); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
        'gate=pathlib.Path(sys.argv[3]); exec("while not gate.exists(): time.sleep(.02)"); '
        'exec("try:\\n m.install_guard(int(sys.argv[2]))\\n pathlib.Path(sys.argv[5]).touch()\\nexcept RuntimeError as e:\\n pathlib.Path(sys.argv[4]).write_text(json.dumps({\\"rejected\\":str(e),\\"actual_parent\\":os.getppid()}))")')
    # The intermediate launcher really exits before releasing the child into
    # guard installation. This exercises the documented pre-installation race.
    parent_code=('import json,os,subprocess,sys; '
        'child=subprocess.Popen([sys.executable,"-B","-c",sys.argv[1],sys.argv[2],str(os.getpid()),*sys.argv[3:]],'
        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True); '
        'print(json.dumps({"child_pid":child.pid,"dead_parent_pid":os.getpid()}))')
    parent=subprocess.run([sys.executable,'-B','-c',parent_code,child_code,str(jobs.GUARD),str(gate),str(out),str(payload)],capture_output=True,text=True,check=True)
    launched=json.loads(parent.stdout);identity=jobs.process(launched['child_pid'])
    try:
        assert identity and jobs.matches(identity)
        gate.touch();until(out.exists)
        result=json.loads(out.read_text())
        assert 'changed before guard installation' in result['rejected']
        assert result['actual_parent']!=launched['dead_parent_pid'] and not payload.exists()
        until(lambda:not jobs.matches(identity))
    finally:
        if jobs.matches(identity):os.killpg(identity['pid'],signal.SIGKILL)


def test_post_prctl_parent_race_is_refused_without_native_signal(monkeypatch):
    # Synthetic syscall seam: do not modify the test runner's own death signal.
    parents=iter([123,456]);monkeypatch.setattr(guard.os,'getppid',lambda:next(parents))
    class Syscall:
        restype=None
        def __call__(self,*args):return 0
    class FakeLibc:prctl=Syscall()
    monkeypatch.setattr(guard.ctypes,'CDLL',lambda *a,**kw:FakeLibc())
    with pytest.raises(RuntimeError,match='changed while installing'):guard.install_guard(123)


def test_failed_native_syscall_is_not_silently_ignored(monkeypatch):
    class Syscall:
        restype=None
        def __call__(self,*args):return -1
    class FakeLibc:prctl=Syscall()
    monkeypatch.setattr(guard.ctypes,'CDLL',lambda *a,**kw:FakeLibc())
    monkeypatch.setattr(guard.ctypes,'get_errno',lambda:22)
    with pytest.raises(OSError,match='Cannot install'):guard.install_guard(os.getppid())


@pytest.mark.parametrize('state',['completed','failed','interrupted','running'])
def test_legacy_job_without_claim_still_preserves_all_receipts(tmp_path,state):
    folder=tmp_path/state;folder.mkdir()
    jobs.write_json(folder/'config.json',{'legacy':True})
    jobs.write_json(folder/'status.json',{'state':state,'return_code':0 if state=='completed' else None})
    (folder/'experiment.log').write_text('original-once\n')
    before={p.name:p.read_bytes() for p in folder.iterdir()}
    result=subprocess.run([sys.executable,'-B',str(FOLDER/'run_frozen_capability_job.py'),
        '--worker',str(folder),'--config-sha256',jobs.digest(folder/'config.json')],capture_output=True,text=True)
    assert result.returncode!=0 and 'already attempted' in result.stderr
    assert {p.name:p.read_bytes() for p in folder.iterdir()}==before

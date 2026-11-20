"""Real CPU provider-edge lifecycle and a protected three-process chain."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts/lab'))
import owned_provider as owned
import run_frozen_capability_job as jobs


def until(predicate):
    end=time.monotonic()+10
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.02)
    pytest.fail('Owned CPU provider fixture did not reach expected state')


@pytest.mark.parametrize('code',[0,7])
def test_provider_preserves_actual_exit_and_immutable_terminal(tmp_path,code):
    folder=tmp_path/'provider';argv=[sys.executable,'-B','-c',f'import time; print("ready",flush=True); time.sleep(.15); raise SystemExit({code})']
    with (tmp_path/'provider.log').open('x') as log:
        process,proof=owned.start_provider(tuple(argv),folder,cwd=ROOT,env=dict(os.environ),stdout=log)
        with pytest.raises(ValueError,match='Wait'):owned.finish_provider(process,folder)
        assert process.wait(timeout=10)==code
        terminal=owned.finish_provider(process,folder)
    assert proof['payload_argv_observed'] and proof['provider_identity']['argv']==argv
    assert terminal['actual_provider_wait_code']==code
    guard=json.loads((folder/'parent-death-guard.json').read_text())
    assert guard['pid']==process.pid and guard['kernel_parent_death_signal']==signal.SIGKILL
    original=(folder/'terminal.json').read_bytes()
    with pytest.raises(FileExistsError):owned.finish_provider(process,folder)
    assert (folder/'terminal.json').read_bytes()==original
    with pytest.raises(FileExistsError):
        owned.start_provider(argv,folder,cwd=ROOT,env=dict(os.environ),stdout=subprocess.DEVNULL)


def test_three_layer_chain_retires_provider_after_supervisor_SIGKILL(tmp_path):
    manager=tmp_path/'manager.py';payload=tmp_path/'payload.py'
    payload.write_text('''import ctypes,json,os,signal,sys,time
from pathlib import Path
signal.signal(signal.SIGINT,signal.SIG_IGN);signal.signal(signal.SIGTERM,signal.SIG_IGN)
c=ctypes.CDLL(None);v=ctypes.c_int();c.prctl(2,ctypes.byref(v),0,0,0)
Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid(),'parent_pid':os.getppid(),'signal':v.value}))
while True:time.sleep(.1)
''')
    manager.write_text('''import ctypes,json,os,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from owned_provider import start_provider
root=Path(sys.argv[2]);c=ctypes.CDLL(None);v=ctypes.c_int();c.prctl(2,ctypes.byref(v),0,0,0)
with (root/'provider.log').open('x') as stream:
 child,proof=start_provider([sys.executable,'-B',str(root/'payload.py'),str(root/'payload-ready.json')],root/'provider-edge',cwd=root,env=dict(os.environ),stdout=stream)
 (root/'manager-ready.json').write_text(json.dumps({'pid':os.getpid(),'signal':v.value,'child_pid':child.pid}))
 while True:time.sleep(.1)
''')
    folder=tmp_path/'top-job'
    jobs.launch([sys.executable,'-B',str(manager),str(ROOT/'scripts/lab'),str(tmp_path)],folder)
    identities=[]
    unrelated=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(60)'])
    try:
        until(lambda:(tmp_path/'manager-ready.json').exists() and (tmp_path/'payload-ready.json').exists())
        m=json.loads((tmp_path/'manager-ready.json').read_text());p=json.loads((tmp_path/'payload-ready.json').read_text())
        state=jobs.status(folder);identities=[jobs.process(p['pid']),state['child'],state['worker']]
        assert m['signal']==p['signal']==signal.SIGKILL
        assert m['pid']==state['child']['pid'] and m['child_pid']==p['pid'] and p['parent_pid']==m['pid']
        assert all(jobs.matches(i) for i in identities)
        os.kill(state['worker']['pid'],signal.SIGKILL)
        until(lambda:all(not jobs.matches(i) for i in identities))
        assert unrelated.poll() is None
        assert jobs.status(folder)['return_code'] is None
        assert not (tmp_path/'provider-edge/terminal.json').exists()  # Lost parent wait stays unknown.
        assert json.loads((tmp_path/'provider-edge/parent-death-guard.json').read_text())['kernel_parent_death_signal']==signal.SIGKILL
    finally:
        for identity in identities:
            if jobs.matches(identity):os.killpg(identity['pid'],signal.SIGKILL)
        unrelated.terminate();unrelated.wait()


def test_provider_argv_is_not_a_shell_string(tmp_path):
    with pytest.raises(ValueError,match='explicit argv'):
        owned.start_provider('python -V',tmp_path/'not-created',cwd=ROOT,env={},stdout=subprocess.DEVNULL)
    assert not (tmp_path/'not-created').exists()

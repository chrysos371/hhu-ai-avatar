"""Protect each explicit native-provider edge; preserve real launch/wait evidence."""
import json
from pathlib import Path
import signal
import subprocess
import sys

import run_frozen_capability_job as jobs

PROTECTION_SOURCES=('scripts/lab/owned_provider.py',
    'scripts/lab/run_frozen_capability_job.py','scripts/lab/guard_direct_child.py')


def immutable(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False)
        stream.write('\n');stream.flush()


def start_provider(command,directory,*,cwd,env,stdout):
    if not command or not command[0] or any(not isinstance(v,str) or '\0' in v for v in command):
        raise ValueError('Provider requires explicit argv')
    directory=Path(directory).absolute();directory.mkdir(parents=True,exist_ok=False)
    config={'command':command,'cwd':str(Path(cwd).absolute()),'context':{'process_role':'native_provider'},
        'environment':{k:env[k] for k in ('CUDA_VISIBLE_DEVICES','LD_LIBRARY_PATH','OMP_NUM_THREADS','OPENBLAS_NUM_THREADS') if k in env},
        'parent_death_guard_sha256':jobs.digest(jobs.GUARD),
        'provider_launcher_sha256':jobs.digest(Path(__file__).resolve()),
        'supervisor_utility_sha256':jobs.digest(Path(jobs.__file__).resolve()),'created_utc':jobs.utc()}
    immutable(directory/'config.json',config)
    expected=jobs.digest(directory/'config.json')
    state={'state':'starting_provider','worker':jobs.process(__import__('os').getpid()),
        'child':None,'return_code':None,'stop_signal':None,'context':config['context']}
    jobs.write_json(directory/'status.json',state)
    child=None
    try:
        guarded=[sys.executable,'-B',str(jobs.GUARD),'--job',str(directory),
            '--config-sha256',expected,'--parent-pid',str(state['worker']['pid'])]
        child=subprocess.Popen(guarded,cwd=config['cwd'],env=env,stdin=subprocess.DEVNULL,
            stdout=stdout,stderr=subprocess.STDOUT,start_new_session=True)
        state['child']=jobs.process(child.pid)
        jobs.write_json(directory/'status.json',state)
        jobs.observe_protected_exec(child,directory,config,expected,state,[])
        if not (directory/'parent-death-guard.json').is_file():
            raise RuntimeError('Native provider did not install actual parent-death guard')
        state['state']='provider_running' if child.poll() is None else 'provider_exited'
        jobs.write_json(directory/'status.json',state)
        evidence={'directory':str(directory),'config_sha256':expected,
            'guard_receipt_sha256':jobs.digest(directory/'parent-death-guard.json'),
            'provider_identity':state['child'],'parent_identity':state['worker'],
            'payload_argv_observed':state['payload_argv_observed'],
            'provider_launcher_sha256':config['provider_launcher_sha256'],
            'supervisor_utility_sha256':config['supervisor_utility_sha256'],
            'guard_source_sha256':config['parent_death_guard_sha256']}
        immutable(directory/'launch-evidence.json',evidence)
        return child,evidence
    except BaseException as error:
        state['state']='failed';state['error']=repr(error)
        if child is not None:
            if child.poll() is None:
                jobs.signal_owned_child(child,state['child'] or jobs.process(child.pid),signal.SIGKILL)
            state['return_code']=child.wait()
        state['ended_utc']=jobs.utc()
        jobs.write_json(directory/'status.json',state)
        immutable(directory/'startup-failure.json',state)
        raise


def finish_provider(child,directory):
    directory=Path(directory)
    if type(child.returncode) is not int:
        raise ValueError('Wait for the actual provider before recording terminal evidence')
    state=json.loads((directory/'status.json').read_text())
    launch=json.loads((directory/'launch-evidence.json').read_text())
    if state['child']!=launch['provider_identity'] or state['child']['pid']!=child.pid:
        raise ValueError('Provider terminal identity differs from launch')
    state.update(state='completed' if child.returncode==0 else 'failed',
        return_code=child.returncode,ended_utc=jobs.utc())
    immutable(directory/'terminal.json',state)
    jobs.write_json(directory/'status.json',state)
    return {'actual_provider_wait_code':child.returncode,
        'terminal_sha256':jobs.digest(directory/'terminal.json'),'directory':str(directory)}

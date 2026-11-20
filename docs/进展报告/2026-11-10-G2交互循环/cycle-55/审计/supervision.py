"""Bind the reusable detached supervisor to exactly one frozen C55 stage."""
import importlib.util
import os
from pathlib import Path
import sys
from execution_common import ROOT,AUDIT,ASSETS,WORK,JOBS,STAGES,read,sha,require

SOURCE=ROOT/'scripts/lab/run_frozen_capability_job.py'
spec=importlib.util.spec_from_file_location('c55_durable_jobs',SOURCE)
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)


def command(stage,expected):
    require(stage in STAGES,'unknown C55 stage')
    return [str(ASSETS/'envs/hhu-ai-avatar-train/bin/python'),'-B',str(AUDIT/'run_execution.py'),
        '--freeze',str(WORK/'freeze-v1.json'),'--expected-freeze-sha256',expected,'--stage',stage]


def context(stage,expected):
    return {'experiment':'C55','stage':stage,'execution_freeze':str(WORK/'freeze-v1.json'),
        'execution_freeze_sha256':expected,'supervision_binding_sha256':sha(Path(__file__)),
        'whole_experiment_deadline':None,'no_retries':True}


def config_check(folder,stage,expected):
    config=read(folder/'config.json')
    require(config['command']==command(stage,expected) and config['cwd']==str(ROOT)
        and config['context']==context(stage,expected)
        and config['environment']=={'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4'}
        and config['controller_sha256']==sha(SOURCE),'supervised argv/context/controller differs')
    return config


def admission(stage,expected):
    folder=JOBS/stage
    config_check(folder,stage,expected)
    state=read(folder/'status.json')
    own=jobs.process(os.getpid())
    worker=state.get('worker')
    # Supervisor writes child identity immediately after Popen. Checking our
    # parent does not depend on that small status-update race.
    require(state['state']=='running' and state['context']==context(stage,expected)
        and worker and jobs.matches(worker) and os.getppid()==worker['pid']
        and worker['process_group']==worker['pid']
        and own['process_group']==own['pid'] and own['argv']==command(stage,expected),
        'C55 worker requires its bound live detached supervisor')
    return {'supervisor':worker,'worker':own,'config_sha256':sha(folder/'config.json')}


def terminal(stage,expected,marker):
    folder=JOBS/stage
    config_check(folder,stage,expected)
    state=read(folder/'status.json');child=state.get('child')
    launch=read(folder/'launch.json')
    require(state['state']=='completed' and type(state['return_code']) is int and state['return_code']==0
        and state['stop_signal'] is None and state['ended_utc']
        and state['context']==context(stage,expected),'actual supervisor wait did not report normal success')
    require(child and child['pid']==marker['pid'] and str(child['start_ticks'])==marker['start_ticks']
        and child['argv']==command(stage,expected) and child['process_group']==child['pid'],
        'terminal child identity differs from stage process')
    require(state['worker']['pid']==launch['worker_pid']
        and state['worker']['start_ticks']==launch['worker_identity']['start_ticks']
        and state['worker']['argv']==launch['worker_identity']['argv']
        and state['worker']['process_group']==state['worker']['pid']
        and not jobs.matches(state['worker']) and not jobs.matches(child),'supervisor or child still live / launch identity differs')
    return {'actual_child_wait_returncode':0,'supervisor_retired':True,
        'job_files_sha256':{p.name:sha(p) for p in folder.iterdir() if p.is_file()},
        'job_root':str(folder),'supervisor_source_sha256':sha(SOURCE)}

"""Inspect actual CPU job bytes and stop one owned payload only after exec."""
import importlib.util
from pathlib import Path
import os
import signal
import sys
import time

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'scripts/lab/run_frozen_capability_job.py'
spec=importlib.util.spec_from_file_location('c56_receipt_jobs',SOURCE)
jobs=importlib.util.module_from_spec(spec);spec.loader.exec_module(jobs)
OUT=ASSETS/'artifacts/c56/stop-after-payload-exec-v1'


def require(ok,message):
    if not ok:raise ValueError(message)


def wait_for(predicate):
    end=time.monotonic()+15  # Only this tiny CPU fixture's engineering bound.
    while time.monotonic()<end:
        value=predicate()
        if value:return value
        time.sleep(.02)
    raise RuntimeError('CPU fixture did not reach expected state')


def main():
    require(not OUT.exists(),'fresh stop-after-exec fixture required')
    argv=[sys.executable,'-B','-c','import time; print("actual-payload-ready",flush=True); time.sleep(60)']
    jobs.launch(argv,OUT)
    before=None
    try:
        before=wait_for(lambda:(s if (s:=jobs.status(OUT)).get('payload_argv_observed')
            and s['child_verified_alive'] and 'actual-payload-ready' in (OUT/'experiment.log').read_text() else None))
        require(before['child']['argv']==argv and jobs.matches(before['worker']),'actual payload/supervisor identity differs')
        os.kill(before['worker']['pid'],signal.SIGTERM)
        after=wait_for(lambda:(s if (s:=jobs.status(OUT))['state'] in ('completed','failed','interrupted') else None))
        require(after['state']=='interrupted' and after['stop_signal']==signal.SIGTERM
            and type(after['return_code']) is int and after['return_code']!=0,'actual post-exec stop terminal differs')
        wait_for(lambda:not jobs.matches(after['worker']) and not jobs.matches(after['child']))
    finally:
        if before:
            for key in ('child','worker'):
                identity=before[key]
                if jobs.matches(identity):os.killpg(identity['pid'],signal.SIGKILL)
    rows=[];raw={}
    roots=[ASSETS/'tmp/c56-supervisor-green-v1',ASSETS/'tmp/c56-guard-controls-v1',ASSETS/'tmp/c56-claim-controls-v1']
    for root in roots:
        require(root.is_dir(),'original CPU fixture root missing')
        for path in sorted(root.rglob('status.json')):
            state=__import__('json').loads(path.read_text())
            if not state.get('worker'):continue  # Synthetic legacy JSON refusal fixture.
            require(not jobs.matches(state.get('worker')) and not jobs.matches(state.get('child')),'owned CPU fixture remains live')
            receipt=path.parent/'parent-death-guard.json'
            if receipt.exists():
                guard=__import__('json').loads(receipt.read_text())
                require(guard['installed'] and guard['kernel_parent_death_signal']==signal.SIGKILL
                    and guard['guard_sha256']==jobs.digest(jobs.GUARD),'actual CPU guard receipt differs')
            rows.append({'status':str(path),'state':state['state'],'actual_child_wait_code':state['return_code'],
                'original_worker_dead':True,'original_child_dead':True,'guard_receipt':receipt.exists()})
            for p in path.parent.iterdir():
                if p.is_file():raw[str(p)]=jobs.digest(p)
    require(any(r['state']=='running' and r['actual_child_wait_code'] is None and r['guard_receipt'] for r in rows),
        'retain hard-killed supervisor unknown terminal rather than faking success')
    raw.update({str(p):jobs.digest(p) for p in OUT.iterdir() if p.is_file()})
    jobs.write_json(HERE/'cpu-receipts-v1.json',{'verified':True,'inspector_sha256':jobs.digest(Path(__file__)),
        'supervisor_sha256':jobs.digest(SOURCE),'guard_sha256':jobs.digest(jobs.GUARD),
        'actual_stop_after_payload_exec':{'before':before,'after':after,'both_identities_retired':True},
        'existing_actual_job_receipts':rows,'external_sha256':raw,'new_model_calls':0,'new_training_steps':0,'GPU_allocations':0,
        'scope':'actual CPU receipts and explicit post-exec stop;not GPU/cross-OS/grandchild-tree approval'})
    print('CPU receipts inspected',len(rows),'actual jobs;post-exec child wait',after['return_code'],';all owned identities retired')


if __name__=='__main__':main()

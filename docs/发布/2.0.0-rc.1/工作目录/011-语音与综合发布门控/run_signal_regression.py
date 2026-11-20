"""Replay existing analytical lip mechanics and integer-sample clock gates."""
from hashlib import sha256
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import time

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
RAW=Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/signal-regression-v1')


def digest(p):return sha256(p.read_bytes()).hexdigest()


def main():
    assert not sys.argv[1:]
    common=runpy.run_path(str(HERE.parent/'006-写作交付与严格格式/run_current_python.py'))
    before=common['snapshot']();before[str(Path(__file__).relative_to(ROOT))]=digest(Path(__file__))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    blob=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(blob)) as stream:
        assert {m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}==before
    RAW.mkdir(parents=True,exist_ok=False);steps=[];start=time.monotonic()
    commands=[('analytic-baseline',['scripts/evaluate_analytic_lipsync.py','--split','validation','--arm','baseline','--regression-replay','--output',str(RAW/'analytic-baseline.json')]),
        ('analytic-current',['scripts/evaluate_analytic_lipsync.py','--split','validation','--arm','candidate','--regression-replay','--output',str(RAW/'analytic-current.json')]),
        ('analytic-compare',['scripts/compare_analytic_lipsync.py','--baseline',str(RAW/'analytic-baseline.json'),'--candidate',str(RAW/'analytic-current.json'),'--output',str(RAW/'analytic-compare.json')]),
        ('sample-clock',['scripts/evaluate_lipsync_timeline.py','--arm','candidate','--output',str(RAW/'sample-clock.json')])]
    for label,args in commands:
        argv=[sys.executable,'-B',*args];began=time.monotonic()
        with (RAW/(label+'.log')).open('x') as out:
            result=subprocess.run(argv,cwd=ROOT,stdout=out,stderr=subprocess.STDOUT)
        steps.append(dict(label=label,argv=argv,actual_returncode=result.returncode,seconds=time.monotonic()-began))
        if result.returncode:break
    read=lambda n:json.loads((RAW/n).read_text()) if (RAW/n).exists() else {}
    compare=read('analytic-compare.json');clock=read('sample-clock.json')
    stable=all(digest(ROOT/p)==h for p,h in before.items())
    passed=(len(steps)==4 and all(s['actual_returncode']==0 for s in steps) and stable
        and compare.get('engineering_gate_passed') is True and clock.get('sample_clock_gate_passed') is True)
    proof=dict(source_ref=head,source_sha256=before,source_inputs=len(before),source_unchanged=stable,
        steps=steps,passed=passed,seconds_including_processes=time.monotonic()-start,whole_stage_wallclock_cutoff=None,
        analytic_summary=compare,sample_clock_rows=clock.get('rows'),file_api=clock.get('file_api'),
        scope='same already-seen all-pole signals and integer PCM clocks; no human phoneme/ue/tone/physical synchronization approval',
        raw=str(RAW),raw_sha256={str(p.relative_to(RAW)):digest(p) for p in sorted(RAW.rglob('*')) if p.is_file()})
    with (HERE/'signal-regression-v1.json').open('x') as f:json.dump(proof,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps(dict(passed=passed,source_unchanged=stable,steps=[(s['label'],s['actual_returncode']) for s in steps])))
    assert passed,'failure retained'


if __name__=='__main__':main()

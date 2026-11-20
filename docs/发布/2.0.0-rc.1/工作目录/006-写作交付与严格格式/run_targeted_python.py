"""Capture real pytest status separately from controller/expected-red status."""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import time

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent


def digest(path):return sha256(path.read_bytes()).hexdigest()


def execution_input(name):
    return (name.startswith(('src/','scripts/','tests/','frontend/','evals/','training/'))
        or name=='pyproject.toml' or name.startswith('requirements') and name.endswith('.txt')
        or '/' not in name and name.endswith('.py'))


def snapshot():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected={n for n in names if execution_input(n)}
    selected.add(str(Path(__file__).resolve().relative_to(ROOT)))
    return {n:digest(ROOT/n) for n in sorted(selected)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--name',required=True)
    parser.add_argument('--expected-exit',type=int,choices=[0,1,2],default=0)
    parser.add_argument('tests',nargs='+')
    args=parser.parse_args()
    assert re.fullmatch(r'[a-z][a-z0-9-]*-v[1-9][0-9]*',args.name),'versioned run name required'
    log=HERE/(args.name+'.log');proof_path=HERE/(args.name+'.json')
    assert not log.exists() and not proof_path.exists(),'preserve prior runs'
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    assert not any(n and execution_input(n) for n in untracked),'commit execution inputs first'
    before=snapshot()
    for node in args.tests:
        name=node.split('::')[0]
        assert name.startswith('tests/') and name in before and (ROOT/name).resolve().is_relative_to(ROOT)
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    raw=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
        historical={m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    assert historical==before,'tested bytes must already exist in source Git history'
    argv=[sys.executable,'-B','-m','pytest','-q','--color=no',*args.tests]
    proof=dict(source_ref=head,source_sha256=before,source_inputs=len(before),argv=argv,
        expected_pytest_returncode=args.expected_exit,actual_returncode=None,source_unchanged=False,
        whole_stage_wallclock_cutoff=None,scope='targeted software evidence, not native or semantic quality approval')
    with proof_path.open('x') as stream:json.dump(proof,stream,ensure_ascii=False,indent=2);stream.write('\n')
    start=time.monotonic()
    with log.open('x') as stream:result=subprocess.run(argv,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    proof.update(actual_returncode=result.returncode,source_unchanged=snapshot()==before,
        seconds_including_collection=time.monotonic()-start,log_sha256=digest(log),
        expected_result_matched=result.returncode==args.expected_exit)
    proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in proof.items() if k not in ('source_sha256','argv')},ensure_ascii=False))
    raise SystemExit(0 if proof['source_unchanged'] and proof['expected_result_matched'] else 1)


if __name__=='__main__':main()

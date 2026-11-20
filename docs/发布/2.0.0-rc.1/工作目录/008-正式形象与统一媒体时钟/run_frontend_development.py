"""Source-bound development frontend gates; final clean distribution remains separate."""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent


def digest(path):return sha256(path.read_bytes()).hexdigest()


def snapshot():
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected={p for p in tracked if p.startswith('frontend/')}
    selected.update(('scripts/frontend.sh','scripts/project_env.sh','scripts/project_paths.py',
        'src/avatar/paths.py',str(Path(__file__).relative_to(ROOT))))
    return {p:digest(ROOT/p) for p in sorted(selected)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',type=int,required=True);args=parser.parse_args()
    assert 1<=args.version<=99
    label='frontend-development-v'+str(args.version)
    raw=ASSETS/'artifacts/release'/('formal-renderer-'+label);raw.mkdir(parents=True,exist_ok=False)
    path=HERE/(label+'.json');assert not path.exists()
    before=snapshot();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    archived=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archived)) as stream:
        historical={m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    assert historical==before
    others=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z','--','frontend'],cwd=ROOT).decode().split('\0')
    assert not any(others)
    proof=dict(source_ref=head,source_sha256=before,source_unchanged=False,passed=False,steps=[],
        raw_root=str(raw),whole_stage_deadline=None,scope='development frontend software gates; not clean distribution or physical/human approval')
    path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic()
    try:
        steps=[('typecheck',['exec','--','tsc','--noEmit','--project',str(ROOT/'frontend/tsconfig.json')]),('lint',['run','lint']),
            ('unit',['run','test','--','--run']),('build',['run','build','--','--outDir',str(raw/'ui')])]
        for name,options in steps:
            tick=time.monotonic();argv=[str(ROOT/'scripts/frontend.sh'),*options]
            with (raw/(name+'.log')).open('x') as output:
                result=subprocess.run(argv,cwd=ROOT/'frontend',stdout=output,stderr=subprocess.STDOUT)
            proof['steps'].append(dict(name=name,argv=argv,cwd=str(ROOT/'frontend'),actual_returncode=result.returncode,
                seconds=time.monotonic()-tick,log_sha256=digest(raw/(name+'.log'))))
            assert result.returncode==0,name+' failed; original retained'
            print(name,'actual exit',result.returncode,flush=True)
        proof['source_unchanged']=snapshot()==before;assert proof['source_unchanged']
        proof['ui_sha256']={str(p.relative_to(raw/'ui')):digest(p) for p in sorted((raw/'ui').rglob('*')) if p.is_file()}
        proof['passed']=True
    except BaseException as error:
        proof['error']=repr(error);raise
    finally:
        proof['seconds_including_all_steps']=time.monotonic()-started
        proof['raw_sha256']={str(p.relative_to(raw)):digest(p) for p in sorted(raw.rglob('*')) if p.is_file()}
        path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':main()

"""Run one full Python regression with current/Git source binding; no wall cutoff."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/004-当前软件回归'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot():
    prior=json.loads((BASE.parent/'cycle-50/审计/收尾核验/system-evidence.json').read_text())['source_sha256']
    names=set(prior)
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    names.update(n for n in tracked if n.startswith(('src/','scripts/','tests/','frontend/')))
    return {n:digest(ROOT/n) for n in sorted(names)}


def main():
    WORK.mkdir(exist_ok=True);output=WORK/'python-first-binding.json';log=WORK/'python-first.log'
    assert not output.exists() and not log.exists()
    before=snapshot();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    # Git archive validates the whole set without spawning one git process per file.
    import io
    import tarfile
    archive=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        historical={m.name:hashlib.sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    assert historical==before
    command=[sys.executable,'-m','pytest','tests/','-q']
    proof={'scope':'current C53 full Python regression after loader-integrity and step-evidence changes; no frontend or native quality claim',
        'head':head,'source_git_sha256':before,'source_inputs':len(before),'driver_sha256':digest(__file__),
        'argv':command,'exit_code':None,'source_unchanged':False,'whole_stage_wallclock_cutoff':None,'native_quality_claim':False}
    output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    started=time.monotonic()
    with log.open('x') as stream:result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    proof.update(exit_code=result.returncode,source_unchanged=snapshot()==before,
        seconds_including_collection=time.monotonic()-started,log_sha256=digest(log))
    output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    assert result.returncode==0 and proof['source_unchanged'],'Retained failure and binding; do not overwrite'
    print('C53 full Python passed;',len(before),'stable current/Git inputs;',proof['seconds_including_collection'],'seconds')


if __name__=='__main__':main()

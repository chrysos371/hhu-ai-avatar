"""Source-bound original C01 engineering regressions after release startup changes."""
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent


def digest(path):return sha256(path.read_bytes()).hexdigest()


def snapshot():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected={n for n in names if n.startswith(('src/','scripts/','tests/','frontend/','evals/','training/'))
        or n=='pyproject.toml' or n.startswith('requirements') and n.endswith('.txt')
        or '/' not in n and n.endswith('.py')}
    return {n:digest(ROOT/n) for n in sorted(selected)}


def main():
    proof_path=HERE/'c01-current-v1-binding.json';log=HERE/'c01-current-v1.log'
    assert not proof_path.exists() and not log.exists(),'retain previous run;do not overwrite'
    before=snapshot();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    raw=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
        historical={m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    assert historical==before,'all execution inputs must already be committed'
    argv=[sys.executable,'-B','-m','pytest', 'tests/test_web_concurrency.py','tests/test_context_erasure.py','tests/test_turns.py','tests/test_lipsync.py','tests/test_web_runtime.py','tests/test_streaming.py','tests/test_response_erasure.py','tests/test_turn_subscribers.py','-q']
    proof={'source_ref':head,'source_sha256':before,'source_inputs':len(before),'driver_sha256':digest(Path(__file__)),
        'argv':argv,'actual_returncode':None,'source_unchanged':False,'whole_stage_wallclock_cutoff':None,
        'scope':'C01 original nine engineering findings; targeted current software, not model/release-wide approval'}
    with proof_path.open('x') as stream:json.dump(proof,stream,ensure_ascii=False,indent=2);stream.write('\n')
    start=time.monotonic()
    with log.open('x') as stream:result=subprocess.run(argv,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    proof.update(actual_returncode=result.returncode,source_unchanged=snapshot()==before,
        seconds_including_collection=time.monotonic()-start,log_sha256=digest(log))
    proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    assert result.returncode==0 and proof['source_unchanged'],'failure retained;repair before broader release'
    print('C01 targeted Python passed;',len(before),'stable Git/current inputs;',proof['seconds_including_collection'],'seconds')


if __name__=='__main__':main()

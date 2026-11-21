"""Current-source replay of the already-known, pinned public ASR corpus."""
from hashlib import sha256
import importlib.metadata
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
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
RAW=ASSETS/'artifacts/release/public-asr-cpu-v2'
FOLDER=ASSETS/'artifacts/g2-cycle-02/aishell'
MODEL=ASSETS/'models/faster-whisper-small'


def digest(p):return sha256(p.read_bytes()).hexdigest()


def main():
    assert not sys.argv[1:]
    common=runpy.run_path(str(HERE.parent/'006-写作交付与严格格式/run_current_python.py'))
    before=common['snapshot']();before[str(Path(__file__).relative_to(ROOT))]=digest(Path(__file__))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    blob=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(blob)) as stream:
        historical={m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    assert historical==before,'all execution inputs must be committed'
    manifest=json.loads((FOLDER/'manifest.json').read_text())
    external={FOLDER/'manifest.json':digest(FOLDER/'manifest.json')}
    for row in manifest['rows']:
        path=(ROOT/row['path']).resolve();assert path.is_relative_to(ASSETS)
        assert digest(path)==row['audio_sha256'];external[path]=digest(path)
    for path in MODEL.iterdir():
        if path.is_file():external[path]=digest(path)
    assert len(manifest['rows'])==40 and len({r['speaker'] for r in manifest['rows']})==20
    RAW.mkdir(parents=True,exist_ok=False)
    argv=[sys.executable,'-B',str(ROOT/'scripts/evaluate_public_asr.py'),'evaluate',
        '--folder',str(FOLDER),'--model',str(MODEL),'--device','cpu','--output',str(RAW/'results.json')]
    start=time.monotonic()
    with (RAW/'stdout.log').open('x') as out,(RAW/'stderr.log').open('x') as err:
        proc=subprocess.run(argv,cwd=ROOT,stdout=out,stderr=err)
    results=json.loads((RAW/'results.json').read_text()) if (RAW/'results.json').exists() else {}
    stable=all(digest(ROOT/p)==h for p,h in before.items())
    external_stable=all(digest(p)==h for p,h in external.items())
    passed=proc.returncode==0 and stable and external_stable and results.get('summary',{}).get('passes_preregistered_gate') is True
    proof=dict(source_ref=head,source_sha256=before,source_inputs=len(before),source_unchanged=stable,
        external_sha256={str(p):h for p,h in external.items()},external_unchanged=external_stable,
        actual_returncode=proc.returncode,argv=argv,seconds_including_process=time.monotonic()-start,
        whole_stage_wallclock_cutoff=None,device='cpu',compute_type='int8',cpu_threads=4,
        package_versions={n:importlib.metadata.version(n) for n in ('faster-whisper','ctranslate2','numpy','soundfile')},
        summary=results.get('summary'),passed=passed,
        scope='40 known public read-speech utterances, no novel holdout/free conversation/physical or human acceptance',
        raw=str(RAW),raw_sha256={str(p.relative_to(RAW)):digest(p) for p in sorted(RAW.rglob('*')) if p.is_file()})
    with (HERE/'public-asr-cpu-v2.json').open('x') as stream:json.dump(proof,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:proof[k] for k in ('actual_returncode','source_unchanged','external_unchanged','summary','passed')},ensure_ascii=False))
    assert passed,'failure retained; repair before release'


if __name__=='__main__':main()

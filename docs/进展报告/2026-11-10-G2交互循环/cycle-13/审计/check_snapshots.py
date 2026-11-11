"""Verify bindings against archives/commit trees, not mutable current source alone."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
EV=HERE.parent/'实验'
ROOT=Path(__file__).resolve().parents[5]
C12=HERE.parent.parent/'cycle-12/实验'
checks=[]
for report in sorted(EV.rglob('*.json')):
    if any(p in report.parts for p in ('frozen-v1-source','frozen-v2-source')):continue
    data=json.loads(report.read_text())
    if not isinstance(data,dict) or 'sourceSha256' not in data:continue
    head=data.get('head')
    if head is None and report.name.endswith('-state.json'):
        head=json.loads((report.parents[1]/'restart.json').read_text())['head']
    for original,digest in data['sourceSha256'].items():
        root_relative=original.startswith(('src/avatar/','scripts/','evals/'))
        repo=Path(original) if root_relative else (ROOT/'frontend'/original).resolve().relative_to(ROOT)
        choices=[EV/'frozen-v1-source'/repo,EV/'frozen-v2-source'/repo,ROOT/repo]
        found=next((p for p in choices if p.is_file() and sha256(p.read_bytes()).hexdigest()==digest),None)
        if found: match=str(found.relative_to(ROOT))
        else:
            payload=subprocess.check_output(['git','show',head+':'+str(repo)],cwd=ROOT)
            assert sha256(payload).hexdigest()==digest,(report,original)
            match='git:'+head+':'+str(repo)
        checks.append({'report':str(report.relative_to(EV)),'source':original,'sha256':digest,'matches':match})
    for original,digest in data.get('servedBundleSha256',{}).items():
        archived=C12/'frozen-source/frontend'/original
        assert sha256(archived.read_bytes()).hexdigest()==digest,(report,original)
        checks.append({'report':str(report.relative_to(EV)),'bundle':original,'sha256':digest,'matches':str(archived.relative_to(ROOT))})
for name,folder in [('frozen-after.json','frozen-v1-source'),('frozen-v2-after.json','frozen-v2-source')]:
    for original,digest in json.loads((EV/name).read_text())['sha256'].items():
        assert sha256((EV/folder/original).read_bytes()).hexdigest()==digest
# These are metadata-byte checks, not approval of mixed-development execution.
(EV/'snapshot-check.json').write_text(json.dumps({'allPassed':True,'checked':len(checks),
  'qualifiedExecution':['development-after: mixed main.py; initial metadata only, not an after gate'],
  'bindings':checks},ensure_ascii=False,indent=2)+'\n')
print(len(checks),'source/bundle bindings match; mixed development explicitly excluded from gates')

"""Verify every retained browser source and bundle binding, including dev failures."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

EV = Path(__file__).resolve().parent.parent/'实验'
ROOT = Path(__file__).resolve().parents[5]
checks=[]
for report in sorted(EV.rglob('*.json')):
    if any(part in report.parts for part in ('source','frozen-source','served')): continue
    data=json.loads(report.read_text())
    if not isinstance(data,dict) or 'sourceSha256' not in data: continue
    for original,digest in data['sourceSha256'].items():
        # Existing probes resolve sources from frontend; the cleanup script
        # records repository-relative paths explicitly.
        root_relative=report.name=='fixture-cleanup.json'
        repo=Path(original) if root_relative else (ROOT/'frontend'/original).resolve().relative_to(ROOT)
        choices=[report.parent/'source'/repo,report.parent/Path(original).name,EV/'frozen-source'/repo,ROOT/repo]
        found=next((p for p in choices if p.is_file() and sha256(p.read_bytes()).hexdigest()==digest),None)
        provenance=str(found.relative_to(ROOT)) if found else None
        if not found:
            head=data.get('head',data.get('sourceHead'))
            payload=subprocess.check_output(['git','show',head+':'+str(repo)],cwd=ROOT)
            assert sha256(payload).hexdigest()==digest,(report,original)
            provenance='git:'+head+':'+str(repo)
        checks.append({'report':str(report.relative_to(EV)),'source':original,'sha256':digest,'matches':provenance})
    for original,digest in data.get('servedBundleSha256',{}).items():
        choices=[report.parent/'served'/original,EV/'frozen-source/frontend'/original]
        found=next((p for p in choices if p.is_file() and sha256(p.read_bytes()).hexdigest()==digest),None)
        assert found,(report,original)
        checks.append({'report':str(report.relative_to(EV)),'bundle':original,'sha256':digest,'matches':str(found.relative_to(ROOT))})
frozen=json.loads((EV/'frozen-after.json').read_text())
for original,digest in frozen['sha256'].items():
    assert sha256((EV/'frozen-source'/original).read_bytes()).hexdigest()==digest
(EV/'snapshot-check.json').write_text(json.dumps({'checked':len(checks),'allPassed':True,'bindings':checks},ensure_ascii=False,indent=2)+'\n')
print(len(checks),'source/bundle bindings verified; frozen bytes verified')

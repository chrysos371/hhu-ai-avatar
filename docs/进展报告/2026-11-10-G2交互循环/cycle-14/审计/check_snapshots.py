from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
EV=HERE.parent/'实验'
ROOT=HERE.parents[4]
C12=HERE.parent.parent/'cycle-12/实验'
checks=[]
for report in sorted(EV.rglob('*.json')):
    if 'frozen-source' in report.parts:continue
    data=json.loads(report.read_text())
    if not isinstance(data,dict) or 'sourceSha256' not in data:continue
    for original,digest in data['sourceSha256'].items():
        root_relative=original.startswith(('src/avatar/','scripts/','evals/'))
        repo=Path(original) if root_relative else (ROOT/'frontend'/original).resolve().relative_to(ROOT)
        choices=[EV/'frozen-source'/repo,ROOT/repo]
        match=next((p for p in choices if p.is_file() and sha256(p.read_bytes()).hexdigest()==digest),None)
        if match:match=str(match.relative_to(ROOT))
        else:
            payload=subprocess.check_output(['git','show',data['head']+':'+str(repo)],cwd=ROOT)
            assert sha256(payload).hexdigest()==digest,(report,original)
            match='git:'+data['head']+':'+str(repo)
        checks.append({'report':str(report.relative_to(EV)),'source':original,'sha256':digest,'matches':match})
    for original,digest in data.get('servedBundleSha256',{}).items():
        archived=C12/'frozen-source/frontend'/original
        assert sha256(archived.read_bytes()).hexdigest()==digest
        checks.append({'report':str(report.relative_to(EV)),'bundle':original,'sha256':digest,'matches':str(archived.relative_to(ROOT))})
for original,digest in json.loads((EV/'frozen-after.json').read_text())['sha256'].items():
    assert sha256((EV/'frozen-source'/original).read_bytes()).hexdigest()==digest
(EV/'snapshot-check.json').write_text(json.dumps({'allPassed':True,'checked':len(checks),'bindings':checks},ensure_ascii=False,indent=2)+'\n')
print(len(checks),'source/bundle bindings and frozen files verified')

"""Finite fresh installation; every child status captured, no experiment deadline."""
from pathlib import Path
from hashlib import sha256
import json,subprocess,sys
ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
A=Path('/data/Users/zrh/data/hhu-ai-avatar')
ENV=A/'envs/hhu-ai-avatar-release-final-v7'
PREP=A/'artifacts/release/final-install-preparation-v8'
def h(p):return sha256(p.read_bytes()).hexdigest()
def write(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2);f.write('\n')
def main():
 assert not ENV.exists();PREP.mkdir(exist_ok=False)
 steps=[]
 commands=[[sys.executable,'-B','-m','venv',str(ENV)], [str(ENV/'bin/python'),'-I','-B','-m','pip','install','--constraint',str(HERE.parent/'004-版本与启动基础设施/runtime-constraints-v1.txt'),str(A/'artifacts/release/final-build-v8/dist/hhu_ai_avatar-2.0.0-py3-none-any.whl')],[str(ENV/'bin/python'),'-I','-B','-m','pip','check']]
 for i,argv in enumerate(commands):
  with (PREP/f'step-{i}.log').open('x') as log:r=subprocess.run(argv,cwd=PREP,stdout=log,stderr=subprocess.STDOUT)
  steps.append(dict(argv=argv,actual_returncode=r.returncode));(PREP/'progress.json').write_text(json.dumps(steps,indent=2)+'\n');assert r.returncode==0
 for driver,label,key in [('install_smoke_v11.py','install-smoke-v11','install'),('installed_soak_v6.py','installed-soak-v6','soak')]:
  with (PREP/(key+'.log')).open('x') as log:r=subprocess.run([str(ENV/'bin/python'),'-I','-B',str(HERE/driver)],cwd=PREP,stdout=log,stderr=subprocess.STDOUT)
  raw=A/'artifacts/release'/label/'result.json';v=json.loads(raw.read_text())
  if key=='install':o=dict(actual_smoke_driver_returncode=r.returncode,result=v,raw=str(raw),raw_sha256=h(raw),preparation=str(PREP),preparation_actual_steps=steps,preparation_sha256={f.name:h(f) for f in PREP.glob('*') if f.is_file()})
  else:o=dict(actual_driver_returncode=r.returncode,summary={k:x for k,x in v.items() if k not in ('events','installed_sha256')},completed_events=len(v['events']),verified_installed_files=len(v['installed_sha256']),raw=str(raw),raw_sha256=h(raw))
  write(HERE/(label+'-proof.json'),o);assert r.returncode==0 and v['passed'];print(label,'actual exit',r.returncode,flush=True)
if __name__=='__main__':main()

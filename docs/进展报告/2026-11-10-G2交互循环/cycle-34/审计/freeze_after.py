"""Freeze committed after sources and the separately archived actual browser bundle."""
from pathlib import Path
import json,sys,subprocess
ROOT=Path(__file__).resolve().parents[5];sys.path.insert(0,str(Path(__file__).resolve().parent))
from revision_common import BASE,PROTOCOL,source_paths,digest,verify_freeze,verify_historical_binding
work=BASE/'审计/工作目录/002-系统回归';paths=source_paths('after');paths.update(str((BASE/'审计'/name).relative_to(ROOT)) for name in ('run_product_regression.py','freeze_after.py','verify_native_revision.py'))
tracked=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0'))
archive=json.loads((work/'browser-dist-archive.json').read_text());paths.add(str((work/'browser-dist-archive.json').relative_to(ROOT)))
for name,entry in archive.items():
 assert digest(ROOT/name)==digest(ROOT/entry['archived_path'])==entry['sha256'];paths.add(entry['archived_path'])
for mode in ('full-python','default-browser'):
 binding=json.loads((work/(mode+'-binding.json')).read_text());assert binding['exit_code']==0 and binding['source_unchanged'];paths.update(name for name in binding['source_sha256'] if name in tracked);paths.add(str((work/(mode+'.log')).relative_to(ROOT)))
 for name,value in binding['source_sha256'].items():assert digest(ROOT/name)==value,name
 if mode=='default-browser':assert binding['runtime_matches'];paths.add(str((work/'browser-runtime.json').relative_to(ROOT)))
protocol=json.loads((ROOT/PROTOCOL).read_text());frozen={**protocol,'phase':'after','source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'sha256':{name:digest(ROOT/name) for name in sorted(paths)}}
verify_historical_binding(frozen);target=BASE/'审计/工作目录/001-自动情绪版本失效/native-after-freeze.json';assert not target.exists();target.write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n');sha=digest(target);verify_freeze(target,sha,phase='after');print(len(paths),sha,frozen['source_ref'])

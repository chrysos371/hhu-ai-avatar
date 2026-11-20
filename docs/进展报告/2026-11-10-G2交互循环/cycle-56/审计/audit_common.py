"""Read-only C56 audit helpers; no model/runtime admission imports."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
AUDIT=BASE/'审计'
OUT=AUDIT/'收尾核验'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def require(ok,message):
    if not ok:raise ValueError(message)


def read(path):return json.loads(Path(path).read_text())


def sha(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):result.update(block)
    return result.hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')


def historical(ref,names):
    raw=subprocess.check_output(['git','archive','--format=tar',ref,'--',*names],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
        return {m.name:hashlib.sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def software():
    folder=AUDIT/'工作目录/002-当前软件回归';p=read(folder/'python-first-binding.json')
    driver=load('c56_regression_current_snapshot',AUDIT/'run_python_regression.py')
    require(p['exit_code']==0 and p['source_unchanged'] and p['source_inputs']==812
        and p['driver_sha256']==sha(AUDIT/'run_python_regression.py')
        and p['log_sha256']==sha(folder/'python-first.log'),'actual full regression evidence differs')
    require('2562 passed, 1 skipped' in (folder/'python-first.log').read_text(),'full regression counts differ')
    require(driver.snapshot()==p['source_git_sha256'] and historical(p['head'],p['source_git_sha256'])==p['source_git_sha256'],'current/Git software input set changed')
    return p

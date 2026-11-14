"""Install an isolated tokenizer-only environment; no Torch or model weights."""
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/005-真实分词预检'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def main():
    protocol=json.loads((WORK/'tokenizer-protocol.json').read_text())
    target=Path(protocol['environment']);assert not target.exists()
    output=WORK/'environment-v1.json';assert not output.exists()
    assert subprocess.run(['mountpoint','-q','/data']).returncode==0
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='',
        TMPDIR=str(ASSETS/'tmp'),PIP_CACHE_DIR=str(ASSETS/'cache/pip'),HF_HOME=str(ASSETS/'cache/huggingface'))
    result={'status':'running','environment':str(target),'scope':protocol['scope'],'steps':[]}
    def save():output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    def run(name,args):
        log=WORK/(name+'.log');assert not log.exists()
        with log.open('x') as stream:r=subprocess.run(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        result['steps'].append({'name':name,'argv':args,'returncode':r.returncode});save()
        if r.returncode:raise RuntimeError(name+' failed; retained log')
        print(name,'complete',flush=True)
    save()
    try:
        run('tokenizer-venv-create',['/usr/bin/python3.10','-m','venv',str(target)])
        python=str(target/'bin/python');wheel=ASSETS/'cache/pip-bootstrap/pip-25.3-py3-none-any.whl'
        assert hashlib.sha256(wheel.read_bytes()).hexdigest()=='9655943313a94722b7774661c21049070f6bbb0a1516bf02f7c8d5d9201514cd'
        run('tokenizer-pip-bootstrap',[python,'-m','pip','--isolated','install','--no-deps','--no-index',str(wheel)])
        packages=[name+'=='+version for name,version in protocol['packages'].items() if name!='pip']
        run('tokenizer-package-install',[python,'-m','pip','--isolated','install','--index-url',protocol['package_index'],
            '--cache-dir',str(ASSETS/'cache/pip'),'--timeout','60','--retries','3','--progress-bar','off',
            '--report',str(WORK/'package-report.json'),*packages])
        run('tokenizer-pip-check',[python,'-m','pip','check'])
        run('tokenizer-freeze',[python,'-m','pip','freeze','--all'])
        code='''import importlib.metadata as m,importlib.util,json,sys
from transformers import AutoTokenizer
names=['pip','transformers','tokenizers','huggingface_hub','safetensors','numpy','Jinja2']
print(json.dumps({'prefix':sys.prefix,'versions':{n:m.version(n) for n in names},'torch_available':importlib.util.find_spec('torch') is not None,'AutoTokenizer_imported':True}))
'''
        actual=json.loads(subprocess.check_output([python,'-B','-c',code],env=env,cwd=ROOT,text=True))
        assert actual['versions']==protocol['packages'] and actual['torch_available'] is False
        result.update(status='complete',CPU_import_probe=actual,LLM_model_constructions=0,CUDA_allocation=False,training_steps=0)
    except BaseException as e:
        result.update(status='failed',error=type(e).__name__+': '+str(e));save();raise
    save();print('C51 tokenizer-only environment complete;0 Torch/model/CUDA/training',flush=True)


if __name__=='__main__':main()

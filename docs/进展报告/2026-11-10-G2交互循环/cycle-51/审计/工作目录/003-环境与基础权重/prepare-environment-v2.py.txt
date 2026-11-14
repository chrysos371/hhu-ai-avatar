"""Install an isolated project training environment; never construct a model."""
import importlib.metadata
import hashlib
import urllib.request
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
PREPARATION=BASE/'审计/工作目录/003-环境与基础权重'
WORK=PREPARATION/'environment-v2'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def inventory(python,env):
    script='import importlib.metadata as m,json,sys;print(json.dumps({"prefix":sys.prefix,"versions":{d.metadata["Name"]:d.version for d in m.distributions()}}))'
    return json.loads(subprocess.check_output([str(python),'-B','-c',script],cwd=ROOT,env=env,text=True))


def main():
    assert subprocess.run(['mountpoint','-q','/data']).returncode==0
    WORK.mkdir(exist_ok=False)
    output=WORK/'environment-v2.json';assert not output.exists()
    target=ASSETS/'envs/hhu-ai-avatar-train';assert target.is_dir()
    prior=json.loads((PREPARATION/'environment-v1.json').read_text());assert prior['status']=='failed' and prior['target']==str(target)
    protocol=json.loads((PREPARATION/'preparation-protocol.json').read_text())
    assert str(ASSETS)==protocol['data_root'] and protocol['model_constructions']==0
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1',
        TMPDIR=str(ASSETS/'tmp'),PIP_CACHE_DIR=str(ASSETS/'cache/pip'),
        XDG_CACHE_HOME=str(ASSETS/'cache/xdg'),HF_HOME=str(ASSETS/'cache/huggingface'))
    originals={name:inventory(ASSETS/'envs'/name/'bin/python',env) for name in ('hhu-ai-avatar','hhu-ai-avatar-llm')}
    result={'status':'running','started_UTC':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),
        'target':str(target),'original_environments_before':originals,'steps':[],
        'model_constructions':0,'CUDA_allocation':False,'training_steps':0}
    write(output,result)
    def run(name,args):
        log=WORK/(name+'.log');assert not log.exists()
        started=time.monotonic()
        with log.open('x') as stream:
            command=subprocess.run(args,cwd=ROOT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        result['steps'].append({'name':name,'argv':args,'returncode':command.returncode,'seconds':time.monotonic()-started})
        write(output,result)
        if command.returncode:raise RuntimeError(name+' failed; preserve its log before retry')
        print(name,'completed',flush=True)
    try:
        python=str(target/'bin/python')
        seed=inventory(python,env);assert set(seed['versions'])=={'pip','setuptools'} and seed['versions']['pip']=='22.0.2'
        result['resumed_seed_only_environment']=seed
        url='https://pypi.org/pypi/pip/25.3/json'
        with urllib.request.urlopen(url,timeout=60) as stream:metadata=json.load(stream)
        artifact=next(f for f in metadata['urls'] if f['filename']=='pip-25.3-py3-none-any.whl')
        write(WORK/'pip-bootstrap-metadata.json',metadata)
        wheel=ASSETS/'cache/pip-bootstrap'/artifact['filename'];wheel.parent.mkdir(parents=True,exist_ok=True)
        if not wheel.exists():
            with urllib.request.urlopen(artifact['url'],timeout=60) as stream:wheel.write_bytes(stream.read())
        assert hashlib.sha256(wheel.read_bytes()).hexdigest()==artifact['digests']['sha256']
        result['pip_bootstrap']={'source':url,'wheel':str(wheel),'sha256':artifact['digests']['sha256']}
        run('environment-pip-bootstrap',[python,'-m','pip','--isolated','install','--no-deps','--no-index',str(wheel)])
        assert inventory(python,env)['versions']['pip']=='25.3'
        common=[python,'-m','pip','--isolated','install','--cache-dir',str(ASSETS/'cache/pip'),
            '--timeout','60','--retries','3','--progress-bar','off']
        run('environment-torch-install',common+['--index-url',protocol['torch']['index'],
            '--report',str(WORK/'torch-pip-report.json'),'torch=='+protocol['torch']['version']])
        core={key:importlib.metadata.version(key) for key in ('numpy','edge-tts','openai','python-dotenv')}
        constraints=WORK/'core-constraints-v1.txt'
        constraints.write_text(''.join(k+'=='+v+'\n' for k,v in core.items()))
        run('environment-training-install',common+['--index-url',protocol['python_dependencies_source'],
            '--report',str(WORK/'training-pip-report.json'),'-c',str(constraints),
            '-r',str(ROOT/'training/requirements-eval.txt'),'-r',str(ROOT/'requirements.txt')])
        run('environment-pip-check',[python,'-m','pip','check'])
        run('environment-pip-freeze',[python,'-m','pip','freeze','--all'])
        script='''import json,sys,torch,transformers,peft,lmformatenforcer,interegular
from transformers import Qwen3ForCausalLM,AutoTokenizer
from peft import get_peft_model
print(json.dumps({'prefix':sys.prefix,'torch':torch.__version__,'CUDA_build':torch.version.cuda,'CUDA_initialized':torch.cuda.is_initialized(),'Qwen3_class':Qwen3ForCausalLM.__name__,'torch_cuda_visible_count':torch.cuda.device_count(),'CPU_imports_passed':True}))
'''
        actual=json.loads(subprocess.check_output([python,'-B','-c',script],cwd=ROOT,env=env,text=True))
        assert actual['torch']==protocol['torch']['version'] and actual['CUDA_initialized'] is False
        assert actual['torch_cuda_visible_count']==0 and actual['CPU_imports_passed']
        result['CPU_import_probe']=actual;result['installed']=inventory(python,env)
        result['original_environments_after']={name:inventory(ASSETS/'envs'/name/'bin/python',env) for name in originals}
        assert result['original_environments_after']==originals
        result.update(status='complete',existing_environments_unchanged=True)
    except BaseException as error:
        result.update(status='failed',error=type(error).__name__+': '+str(error));write(output,result);raise
    write(output,result)
    print('C51 isolated training environment ready: CPU imports/pip check;0 model construction/CUDA allocation/training',flush=True)


if __name__=='__main__':main()

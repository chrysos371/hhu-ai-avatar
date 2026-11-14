"""Read project-owned training conditions and actual evaluation protection, CPU only."""
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    output=BASE/'审计/工作目录/001-训练条件与入口/readiness-first.json';assert not output.exists()
    assert subprocess.run(['mountpoint','-q','/data']).returncode==0
    env=dict(os.environ,CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
    package_names=['torch','transformers','peft','accelerate','huggingface_hub','tokenizers','safetensors','llama_cpp_python']
    script='''import importlib.metadata as m,json,sys
names=NAME_LIST
versions={}
for name in names:
 try: versions[name]=m.version(name)
 except m.PackageNotFoundError: versions[name]=None
print(json.dumps({'executable':sys.executable,'prefix':sys.prefix,'versions':versions}))
'''.replace('NAME_LIST',repr(package_names))
    environments=[]
    for name in ('hhu-ai-avatar','hhu-ai-avatar-llm','hhu-ai-avatar-train'):
        python=ASSETS/'envs'/name/'bin/python'
        record={'name':name,'path':str(python),'exists':python.is_file()}
        if record['exists']:
            actual=subprocess.run([str(python),'-B','-c',script],cwd=ROOT,env=env,text=True,capture_output=True)
            record.update(returncode=actual.returncode,stdout=actual.stdout,stderr=actual.stderr)
            assert actual.returncode==0;record['metadata']=json.loads(actual.stdout)
        environments.append(record)
    help_result=subprocess.run(['./scripts/companion_lab.sh','--help'],cwd=ROOT,env=env,text=True,capture_output=True)
    assert help_result.returncode==0
    files=subprocess.check_output(['rg','--files','--hidden','--no-ignore',str(ASSETS/'models'),str(ASSETS/'cache/huggingface')],text=True).splitlines()
    weight_names=[n for n in files if n.endswith(('.safetensors','.bin','.gguf'))]
    # This is existence/size inventory; do not call un-hashed weights identity verified.
    weights=[{'path':n,'bytes':Path(n).stat().st_size,'sha256_verified_in_this_probe':False} for n in weight_names]
    from avatar.lab.data import evaluation_texts
    protected_texts,hashes=evaluation_texts()
    queries=[]
    for number,filename in [(47,'native-history-cases.json'),(48,'typed-history-cases.json'),(49,'minimal-history-cases.json'),(50,'natural-history-cases.json')]:
        path=ROOT/f'evals/interaction/cycle-{number}'/filename;material=json.loads(path.read_text())
        queries.append({'file':str(path.relative_to(ROOT)),'file_sha256':sha(path),
            'included_in_protected_hashes':str(path.relative_to(ROOT)) in hashes,
            'cases':len(material['cases']),
            'query_inputs_absent_from_text_corpus':sum(c['query_text'] not in protected_texts for c in material['cases']),
            'followup_inputs_absent_from_text_corpus':sum(c['followup_text'] not in protected_texts for c in material['cases'])})
    sources=['scripts/companion_lab.sh','scripts/train_companion_smoke.py','scripts/prepare_companion_training.py',
        'src/avatar/lab/__main__.py','src/avatar/lab/training.py','src/avatar/lab/data.py',
        'experiments/style/README.md','experiments/style/lora-config.json','training/companion/smoke-config.json',
        'training/requirements-smoke.txt','training/requirements-eval.txt']
    result={'completed':True,'scope':'read-only project-owned metadata, existence and actual CPU help/protection; no model/GPU allocation',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'collector_sha256':sha(__file__),'source_sha256':{n:sha(ROOT/n) for n in sources},
        'environments':environments,'training_cli_help':{'returncode':help_result.returncode,'stdout':help_result.stdout,'stderr':help_result.stderr},
        'local_weights_existence_only':weights,'local_models_dirs':sorted(p.name for p in (ASSETS/'models').iterdir()),
        'old_style_lab_artifact_dir_exists':(ASSETS/'artifacts/style-lab').is_dir(),
        'protected_text_count':len(protected_texts),'protected_file_count':len(hashes),
        'actual_history_material_coverage':queries,
        'main_trainer_has_gradient_checkpointing_enable':'model.gradient_checkpointing_enable(' in (ROOT/'src/avatar/lab/training.py').read_text(),
        'main_trainer_uses_nonreentrant_checkpointing':'"use_reentrant": False' in (ROOT/'src/avatar/lab/training.py').read_text(),
        'independent_smoke_config_has_checkpoint_flag':'gradient_checkpointing' in json.loads((ROOT/'training/companion/smoke-config.json').read_text()),
        'GPU_inventory_without_allocation':subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True),
        'model_constructions':0,'training_steps':0,'native_inference_calls':0,
        'limits':'No model SHA verification or CUDA compatibility/training proof; standalone old smoke is distinct from avatar.lab main trainer.'}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'environments':[{k:r[k] for k in ('name','exists')} for r in environments],
        'weight_files':len(weights),'history_coverage':queries,'main_checkpointing':result['main_trainer_has_gradient_checkpointing_enable'],
        'model_constructions':0},ensure_ascii=False))


if __name__=='__main__':main()

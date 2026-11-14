"""C54 frozen-source, data, environment and historical-adapter admission; no Torch."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
AUDIT=BASE/'审计'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
WORK=AUDIT/'工作目录/006-真实执行输入'
RUN=ASSETS/'artifacts/c54/real-target-transfer-v1'
DATA=ASSETS/'artifacts/c54/target-expression-v1/sft.jsonl'
TOKEN_RUN=ASSETS/'artifacts/c54/target-tokenization-v1'
PROTOCOL=ROOT/'evals/interaction/cycle-54/correction-transfer-protocol.json'
CASES=PROTOCOL.with_name('correction-transfer-cases.json')
C51=BASE.parent/'cycle-51'
PREPARATION=C51/'审计/工作目录/003-环境与基础权重'
TOKENIZATION=C51/'审计/工作目录/005-真实分词预检'
LOCK=PREPARATION/'model-v1/models.lock.json'
STAGES=('base','old_adapter','train','reload','new_adapter')
EVAL_STAGES=('base','old_adapter','new_adapter')
OLD_ADAPTER=ASSETS/'artifacts/c52/real-transfer-v1/adapter'
SEALS={51:'8897ba4fa31d23d6ed8153f4c5de48e41391b982b2269b9e4d3bd482eb74895e',
       52:'6786ce8a17dfcbcb777efaf8333f75e348c33d8eb927ac7f39371ae10b2cf092',
       53:'5175b02e457dfa9450156b4ff793447e4e722354905e426094f2ef42b974d6f2'}


def require(condition,message):
    if not condition:raise ValueError(message)

def read(path):return json.loads(Path(path).read_text())

def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):value.update(block)
    return value.hexdigest()

def write_new(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')

def typed(actual,expected,label):
    for key,value in expected.items():
        require(type(actual.get(key)) is type(value) and actual[key]==value,label+': '+key)


def environment_reader():
    p=C51/'审计/environment_receipt.py'
    spec=importlib.util.spec_from_file_location('c54_c51_environment_reader',p)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def old_binding_files():
    return {'old_manifest':OLD_ADAPTER/'manifest.json','old_steps':OLD_ADAPTER/'steps.json',
        'old_weights':OLD_ADAPTER/'adapter/adapter_model.safetensors',
        'old_config':OLD_ADAPTER/'adapter/adapter_config.json','old_probe':OLD_ADAPTER/'probe.pt'}


def protocol_check():
    p=read(PROTOCOL)
    require(type(p.get('version')) is int and p['version']==1,'C54 protocol version differs')
    require(p['cases_sha256']==sha(CASES) and len(read(CASES)['cases'])==22,'C54 cases identity differs')
    require(p['default_activation_authorized'] is False and p['whole_experiment_wallclock_cutoff'] is None,
        'C54 isolated experiment without whole-wallclock cutoff required')
    require(p['execution']['stages']==list(STAGES) and p['execution']['no_retries'] is True
        and p['execution']['fresh_process_each_stage'] is True,'C54 stage/no-retry contract differs')
    require(p['training']==read(TOKENIZATION/'training-config-v1.json'),'registered original training settings differ')
    typed(p['training'],{'seed':42,'max_length':2048,'max_steps':44,'epochs_cap':1,'gradient_accumulation_steps':4,
        'lora_r':8,'lora_alpha':16,'lora_dropout':0.05,'target_modules':['q_proj','v_proj'],'learning_rate':2e-5,
        'analysis_adapter_enabled':False,'dtype':'bfloat16','attention':'sdpa'},'C54 training contract')
    typed(p['evaluation'],{'cases':22,'repetitions':3,'trials_per_phase':66,'generation_cap_per_phase':134,
        'phase_generation_cap':134,'three_phase_generation_cap':402,'save_reload_probe_generation_cap':2,
        'total_generation_cap':404,'context_tokens':8192,'reply_tokens':512,'analysis_tokens':512,
        'do_sample':False,'enable_thinking':False,'query_clock_epoch':1794650400.0,
        'controlled_query_clock_epoch':1794650400.0},'C54 evaluation contract')
    require(p['evaluation']['phases']==list(EVAL_STAGES),'C54 evaluation stages differ')
    typed(p['GPU'],{'min_free_MiB':36000,'max_used_MiB':1024,'max_utilization_percent':10,
        'single_card_each_stage':True,'no_CPU_or_disk_offload':True},'C54 GPU contract')
    require(sha(DATA.with_name('manifest.json'))==p['data']['manifest_sha256'],'C54 data manifest differs')
    manifest=read(DATA.with_name('manifest.json'))
    require(manifest['sft_sha256']==sha(DATA) and manifest['dev_sha256']==sha(DATA.with_name('dev.jsonl')),
        'C54 data bytes differ')
    require(manifest['protocol_sha256']==p['data']['data_preparation_protocol_sha256']==
        sha(AUDIT/'工作目录/001-目标表达对照/protocol-v1.json'),'C54 data-preparation protocol differs')
    require(manifest['target_variants_sha256']==p['data']['target_variants_sha256']==
        sha(AUDIT/'工作目录/001-目标表达对照/target-variants-v1.json'),'C54 target variants differ')
    from avatar.lab.training import load_data
    train,dev,_=load_data(DATA)
    require(len(train)==176 and len(dev)==44 and manifest['human_reviewed'] is False,'C54 material scope differs')
    entry=next(e for e in read(LOCK)['models'] if e['name']=='4b')
    require(entry['repo']==p['model']['model_id'] and entry['revision']==p['model']['revision']
        and {f['path']:f['sha256'] for f in entry['files']}==p['model']['sha256'],'prepared base identity differs')
    old=p['old_adapter'];files=old_binding_files()
    require(old['root']==str(OLD_ADAPTER) and sha(files['old_weights'])==old['adapter_weights_sha256']
        and sha(files['old_config'])==old['adapter_config_sha256'] and sha(files['old_manifest'])==old['manifest_sha256'],
        'C52 historical adapter differs')
    old_manifest=read(files['old_manifest'])
    require(old_manifest['status']=='completed' and old_manifest['base_revision']==entry['revision'],
        'C52 historical training identity differs')
    return p


def preparation_check():
    environment=environment_reader().admitted_environment()
    require(environment['status']=='complete','admitted environment incomplete')
    for number,value in SEALS.items():
        cycle=BASE.parent/f'cycle-{number:02}';path=cycle/'审计/证据清单.json'
        require(sha(path)==value,'prior seal identity differs: '+str(number))
        require(all((cycle/n).resolve().is_relative_to(cycle.resolve()) and sha(cycle/n)==v
            for n,v in read(path).items()),'prior sealed bytes changed: '+str(number))
    base=read(PREPARATION/'model-v1/model-preparation.json')
    require(base['status']=='complete' and base['shard_index_verified']
        and base['all_git_or_LFS_identities_verified'],'C51 base preparation incomplete')
    token=read(AUDIT/'工作目录/003-真实分词/target-tokenization-v1.json')
    require(token['verified'] and token['actual_prompt_token_pairs_identical']==220
        and token['training_module_sha256']==sha(ROOT/'src/avatar/lab/training.py'),
        'C54 current tokenizer proof/source differs')
    require(token['tokens_sha256']==sha(TOKEN_RUN/'tokens.json') and token['preflight_sha256']==sha(TOKEN_RUN/'preflight.json'),
        'C54 actual token artifacts changed')
    preflight=read(TOKEN_RUN/'preflight.json')
    require(preflight['dataset_manifest_sha256']==sha(DATA.with_name('manifest.json'))
        and preflight['config_sha256']==sha(TOKENIZATION/'training-config-v1.json'),'C54 tokenizer input binding differs')
    typed(token['split_counts']['train'],{'supervised_tokens_including_EOS':3856},'C54 training supervision')
    typed(token['split_counts']['dev'],{'supervised_tokens_including_EOS':1012},'C54 dev supervision')
    independent=read(AUDIT/'工作目录/002-独立原料与隔离/independent-data-v1.json')
    require(independent['verified'] and independent['actual_exact_prefix_pairs']==220
        and independent['manifest_sha256']==sha(DATA.with_name('manifest.json'))
        and len(independent['actual_new_eval_fields_rejected'])==44,'C54 independent material gate missing')
    rehearsal=read(AUDIT/'工作目录/004-新题路由演练/independent-rehearsal-v1.json')
    require(rehearsal['verified'] and rehearsal['actual_CPU_trials']==66
        and rehearsal['actual_SQL_reconstructed']==132,'new-case rehearsal incomplete')
    observer=read(AUDIT/'工作目录/005-实际训练前向采证/capture-cpu-v1.json')
    require(observer['passed'] and len(observer['faults_rejected'])==7
        and observer['observer_sha256']==sha(AUDIT/'labeled_forward_capture.py'),'labeled-forward CPU control missing')
    from labeled_forward_capture import expected_records
    require(len(expected_records(read(TOKEN_RUN/'tokens.json')))==220,'ambiguous labeled tensor identities')
    return environment


def required_inputs():
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    names={n for n in tracked if n.startswith(('src/','evals/','training/'))
        or n in ('requirements.txt','pyproject.toml','scripts/project_env.sh','scripts/project-python')}
    names.update(str(p.relative_to(ROOT)) for p in AUDIT.glob('*.py'))
    for folder in (AUDIT/'工作目录').iterdir():
        if folder.is_dir() and folder.name[:3] in ('001','002','003','004','005','007'):
            names.update(str(p.relative_to(ROOT)) for p in folder.rglob('*') if p.is_file())
    for number in SEALS:names.add(str((BASE.parent/f'cycle-{number:02}/审计/证据清单.json').relative_to(ROOT)))
    for name in ('capture_transformers.py','capture_probe.py','replay_common.py'):
        names.add(str((BASE.parent/'cycle-52/审计'/name).relative_to(ROOT)))
    names.add(str((BASE.parent/'cycle-52/审计/工作目录/006-调用结束态核验/trace_transition.py').relative_to(ROOT)))
    for name in ('sample_history.py','verify_observations.py','text_shape.py'):
        names.add(str((BASE.parent/'cycle-50/审计'/name).relative_to(ROOT)))
    reader=environment_reader();source,_=reader.successful_source(read(reader.ADMISSION)['preparation_source'])
    for path in [reader.ADMISSION,source,C51/'审计/environment_receipt.py',C51/'审计/verify_training_environment.py',
        LOCK,PREPARATION/'model-v1/model-preparation.json',TOKENIZATION/'training-config-v1.json',
        BASE.parent/'cycle-52/审计/工作目录/003-真实执行输入/train-verified.json',
        BASE.parent/'cycle-53/审计/工作目录/004-当前软件回归/python-first-binding.json']:
        names.add(str(path.relative_to(ROOT)))
    return sorted(names)


def historical(ref,names):
    raw=subprocess.check_output(['git','archive','--format=tar',ref,'--',*names],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
        return {m.name:hashlib.sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}


def external_inputs():
    return {**{str(DATA.parent/n):sha(DATA.parent/n) for n in ('sft.jsonl','dev.jsonl','manifest.json')},
        **{str(TOKEN_RUN/n):sha(TOKEN_RUN/n) for n in ('tokens.json','preflight.json')},
        **{str(p):sha(p) for p in old_binding_files().values()}}


def verify_freeze(path,expected):
    path=Path(path).resolve()
    require(path==(WORK/'freeze-v1.json').resolve(),'C54 registered freeze path required')
    require(path.is_file(),'C54 frozen execution descriptor missing')
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected) is not None and sha(path)==expected,
        'C54 freeze SHA differs')
    frozen=read(path)
    protocol_check();preparation_check()
    require(frozen['run_root']==str(RUN) and frozen['stages']==list(STAGES)
        and frozen['prior_seals_sha256']=={str(k):v for k,v in SEALS.items()},'C54 freeze sequence/seals differ')
    require(frozen['default_activation_authorized'] is False,'C54 default activation forbidden')
    names=required_inputs()
    require(set(names)==set(frozen['sha256']),'C54 execution input set changed')
    require(all(sha(ROOT/n)==v for n,v in frozen['sha256'].items()),'C54 execution bytes changed')
    require(historical(frozen['source_ref'],names)==frozen['sha256'],'C54 frozen sources were not committed')
    require(external_inputs()==frozen['external_sha256'],'C54 external data/tokens/old adapter changed')
    return frozen


def training_binding_files():
    return {'training_manifest_sha256':RUN/'adapter/manifest.json','optimizer_log_sha256':RUN/'adapter/steps.json',
        'adapter_model_sha256':RUN/'adapter/adapter/adapter_model.safetensors',
        'adapter_config_sha256':RUN/'adapter/adapter/adapter_config.json','saved_probe_sha256':RUN/'adapter/probe.pt'}


def verify_training_binding():
    proof=read(RUN/'ledger/train-verified.json')
    require(all(proof[k]==sha(p) for k,p in training_binding_files().items()),'verified new training artifacts changed')

"""Actual HF tokenizer/production encoder checks; no Torch, weights, GPU or training."""
import copy
import hashlib
import importlib.metadata
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from avatar.lab.training import preflight,load_data,encode_record
from avatar.lab.common import sha

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/005-真实分词预检'
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')


def check(encoded,row,tokenizer,cap):
    ids,labels=encoded['input_ids'],encoded['labels']
    prefix=tokenizer.apply_chat_template(row['messages'][:-1],tokenize=True,
        add_generation_prompt=True,enable_thinking=False)
    assert 0<len(prefix)<len(ids)<=cap and len(ids)==len(labels)
    assert ids[:len(prefix)]==prefix and labels[:len(prefix)]==[-100]*len(prefix)
    assert labels[len(prefix):]==ids[len(prefix):] and labels[-1]==tokenizer.eos_token_id
    assert all(type(n) is int for n in ids+labels)
    assert tokenizer.decode(labels[len(prefix):-1],skip_special_tokens=False,
        clean_up_tokenization_spaces=False)==row['messages'][-1]['content']
    return {'id':row['id'],'prefix_tokens':len(prefix),'supervised_tokens':len(ids)-len(prefix),
        'total_tokens':len(ids),'token_ids_sha256':hashlib.sha256(json.dumps(ids).encode()).hexdigest()}


def main():
    protocol=json.loads((WORK/'tokenizer-protocol.json').read_text())
    environment=json.loads((WORK/'environment-v1.json').read_text())
    assert environment['status']=='complete' and sys.prefix==protocol['environment']
    assert importlib.util.find_spec('torch') is None
    output=WORK/'mask-preflight-v1.json';assert not output.exists()
    source=Path(protocol['data']);model=Path(protocol['model_assets'])
    assets=json.loads((BASE/'审计/工作目录/003-环境与基础权重/tokenizer-assets-v1.json').read_text())
    assert assets['verified'] and all(sha(Path(f['path']))==f['sha256'] for f in assets['files'])
    config=WORK/'training-config-v1.json';assert config.is_file()
    output_folder=ASSETS/'artifacts/c51/tokenizer-preflight-v1';assert not output_folder.exists()
    result=preflight(source,model,output_folder,config)
    assert result['samples']==176 and result['dev_samples']==44 and not result['rejected']
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True,trust_remote_code=False)
    train,dev,manifest=load_data(source);tokens=json.loads((output_folder/'tokens.json').read_text())
    stats=[]
    for split,rows in (('train',train),('dev',dev)):
        assert len(tokens[split])==len(rows)
        for encoded,row in zip(tokens[split],rows):
            assert encoded['id']==row['id']
            stats.append({'split':split,**check(encoded,row,tokenizer,protocol['max_length'])})
    original=tokens['train'][0];row=train[0];negatives=[]
    for fault in ('unmasked_history','target_token','EOS','prompt_token'):
        changed=copy.deepcopy(original)
        if fault=='unmasked_history':changed['labels'][0]=changed['input_ids'][0]
        elif fault=='target_token':changed['labels'][-2]=(changed['labels'][-2]+1)%len(tokenizer)
        elif fault=='EOS':changed['input_ids'].pop();changed['labels'].pop()
        else:changed['input_ids'][0]=(changed['input_ids'][0]+1)%len(tokenizer)
        try:check(changed,row,tokenizer,protocol['max_length'])
        except AssertionError:negatives.append(fault)
        else:raise AssertionError('Actual token/mask corruption accepted: '+fault)
    try:encode_record(tokenizer,row,1)
    except ValueError as e:negatives.append('actual_encoder_overlength:'+str(e))
    else:raise AssertionError('Actual encoder silently accepted overlength input')
    bad=copy.deepcopy(row);bad['messages'][-1]['role']='user'
    try:encode_record(tokenizer,bad,protocol['max_length'])
    except ValueError as e:negatives.append('actual_encoder_role:'+str(e))
    else:raise AssertionError('Actual encoder accepted non-assistant target')
    assert len(stats)==220 and len(negatives)==6
    assert all(sha(Path(f['path']))==f['sha256'] for f in assets['files'])
    proof={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'scope':'real pinned AutoTokenizer and existing production encoder/preflight, not model training or semantic quality',
        'verifier_sha256':sha(Path(__file__)),'training_module_sha256':sha(ROOT/'src/avatar/lab/training.py'),
        'tokenizer_environment':sys.prefix,'versions':{n:importlib.metadata.version(n) for n in protocol['packages']},
        'preflight_report_sha256':sha(output_folder/'preflight.json'),'tokens_sha256':sha(output_folder/'tokens.json'),
        'data_manifest_sha256':sha(source.with_name('manifest.json')),'config_sha256':sha(config),
        'train_samples':176,'dev_samples':44,'rejected':0,'max_length':protocol['max_length'],
        'max_observed_tokens':max(s['total_tokens'] for s in stats),'min_observed_tokens':min(s['total_tokens'] for s in stats),
        'supervised_tokens_train':sum(s['supervised_tokens'] for s in stats if s['split']=='train'),
        'all_prompt_and_history_tokens_masked':True,'actual_faults_rejected':negatives,
        'sample_stats':stats,'Torch_available':False,'LLM_model_constructions':0,'CUDA_allocation':False,'training_steps':0,
        'full_CUDA_environment_crosscheck_pending':True,'real_training_admission_pending':True}
    output.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print('C51 real tokenizer:176/44 accepted,0rejected;220 prompt/history masks;6 faults rejected;max',proof['max_observed_tokens'],';0 Torch/model/training')


if __name__=='__main__':main()

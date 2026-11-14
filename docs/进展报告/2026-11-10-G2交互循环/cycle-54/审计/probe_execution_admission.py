"""Normal CLI refusal controls and synthetic JSON verifier controls; no model/GPU."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

from execution_common import (ROOT,BASE,AUDIT,ASSETS,WORK,RUN,TOKEN_RUN,SEALS,
    read,sha,write_new,require,protocol_check,preparation_check,environment_reader)
from verify_execution import verify_labeled_training

OUT=ASSETS/'artifacts/c54/execution-admission-cpu-v1'
PROOF=AUDIT/'工作目录/007-冻结前执行门禁'


def main():
    require(not RUN.exists() and not (WORK/'freeze-v1.json').exists(),'CPU controls must precede real freeze/run')
    require(not OUT.exists() and not (PROOF/'admission-v1.json').exists(),'fresh CPU admission controls required')
    p=protocol_check();preparation_check()
    reader=environment_reader();runtime=read(reader.ADMISSION)['actual_CPU_probe']['runtime_files_sha256']
    require(len(runtime)==55 and all(sha(Path(n))==v for n,v in runtime.items()),'admitted runtime subset changed')
    OUT.mkdir(parents=True)
    env=os.environ.copy();env.update(PYTHONPATH=str(ROOT/'src'),CUDA_VISIBLE_DEVICES='',PYTHONDONTWRITEBYTECODE='1')
    freeze=str(WORK/'freeze-v1.json');zeros='0'*64
    cases=[('missing_freeze',['run_execution.py','--freeze',freeze,'--expected-freeze-sha256',zeros,'--stage','base'],1,'C54 frozen execution descriptor missing'),
        ('wrong_freeze_path',['run_execution.py','--freeze',str(OUT/'fake.json'),'--expected-freeze-sha256',zeros,'--stage','base'],1,'C54 registered freeze path required'),
        ('unknown_stage',['run_execution.py','--freeze',freeze,'--expected-freeze-sha256',zeros,'--stage','unknown'],2,"invalid choice: 'unknown'"),
        ('wrong_prior_seal',['freeze_execution.py','--c53-seal-sha256',zeros],1,'C54 explicit sealed C53 identity required')]
    CLI=[]
    for name,args,code,reason in cases:
        command=[sys.executable,'-B',str(AUDIT/args[0]),*args[1:]]
        result=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True)
        require(result.returncode==code and reason in result.stderr
            and 'ModuleNotFoundError' not in result.stderr,'actual normal CLI refusal differs: '+name)
        record={'name':name,'argv':command,'actual_returncode':result.returncode,'expected_reason':reason,
            'stdout':result.stdout,'stderr':result.stderr,'normal_CLI_not_runpy_wrapper':True}
        write_new(PROOF/(name+'-v1.json'),record);CLI.append(name)
    help_result=subprocess.run([sys.executable,'-B',str(AUDIT/'run_execution.py'),'--help'],cwd=ROOT,env=env,capture_output=True,text=True)
    require(help_result.returncode==0 and 'old_adapter' in help_result.stdout and 'new_adapter' in help_result.stdout,'normal CLI help import/control failed')
    write_new(PROOF/'normal-help-v1.json',{'returncode':0,'stdout':help_result.stdout,'stderr':help_result.stderr})
    # These are labeled synthetic JSON records, not GPU observations. The pure
    # verifier function is exercised directly and no production ledger is written.
    fixture=OUT/'synthetic-labeled-verifier';raw=fixture/'actual-labeled-forwards';raw.mkdir(parents=True)
    tokens=read(TOKEN_RUN/'tokens.json');losses=[]
    for ordinal,(split,row) in enumerate([(s,r) for s in ('train','dev') for r in tokens[s]],1):
        from labeled_forward_capture import fingerprint
        key=fingerprint(row['input_ids'],row['labels']);loss=1.0+ordinal/1000
        entry={'ordinal':ordinal,'completed':False,'fixture_cpu':False,'synthetic_JSON_validator_fixture':True,
            'model_training':split=='train','grad_enabled':split=='train','input_ids':[row['input_ids']],'labels':[row['labels']],
            'input_dtype':'torch.int64','labels_dtype':'torch.int64','input_device':'cuda:0','labels_device':'cuda:0',
            'embedding_device':'cuda:0','embedding_dtype':'torch.bfloat16','attention_mask_present':False}
        result={**entry,'completed':True,'id':row['id'],'split':split,'supervised_tokens':sum(v!=-100 for v in row['labels']),
            'input_labels_sha256':key,'loss':loss}
        write_new(raw/f'{ordinal:04}-entry.json',entry);write_new(raw/f'{ordinal:04}-result.json',result)
        losses.append(result)
    steps=[]
    for index in range(44):
        group=losses[index*4:(index+1)*4]
        steps.append({'step':index+1,'samples':4,'sample_ids':[r['id'] for r in group],
            'supervised_tokens':sum(r['supervised_tokens'] for r in group),'loss':sum(r['loss']/4 for r in group),'gradient_norm':1.0})
    summary={'completed':True,'actual_labeled_forwards':220,'observer_sha256':sha(AUDIT/'labeled_forward_capture.py')}
    write_new(fixture/'labeled-forward-summary.json',summary)
    manifest={'dev_loss':sum(r['loss'] for r in losses[176:])/44}
    positive=verify_labeled_training(fixture,steps,manifest)
    require(positive['optimizer_ids_equal_actual_tensor_order'],'positive synthetic validator mapping failed')
    rejected=[]
    for fault in ('step_ids','step_supervision','step_loss','dev_loss','fixture_flag','tensor_token','entry_transition'):
        bad_steps=copy.deepcopy(steps);bad_manifest=copy.deepcopy(manifest)
        if fault=='step_ids':bad_steps[0]['sample_ids'].reverse()
        elif fault=='step_supervision':bad_steps[0]['supervised_tokens']+=1
        elif fault=='step_loss':bad_steps[0]['loss']+=0.1
        elif fault=='dev_loss':bad_manifest['dev_loss']+=0.1
        changed=[]
        if fault in ('fixture_flag','tensor_token','entry_transition'):
            file=raw/('0001-entry.json' if fault=='entry_transition' else '0001-result.json');saved=file.read_bytes();row=json.loads(saved)
            if fault=='fixture_flag':row['fixture_cpu']=True
            elif fault=='tensor_token':row['input_ids'][0][0]+=1
            else:row['completed']=True
            file.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');changed.append((file,saved))
        try:verify_labeled_training(fixture,bad_steps,bad_manifest)
        except ValueError as error:rejected.append({'fault':fault,'rejected':True,'reason':str(error)})
        else:raise ValueError('synthetic verifier fault accepted: '+fault)
        finally:
            for file,saved in changed:file.write_bytes(saved)
    require(verify_labeled_training(fixture,steps,manifest)==positive,'synthetic fixture restoration failed')
    require('torch' not in sys.modules and not RUN.exists(),'CPU gate constructed Torch/run state')
    write_new(PROOF/'admission-v1.json',{'passed':True,
        'scope':'actual normal CLI refusals and synthetic JSON verifier logic; no actual CUDA/LLM training evidence',
        'probe_sha256':sha(Path(__file__)),'common_sha256':sha(AUDIT/'execution_common.py'),
        'run_sha256':sha(AUDIT/'run_execution.py'),'verifier_sha256':sha(AUDIT/'verify_execution.py'),
        'normal_CLI_refusals':CLI,'normal_help_passed':True,'actual_normal_CLI_processes':5,
        'synthetic_labeled_records':220,'synthetic_optimizer_groups':44,'synthetic_verifier_faults_rejected':rejected,
        'admitted_runtime_subset_rehashed':55,'external_fixture_output':str(OUT),
        'real_run_root_absent':True,'Torch_imported_in_probe':False,'actual_GPU_or_model_verified':False,
        'actual_LLM_generations':0,'actual_training_steps':0,'GPU_allocations':0})
    print('C54 admission:4exact normalCLI refusals+help;220syntheticrecords/44steps/7faults;55runtimefiles;0Torch/LLM/GPU')


if __name__=='__main__':main()

"""Rebuild all source SQL and reject real loader/provenance fault controls, CPU only."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/004-纠错材料'
PRIOR=BASE.parent/'cycle-50/审计'
sys.path.insert(0,str(PRIOR))
from verify_observations import inspect_observations
from avatar.lab.common import sha,canonical
from avatar.lab.training import load_data
from avatar.lab.data import evaluation_texts


def read(path):return json.loads(path.read_text())


def main():
    output=WORK/'data-independent-v1.json';assert not output.exists()
    summary=read(WORK/'data-preparation-v1.json');assert summary['completed']
    folder=Path(summary['output']);assert folder==Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/c51/correction-data-v1')
    assert sha(folder/'manifest.json')==summary['manifest_sha256']==sha(WORK/'external-data-manifest-v1.json')
    assert summary['generator_sha256']==sha(BASE/'审计/build_correction_data.py')
    train,dev,manifest=load_data(folder/'sft.jsonl')
    assert len(train)==176 and len(dev)==44 and manifest['human_reviewed'] is False
    assert manifest['protected_eval_hashes']==evaluation_texts()[1]
    assert 'evals/interaction/cycle-52/correction-transfer-cases.json' in manifest['protected_eval_hashes']
    assert summary['protocol_sha256']==sha(ROOT/'evals/interaction/cycle-52/correction-transfer-protocol.json')
    sql=0;seen=set();families={};first=None
    for name in summary['groups']:
        group=read(WORK/name);assert group['samples']==20 and group['train']==16 and group['dev']==4
        assert all(sha(folder/n)==value for n,value in group['raw_sha256'].items())
        families[group['family']]={'train':0,'dev':0}
    for split,rows in (('train',train),('dev',dev)):
        for row in rows:
            assert row['id'] not in seen;seen.add(row['id'])
            case_folder=folder/'raw'/row['id'];case=read(case_folder/'case.json');receipt=read(case_folder/'receipt.json')
            backend=read(case_folder/'scripted-backend-calls.json')
            assert [c['kind'] for c in backend]==['analysis','reply'] and not any(c['adapter_enabled'] for c in backend)
            assert row['messages']==backend[-1]['messages']+[{'role':'assistant','content':receipt['ordinary_result']['reply']}]
            import hashlib
            assert row['provenance']['content_sha256']==hashlib.sha256(canonical(row['messages']).encode()).hexdigest()
            assert row['provenance']['split']==split and row['provenance']['human_reviewed'] is False
            families[row['provenance']['family']][split]+=1
            assert receipt['query_model_calls']==0 and receipt['business_unchanged_by_query_and_ordinary'] and receipt['no_new_user_facts']
            assert receipt['model_modes_valid'] and receipt['ordinary_result']['reply']==backend[-1]['reply']
            sql+=inspect_observations(case_folder,receipt,case,'production_snapshot')
            if first is None:first=(case_folder,receipt,case)
    assert len(seen)==220 and sql==440
    assert len(families)==11 and all(v=={'train':16,'dev':4} for v in families.values())
    fault_root=Path('/data/Users/zrh/data/hhu-ai-avatar/tmp/c51-data-faults-v1');assert not fault_root.exists();fault_root.mkdir()
    loader_faults=[]
    for kind in ('sft_bytes','protected_hash','screen_code','split_id','split_content','human_flag'):
        destination=fault_root/kind;destination.mkdir()
        for name in ('sft.jsonl','dev.jsonl','manifest.json'):shutil.copyfile(folder/name,destination/name)
        meta=read(destination/'manifest.json')
        if kind=='sft_bytes':
            with (destination/'sft.jsonl').open('a') as stream:stream.write('\n')
        elif kind=='protected_hash':meta['protected_eval_hashes'].pop('evals/interaction/cycle-52/correction-transfer-cases.json')
        elif kind=='screen_code':meta['screening_code_sha256']='0'*64
        elif kind=='human_flag':meta['human_reviewed']=True
        else:
            altered=copy.deepcopy(dev)
            if kind=='split_id':altered[0]['id']=train[0]['id']
            else:altered[0]['provenance']['content_sha256']=train[0]['provenance']['content_sha256']
            (destination/'dev.jsonl').write_text(''.join(canonical(r)+'\n' for r in altered));meta['dev_sha256']=sha(destination/'dev.jsonl')
        (destination/'manifest.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
        try:load_data(destination/'sft.jsonl')
        except ValueError as e:loader_faults.append({'kind':kind,'error':str(e),'input':str(destination)})
        else:raise AssertionError('actual training loader accepted fault: '+kind)
    source_faults=[];case_folder,original,case=first
    for kind in ('source_id','state','history_context'):
        changed=copy.deepcopy(original)
        if kind=='source_id':changed['query_observations'][0]['result']['reminder_query']['source_message_id']+=100
        elif kind=='state':changed['query_observations'][0]['result']['reminder_query']['state']['status']='completed'
        else:changed['actual_model_interface_calls'][-1]['messages']=[m for m in changed['actual_model_interface_calls'][-1]['messages'] if m['role']!='assistant']
        try:inspect_observations(case_folder,changed,case,'production_snapshot')
        except AssertionError:source_faults.append(kind)
        else:raise AssertionError('actual source checker accepted fault: '+kind)
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':sha(Path(__file__)),'summary_sha256':sha(WORK/'data-preparation-v1.json'),
        'train_samples':176,'dev_samples':44,'families':families,'actual_CPU_examples':220,
        'SQL_dumps_reconstructed':sql,'raw_source_and_model_messages_matched':True,
        'actual_loader_faults_rejected':loader_faults,'actual_source_faults_rejected':source_faults,
        'native_calls':0,'training_steps':0,'semantic_quality_approved':False,'human_reviewed':False,
        'scope':'mechanical/source/SQL/export verification of scripted-target synthetic corpus, not naturalness or general semantic approval',
        'tokenizer_preflight_pending':True,'real_training_admission_pending':True}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C51 independent data:176/44;440 actual SQL;6 loader+3 source faults rejected;no tokenizer/training/semantic approval')


if __name__=='__main__':main()

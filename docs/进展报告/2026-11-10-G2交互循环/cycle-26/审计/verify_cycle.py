"""C26 post-hoc complete-source, three-model evidence and review integrity audit."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from verify_native_model import verify as verify_native, FREEZE, EXPECTED

BASE=Path(__file__).resolve().parents[1];ROOT=BASE.parents[3]
WORK=BASE/'审计/工作目录/003-模型原生语义评估'


def read(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()
def git_digest(ref,path):return sha256(subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)).hexdigest()


def verify():
    historical=[]
    for n,count in ((21,432),(22,81),(23,80),(24,148),(25,61)):
        folder=BASE.parent/f'cycle-{n}';manifest=folder/'审计/证据清单.json';entries=read(manifest)
        assert len(entries)==count and all(digest(folder/name)==value for name,value in entries.items())
        historical.append({'cycle':n,'entries':count,'manifest_sha256':digest(manifest),'mismatches':0})
    frozen=read(FREEZE);assert digest(FREEZE)==EXPECTED and len(frozen['sha256'])==229
    for name,value in frozen['sha256'].items():
        assert digest(ROOT/name)==value and git_digest(frozen['source_ref'],name)==value
    full_path=BASE/'审计/工作目录/002-当前默认采样冻结/full-final-python-binding.json';full=read(full_path)
    assert digest(full_path)==frozen['full_python_binding_sha256'] and full['head']==frozen['full_python_head']
    assert full['completed'] and full['exit_code']==0 and full['source_unchanged'] and len(full['source_sha256'])==221
    for name,value in full['source_sha256'].items():assert digest(ROOT/name)==git_digest(full['head'],name)==value
    assert '1650 passed, 1 skipped in 114.28s' in (full_path.parent/'full-final-python.log').read_text()
    models=[];external={'unsupported_completed_external_action','unsupported_external_commitment','unsupported_external_offer'}
    for label in ('4b','14b','32b'):
        folder=BASE/f'实验/current-default-{label}';alignment=verify_native(folder)
        assert alignment==read(WORK/f'{label}-native-alignment.json')
        sample=folder/f'qwen3-{label}-q4_k_m/sample/native-output.json';data=read(sample)
        review_path=WORK/f'{label}-semantic-review.json';review=read(review_path)
        assert review['sample_sha256']==digest(sample) and review['model_id']==alignment['model_id']
        assert review['rubric_sha256']==digest(WORK/'评估口径.md') and review['known_development_cases']
        assert len(review['rows'])==20 and len({(r['case'],r['turn']) for r in review['rows']})==20
        for record,(case,n,turn) in zip(review['rows'],[(case,n,t) for case in data['cases'] for n,t in enumerate(case['turns'],1)]):
            assert (record['case'],record['turn'])==(case['id'],n)
            assert record['input']==turn['input'] and record['reply']==turn['result']['reply']
            assert record['generation_mode']==turn['result']['generation_mode'] and record['analysis_mode']==turn['result']['analysis_mode']
            assert record['sqlite_reminder_count']==len(turn['reminders'])
            for finding in record['findings']:assert record['reply'][finding['start']:finding['end']]==finding['span'] and finding['reason']
            assert record['unsupported_external_action_reply']==any(f['category'] in external for f in record['findings'])
        native=[r for r in review['rows'] if r['generation_mode']=='llm'];bad=sum(r['unsupported_external_action_reply'] for r in native)
        assert len(native)==review['native_reply_denominator']==alignment['native_reply_calls']
        assert bad==review['unsupported_external_action_reply_count']
        assert review['semantic_approved'] is False  # Same-agent annotation is not release approval.
        models.append({k:alignment[k] for k in ['model_id','app_turns','native_calls','cognitive_calls','native_reply_calls','warmups','elapsed_seconds','gpu','gpu_allocation_mib','bound_inputs','provider_exit','cleanup_passed']}|{'unsupported_external_action_reply_count':bad,'semantic_review_sha256':digest(review_path),'semantic_approved':False})
    download=read(BASE/'实验/32b-download-terminal.json');assert download['completed'] and download['failure'] is None and download['curl_exit']==0
    assert download['actual_size']==19762149024 and download['actual_sha256']=='efd971561896866f0e910cce52761ca77b1b138090c7f15fe284676d57d1f689'
    assert read(BASE/'实验/current-default-32b/qwen3-32b-q4_k_m/provider-ready.json')['model_sha256']==download['actual_sha256']
    front=read(BASE.parent/'cycle-24/审计/工作目录/002-持久提醒确认/browser-recovery/normal_claim/recovery-browser.json')['sourceSha256'];count=0
    for name,value in front.items():
        if name.startswith(('src/','dist/')):assert digest(ROOT/'frontend'/name)==value;count+=1
    result={'verified':True,'prior_manifests':historical,'execution_freeze_sha256':EXPECTED,'frozen_inputs':229,'source_ref':frozen['source_ref'],
        'full_python':{'head':full['head'],'passed':1650,'skipped':1,'seconds':114.28,'bound_python_and_entry_inputs':221},
        'models':models,'total_application_turns':sum(m['app_turns'] for m in models),'total_native_calls':sum(m['native_calls'] for m in models),
        'frontend_files_unchanged':count,'frontend_reexecuted_this_cycle':False,'retained_C24_frontend_unit_passed':153,
        'reviewer':'same Codex agent, not independent human review','application_wire_body_recomputed':False,
        'general_semantic_P1_closed':False,'prospective_run':False,'production_default_changed':False,'physical_or_human_approved':False}
    target=BASE/'审计/收尾核验/阶段来源与系统收尾核验.json';target.parent.mkdir(exist_ok=True);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if target.exists():assert target.read_text()==text
    else:target.write_text(text)
    print('Verified C21-C25 seals, 229 frozen inputs, full1650 and three native model/application/SQLite reviews.')


if __name__=='__main__':verify()

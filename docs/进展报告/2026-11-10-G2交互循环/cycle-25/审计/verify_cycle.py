"""C25 historical model stages, repaired native trace and regression evidence."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

BASE=Path(__file__).resolve().parents[1];ROOT=BASE.parents[3]
W2=BASE/'审计/工作目录/002-提供方trace身份修复'

def read(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()
@lru_cache(None)
def git_digest(ref,path):return sha256(subprocess.check_output(['git','show',ref+':'+path],cwd=ROOT)).hexdigest()

def verify():
    prior=[]
    for n,count in ((21,432),(22,81),(23,80),(24,148)):
        folder=BASE.parent/('cycle-'+str(n));path=folder/'审计/证据清单.json';manifest=read(path)
        assert len(manifest)==count and all(digest(folder/name)==h for name,h in manifest.items())
        prior.append({'cycle':n,'entries':count,'manifest_sha256':digest(path),'mismatches':0})
    sys.path.insert(0,str(ROOT/'scripts'))
    from probe_structured_provider import validate_trace,schema_valid
    old=ROOT/'evals/interaction/cycle-25/provider-probe-freeze.json'
    fixed=ROOT/'evals/interaction/cycle-25/provider-trace-fixed-freeze.json'
    assert digest(old)=='8ac909ff2f85f3262c8b98b164bc00c70d8be61211681b4daf3968f0fbd1f386'
    assert digest(fixed)=='c047f2482cbe3a728ae3203c4e35e61de7b3946f43e5ea717656532b6b5fd478'
    for path,count in ((old,8),(fixed,9)):
        frozen=read(path);assert len(frozen['sha256'])==count
        assert all(git_digest(frozen['source_ref'],name)==h for name,h in frozen['sha256'].items())
    for name,path in [('provider-probe-retirement.json',old),('provider-trace-fixed-retirement.json',fixed)]:
        retirement=read(ROOT/'evals/interaction/cycle-25'/name)
        assert retirement['status']=='completed_diagnostic_historical_only' and retirement['freeze_sha256']==digest(path)
    protocol=read(ROOT/'evals/interaction/cycle-25/structured-provider-protocol.json')
    cases={case['id']:case for case in protocol['cases']};models=[];outputs={}
    raw_gpu=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)
    for label,descriptor,strict in [('4b',old,False),('14b',old,False),('4b-trace-fixed',fixed,True)]:
        folder=BASE/'实验'/('structured-provider-'+label);data=read(folder/'probe.json')
        calls=[json.loads(line) for line in (folder/'provider-trace.jsonl').read_text().splitlines()]
        assert data['completed'] and data['failure'] is None and data['engineering_passed']
        assert data['cleanup_passed'] and data['provider_exit']==0 and not data.get('forced_cleanup')
        assert data['freeze_sha256']==digest(descriptor) and data['frozen_inputs']==read(descriptor)
        assert len(data['requests'])==len(calls)==10
        assert not any(line.split(',')[0].strip()==str(data['provider_pid']) for line in raw_gpu.splitlines())
        validate_trace(data['requests'],calls,require_request_identity=strict)
        frozen=data['frozen_inputs'];metadata=data['provider_ready']
        assert metadata['backend']=='cuda' and metadata['configuration']['n_gpu_layers']==-1
        assert metadata['configuration']['temperature']==0 and metadata['configuration']['thinking'] is False
        assert metadata['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
        assert metadata['registry_sha256']==frozen['sha256']['evals/interaction/cycle-02/model-scale-protocol.json']
        assert metadata['pid']==data['provider_pid'] and metadata['process_gpu_mib_after_load']
        assert metadata['chosen_gpu']['free_mib']>=16384 and metadata['chosen_gpu']['utilization_percent']<=20
        diagnostic=[];teacher=[]
        for row in data['requests']:
            assert row['finish_reason']=='stop' and row['native_trace_matched']
            if row['role']=='warmup':continue
            case=cases[row['case']]
            assert row['role']==case['role'] and row['request']['messages']==case['messages']
            assert row['request_sha256']==sha256(json.dumps(row['request'],ensure_ascii=False).encode()).hexdigest()
            fmt=row['request'].get('response_format')
            assert bool(fmt)==(row['arm']=='schema')
            if fmt:assert fmt=={'type':'json_schema','json_schema':{'name':case['id'],'strict':True,'schema':case['schema']}}
            assert row['declared_schema_valid']==schema_valid(row['reply'],case['schema'])
            if row['case']=='teacher_draft':
                body=json.loads(row['reply'])['draft'] if fmt else row['reply']
                teacher.append({'arm':row['arm'],'literal_backslash_n_count':body.count('\\n'),'provider_call_id':row['provider_call_id']})
            diagnostic.append(row)
        assert len(diagnostic)==8 and sum(r['declared_schema_valid'] for r in diagnostic if r['arm']=='schema')==4
        assert sum(r['role']=='warmup' for r in data['requests'])==2
        outputs[label]={(r['case'],r['arm']):r['reply'] for r in diagnostic}
        models.append({'label':label,'head':data['head'],'source_ref':frozen['source_ref'],'frozen_inputs':len(frozen['sha256']),
            'requests':10,'warmups':2,'diagnostic_arms':8,'schema_passed':4,'seconds':data['seconds'],
            'gpu':metadata['chosen_gpu'],'strict_wire_schema_binding':strict,'provider_exit':0,'cleanup_passed':True,'teacher_escape_observations':teacher})
    assert outputs['4b']==outputs['4b-trace-fixed']
    full=read(W2/'full-python-binding.json')
    assert full['completed'] and full['exit_code']==0 and full['source_unchanged'] and len(full['source_sha256'])==213
    for name,h in full['source_sha256'].items():assert git_digest(full['head'],name)==h and digest(ROOT/name)==h
    assert '1569 passed, 1 skipped in 110.45s' in (W2/'full-python.log').read_text()
    frontend=read(BASE.parent/'cycle-24/审计/工作目录/002-持久提醒确认/browser-recovery/normal_claim/recovery-browser.json')['sourceSha256']
    front_count=0
    for name,h in frontend.items():
        if name.startswith('src/') or name.startswith('dist/'):
            assert digest(ROOT/'frontend'/name)==h;front_count+=1
    assert '153 passed (153)' in (BASE.parent/'cycle-24/审计/工作目录/002-持久提醒确认/frontend-full.log').read_text()
    out=BASE/'审计/收尾核验';out.mkdir(exist_ok=True)
    result={'verified':True,'prior_manifests':prior,'models':models,'original_diagnostic_requests':20,'original_warmups':4,'original_diagnostic_arms':16,
            'post_fix_requests':10,'post_fix_strict_wire_schema_bindings':10,'post_fix_observed_replies_equal_original_4b':8,
            'candidate_implemented':False,'envelope_only_semantic_release_approved':False,'general_semantic_P1_closed':False,
            'full_python':{'passed':1569,'skipped':1,'seconds':110.45,'head':full['head'],'bound_python_and_entry_inputs':213},
            'frontend_and_product_source_unchanged':True,'frontend_files_checked':front_count,'retained_C24_frontend_unit_passed':153,
            'frontend_reexecuted_this_cycle':False,'physical_or_human_approved':False,'new_32b_downloaded_or_run':False}
    path=out/'阶段来源与系统收尾核验.json';text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if path.exists():assert path.read_text()==text
    else:path.write_text(text)
    print('Verified original20 requests,post-fix10 strict native bindings,full1569 and unchanged C21-C24 evidence.')

if __name__=='__main__':verify()

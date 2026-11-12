"""Post-hoc provenance audit; raw atoms are fixtures, never real SQL evidence."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
BASE=Path(__file__).resolve().parents[1];ROOT=BASE.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
from probe_native_evidence_plans_v2 import verify_freeze,validate_rows,validate_protocol,grade_plan,PROTOCOL,REGISTRY,MODELS
from probe_structured_provider import validate_trace
from evaluate_native_output_audit import validate_provider_identity


def read(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()
def git_digest(ref,name):return sha256(subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)).hexdigest()


def verify():
    seals=[]
    for n,count in ((21,432),(22,81),(23,80),(24,148),(25,61),(26,78),(27,54)):
        folder=BASE.parent/f'cycle-{n}';manifest=folder/'审计/证据清单.json';entries=read(manifest)
        assert len(entries)==count and all(digest(folder/name)==value for name,value in entries.items())
        seals.append({'cycle':n,'entries':count,'manifest_sha256':digest(manifest),'mismatches':0})
    descriptor=ROOT/'evals/interaction/cycle-28/source-atom-three-arm-freeze.json';identity=digest(descriptor);frozen=verify_freeze(descriptor,identity,MODELS[0]);protocol=read(ROOT/PROTOCOL);validate_protocol(protocol)
    for name,value in frozen['sha256'].items():assert git_digest(frozen['source_ref'],name)==value
    full_path=BASE/'审计/工作目录/001-三臂比较口径/full-final-python-binding.json';full=read(full_path)
    assert digest(full_path)==frozen['full_python_binding_sha256'] and full['head']==frozen['full_python_head']
    assert full['completed'] and full['exit_code']==0 and full['source_unchanged']
    for name,value in full['source_sha256'].items():assert git_digest(full['head'],name)==digest(ROOT/name)==value
    gpu_raw=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)
    summaries=[]
    for label,model in zip(('4b','32b'),MODELS):
        folder=BASE/f'实验/three-arm-{label}';report=read(folder/'probe.json');calls=[json.loads(line) for line in (folder/'provider-trace.jsonl').read_text().splitlines()]
        assert report['completed'] and report['engineering_passed'] and report['failure'] is None
        assert report['freeze_sha256']==identity and report['frozen_inputs']==frozen
        assert git_digest(report['head'],str(descriptor.relative_to(ROOT)))==identity
        assert report['provider_exit']==0 and report['cleanup_passed'] and not report.get('forced_cleanup')
        assert not any(line.split(',')[0].strip()==str(report['provider_pid']) for line in gpu_raw.splitlines())
        assert report['model_id']==model and report['native_trace_sha256']==digest(folder/'provider-trace.jsonl')
        validate_rows(report['requests'],protocol,model);validate_trace(report['requests'],calls,require_request_identity=True)
        provider=read(folder/'provider-ready.json');assert report['provider_ready']==provider and provider['pid']==report['provider_pid']
        validate_provider_identity(provider,{'models_registry':REGISTRY,'models_registry_sha256':frozen['sha256'][REGISTRY],'provider_backend':'cuda'})
        assert provider['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py'] and provider['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
        metrics={}
        for arm in ('plan_free','plan_schema'):
            subset=[row for row in report['requests'] if row.get('arm')==arm];assert len(subset)==12
            metrics[arm]={'count':len(subset),'schema_valid':sum(row['declared_schema_valid'] for row in subset),
                          'plan_exact':sum(row['plan_exact'] for row in subset),'render_passed':sum(row['render_passed'] for row in subset),
                          'rendered_task_exact':sum(row['rendered_task_exact'] for row in subset)}
        assert report['arm_metrics']==metrics and report['schema_arms_passed']==metrics['plan_schema']['schema_valid']==12
        assert report['semantic_approved'] is False and report['atoms_are_experiment_fixtures'] is True
        assert report['avatar_integration_run'] is False and report['real_sql_commit_verified'] is False
        natural=[row for row in report['requests'] if row.get('arm')=='natural'];assert len(natural)==12
        format_violations=[]
        for row in natural:
            marker=row['reply'].lstrip().startswith(('capability_boundary','copy_draft','answer_actor','report_receipt','insufficient_evidence'))
            try:marker=marker or isinstance(json.loads(row['reply']), (dict,list))
            except (ValueError,TypeError):pass
            if marker:format_violations.append({'case':row['case'],'native_call':row['provider_call_id'],'reply':row['reply']})
        summaries.append({'model_id':model,'head':report['head'],'requests':38,'warmups':2,'diagnostic_arms':36,
            'arm_metrics':metrics,'natural_format_violations':format_violations,
            'seconds_including_load':report['seconds'],'gpu':provider['chosen_gpu'],'gpu_allocation_mib':provider['process_gpu_mib_after_load'],
            'provider_exit':0,'cleanup_passed':True,'probe_sha256':digest(folder/'probe.json'),'native_trace_sha256':digest(folder/'provider-trace.jsonl')})
    result={'verified':True,'prior_manifests':seals,'models':summaries,'freeze_sha256':identity,'frozen_inputs':len(frozen['sha256']),
        'full_python':frozen['full_python_result'],'full_python_head':full['head'],'bound_full_regression_inputs':len(full['source_sha256']),
        'strict_wire_schema_trace_bindings':76,'atoms_are_fixtures':True,'actual_avatar_or_sql_integration_run':False,'production_activated':False,'prospective_run':False,'semantic_release_approved':False}
    output=BASE/'审计/收尾核验/三臂原生来源与计划核验.json';output.parent.mkdir(exist_ok=True);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if output.exists():assert output.read_text()==text
    else:output.write_text(text)
    print('Verified76 native wire/schema bindings, frozen sources, typed scores, cleanup and C21-C27 seals; not product integration.')


if __name__=='__main__':verify()

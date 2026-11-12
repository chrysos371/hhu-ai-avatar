"""Independent persisted evidence reconstruction, without controller validators."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
from state_common import ROOT,BASE,PROTOCOL,FIXTURES,RUNTIME,digest,verify_freeze,verify_historical_binding,validate_fixture_provenance


def verify(path):
    report=json.loads(path.read_text());model=report['model_id'];work=BASE/'审计/工作目录/001-原生状态隔离'
    frozen=verify_freeze(work/'执行冻结.json',report['freeze_sha256'],model);verify_historical_binding(frozen)
    protocol=json.loads((ROOT/PROTOCOL).read_text());fixture=validate_fixture_provenance(model);backend=json.loads((ROOT/RUNTIME).read_text())
    assert report['completed'] and report['engineering_passed'] and report['cleanup_passed'] and not report['failure'] and not report['cleanup_errors']
    assert report['actual_native_cuda'] and report['avatar_or_sql_run'] is False and report['semantic_approval'] is False
    assert [p['state_policy'] for p in report['policies']]==protocol['policy_orders'][model]
    devices=set();targets=[];summary=[];calls=0
    for policy in report['policies']:
        name=policy['state_policy'];folder=path.parent/name;ready=json.loads((folder/'provider-ready.json').read_text());close=json.loads((folder/'provider-closeout.json').read_text())
        assert ready==policy['provider_ready'] and close==policy['provider_closeout']
        assert policy['completed'] and policy['cleanup_passed'] and policy['provider_exit']==0 and not policy.get('forced_cleanup')
        assert ready['pid']==close['pid']==policy['provider_pid'] and ready['state_policy']==close['state_policy']==name
        assert ready['backend_runtime_identity_sha256']==close['backend_runtime_identity_sha256']==frozen['sha256'][RUNTIME]
        assert ready['backend_runtime_files_verified']==close['runtime_files_verified_after']==len(backend['files_sha256'])==54
        assert close['model_closed'] and close['server_closed'] and ready['model_context_memory_present']
        assert ready['provider_source_sha256']==frozen['sha256'][str((BASE/'审计/serve_state_eval.py').relative_to(ROOT))]
        assert ready['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
        assert len(ready['state_method_sources'])==2
        for method in ready['state_method_sources'].values():assert backend['files_sha256'][method['path']]==method['file_sha256']
        for key,value in {'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1,'repeat_penalty':1.0,'top_p':1.0,'top_k':0,'state_policy':name}.items():assert ready['configuration'][key]==value
        gpu=ready['chosen_gpu'];devices.add(gpu['uuid']);assert gpu['free_mib']>= (16384 if '4b-' in model else 32768) and gpu['utilization_percent']<=20
        assert policy['controller_choice']['uuid']==gpu['uuid'] and policy['historical_gpu_uuid_equal']==(gpu['uuid']==fixture['source_gpu']['uuid'])
        trace=folder/'provider-trace.jsonl';assert Path(policy['trace_path']).resolve()==trace.resolve() and digest(trace)==policy['native_trace_sha256']
        native=[json.loads(line) for line in trace.read_text().splitlines()];rows=policy['requests'];assert len(native)==len(rows)==35
        assert [r['role'] for r in rows[:2]]==['warmup','warmup'] and all(r['role']=='replay' for r in rows[2:])
        expected=[]
        for rep,order in enumerate(protocol['chain_orders'],1):
            for chain in order:
                expected.extend((rep,chain,index) for index in fixture['chains'][chain])
        assert [(r['repetition'],r['chain'],r['source_ordinal']) for r in rows[2:]]==expected
        groups={c:[] for c in fixture['chains']};prompts=set();wire=set();previous=0
        for ordinal,(row,actual) in enumerate(zip(rows,native,strict=True)):
            calls+=1;raw=row['raw_request_json'];request=json.loads(raw)
            assert request==row['request'] and digest_bytes(raw)==row['request_sha256']==actual['request_body_sha256']
            assert row['provider_call_id']==actual['id'] and row['reply']==actual['reply'] and row['finish_reason']==actual['finish_reason']=='stop'
            assert row['status']==200 and row['outcome']=='completed' and row['http_roundtrip_seconds']>0
            body=row['raw_http_body'];assert digest_bytes(body)==row['response_body_sha256']
            if request['stream']:
                lines=[s[6:] for s in body.splitlines() if s.startswith('data: ')]
                assert lines[-1]=='[DONE]';chunks=[json.loads(s) for s in lines[:-1]]
                assert all(c['id']==actual['id'] for c in chunks)
                reply=''.join(c['choices'][0]['delta'].get('content','') or '' for c in chunks)
                assert [c['choices'][0]['finish_reason'] for c in chunks if c['choices'][0]['finish_reason'] is not None]==['stop']
            else:
                decoded=json.loads(body);assert decoded['id']==actual['id'] and decoded['choices'][0]['finish_reason']=='stop';reply=decoded['choices'][0]['message']['content']
            assert reply==row['reply'] and actual['messages']==request['messages']
            fmt=request.get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
            canonical=lambda value:sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value is not None else None
            assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt) and actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)
            state=actual['state_observation'];assert state['policy']==name and state['logical_tokens_before_policy']==previous
            assert state['logical_tokens_after_policy']==(previous if name=='reuse' else 0)
            assert state['explicit_logical_reset_called']==(name!='reuse') and state['explicit_context_memory_clear_called']==(name=='memory_clear_reset')
            assert state['general_physical_state_guarantee'] is False and state['library_internal_resets_not_counted'] is True
            previous=state['logical_tokens_after_generation'];assert type(previous) is int and previous>0
            if ordinal<2:
                assert row['warmup_index']==ordinal and request=={'model':model,'messages':[{'role':'user','content':'请回答：你好。'}],'stream':protocol['warmups'][ordinal],'temperature':0,'max_tokens':16}
            else:
                assert raw==fixture['requests'][row['source_ordinal']]['raw_request_json']
                if row['source_ordinal']==5:
                    groups[row['chain']].append(reply);prompts.add(actual['prompt_sha256']);wire.add(row['request_sha256']);targets.append((row['request_sha256'],actual['prompt_sha256']))
        assert len(prompts)==len(wire)==1
        equal=[a==b for a,b in zip(groups['without_extra_cognitive'],groups['with_extra_cognitive'],strict=True)]
        assert policy['observations']['target_replies']==groups and policy['observations']['within_repeat_equal']==equal
        summary.append({'state_policy':name,'replies':groups,'within_repeat_equal':equal,'unique_count':len(set(sum(groups.values(),[])))})
    assert calls==105 and len(devices)==1 and len(set(targets))==1 and next(iter(devices))==report['same_gpu_uuid_across_policies']
    return {'passed':True,'model_id':model,'evaluation_sha256':digest(path),'freeze_sha256':report['freeze_sha256'],'native_requests_verified':calls,'final_target_generations':len(targets),'same_gpu_uuid':next(iter(devices)),'policies':summary,'independent_of_controller_validation':True,'general_root_cause_or_semantic_approval':False}


def digest_bytes(value):return sha256(value.encode()).hexdigest()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('evaluation',type=Path);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=verify(args.evaluation)
    with args.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps(result,ensure_ascii=False))

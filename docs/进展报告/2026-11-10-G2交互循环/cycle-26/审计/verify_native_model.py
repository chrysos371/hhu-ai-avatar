"""Post-hoc C26 source/native/SSE/SQL alignment; never a semantic grader."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
import sys

CYCLE=Path(__file__).resolve().parents[1];ROOT=CYCLE.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import evaluate_native_output_audit as audit
from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT
FREEZE=ROOT/'evals/interaction/cycle-26/current-default-development-freeze.json'
PROTOCOL=ROOT/'evals/interaction/cycle-26/current-default-model-scale-protocol.json'
EXPECTED='d7e8cea989d308dc657fe1128229d3bc1d9a3428ebbace9ad79fd1d9adff2792'


def read(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()
def canonical(value):return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value is not None else None


def verify(folder):
    lifecycle=read(folder/'lifecycle.json');assert len(lifecycle['models'])==1
    row=lifecycle['models'][0];key=row['model_id'];base=folder/key
    data=read(base/'sample/native-output.json');trace=[json.loads(line) for line in (base/'provider-trace.jsonl').read_text().splitlines()]
    frozen=audit.verify_execution_freeze(FREEZE,EXPECTED,PROTOCOL,model_id=key)
    assert lifecycle['completed'] and lifecycle['failure'] is None and lifecycle['candidate']=='none'
    assert row['sampler_exit']==row['provider_exit']==0 and row['cleanup_passed']
    assert lifecycle['executionFreezeSha256']==data['executionFreezeSha256']==EXPECTED
    assert lifecycle['sourceSha256']==frozen['sha256']
    assert data['execution_complete'] and data['engineering_passed'] and data['failure'] is None
    for name,value in data['sourceSha256'].items():assert frozen['sha256'][name]==value
    for value in data['runtime_modules'].values():assert frozen['sha256'][str(Path(value['path']).relative_to(ROOT))]==value['sha256']
    provider=data['provider'];assert provider==row['provider_ready'] and provider['pid']==row['provider_pid']
    model,binding=audit.validate_provider_identity(provider,read(PROTOCOL));assert data['registry_binding']==binding
    assert provider['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
    assert provider['resource_selector_sha256']==frozen['sha256']['src/avatar/gpu_resources.py']
    assert provider['model_sha256']==model['sha256'] and provider['model_revision']==model['revision']
    assert [c['id'] for c in data['cases']]==frozen['case_ids'] and all(c['completed'] and c['error'] is None for c in data['cases'])
    turns=[t for c in data['cases'] for t in c['turns']]
    assert len(turns)==20 and len({t['input'] for t in turns})==20
    assert len(data['warmups'])==2
    for i,warm in enumerate(data['warmups']):
        assert trace[i]['response']==warm['reply'] and trace[i]['stream']==warm['streaming']
        assert trace[i]['messages']==[{'role':'user','content':'请回答：你好。'}] and trace[i]['response_format'] is None
    for call in trace:
        fmt=call['response_format'];schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        assert call['outcome']=='completed' and call['finish_reason']=='stop'
        assert call['analysis']==call['grammar_enabled']==(fmt is not None)
        assert call['response_format_sha256']==canonical(fmt) and call['response_schema_sha256']==canonical(schema)
        assert re.fullmatch('[0-9a-f]{64}',call['request_body_sha256'])
    cursor=2;items=[]
    for case in data['cases']:
        for number,turn in enumerate(case['turns'],1):
            assert turn['terminal']=='result' and isinstance(turn['result']['reply'],str) and turn['result']['reply'].strip()
            related=[]
            while cursor<len(trace) and trace[cursor]['messages'][-1]['content']==turn['input']:
                related.append(trace[cursor]);cursor+=1
            native=[c for c in related if not c['grammar_enabled']];analysis=[c for c in related if c['grammar_enabled']]
            assert len(analysis)<=1 and all(c['response_format']==ANALYSIS_RESPONSE_FORMAT for c in analysis)
            if turn['result']['analysis_mode']=='llm':assert len(analysis)==1
            if turn['result']['generation_mode']=='llm':
                assert len(native)==1 and native[0]['response']==turn['visible']==turn['result']['reply']
            else:assert native==[]
            stored=turn['conversation']['items'][-1];current=turn['result']['conversation']
            assert stored['role']=='assistant' and stored['id']==current['assistant_message_id']
            assert stored['text']==stored['result']['reply']==turn['result']['reply']
            user=[x for x in turn['conversation']['items'] if x['id']==current['user_message_id']]
            assert len(user)==1 and user[0]['role']=='user' and user[0]['text']==turn['input']
            assert len(turn['reminders'])==turn['expected_reminder_count']
            items.append({'case':case['id'],'turn':number,'source_user_message_id':current['user_message_id'],
                'stored_assistant_id':stored['id'],'generation_mode':turn['result']['generation_mode'],
                'analysis_mode':turn['result']['analysis_mode'],'native_reply_ids':[c['id'] for c in native],
                'cognitive_analysis_ids':[c['id'] for c in analysis],'profile_rows':len(turn['profile']),
                'reminder_count':len(turn['reminders'])})
    assert cursor==len(trace)
    gpu_processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)
    assert not any(line.split(',')[0].strip()==str(row['provider_pid']) for line in gpu_processes.splitlines())
    return {'verified':True,'verifier_sha256':digest(Path(__file__)),'model_id':key,'lifecycle_sha256':digest(folder/'lifecycle.json'),
        'sample_sha256':digest(base/'sample/native-output.json'),'native_trace_sha256':digest(base/'provider-trace.jsonl'),
        'execution_freeze_sha256':EXPECTED,'bound_inputs':len(frozen['sha256']),'runtime_modules':len(data['runtime_modules']),
        'app_turns':len(turns),'native_calls':len(trace),'cognitive_calls':sum(c['grammar_enabled'] for c in trace),
        'native_reply_calls':sum(not c['grammar_enabled'] for c in trace)-2,'warmups':2,
        'generation_modes':data['generation_modes'],'analysis_modes':data['analysis_modes'],
        'schema_identifiers':dict(Counter(c['response_format']['json_schema']['name'] if c['response_format'] else 'plain' for c in trace)),
        'elapsed_seconds':data['elapsedSeconds'],'gpu':provider['chosen_gpu'],
        'gpu_allocation_mib':provider['process_gpu_mib_after_load'],'provider_exit':0,'cleanup_passed':True,
        'application_wire_body_recomputed':False,'wire_note':'Server wire SHA retained; application SDK full raw body not independently archived. Do not claim C25 standalone sender wire recomputation.',
        'semantic_approved':False,'bindings':items}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--run',required=True,type=Path);parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    value=verify(args.run);text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if args.output.exists():assert args.output.read_text()==text
    else:args.output.write_text(text)
    print(value['model_id'],'verified',value['app_turns'],'app turns',value['native_calls'],'native calls; semantic approval false')

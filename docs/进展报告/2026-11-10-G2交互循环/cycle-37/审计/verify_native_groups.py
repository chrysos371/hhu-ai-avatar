"""Reconstruct native/SDK/SSE/storage identities independently; gate is engineering only."""
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime
from native_common import ROOT,BASE,PROTOCOL,REGISTRY,RUNTIME,REFERENCE,WORK,digest,read,verify_source
from native_wire_relay import parse_wire
from evaluate_native_output_audit import validate_provider_identity
from run_native_output_models import has_pid
from avatar.brain.reminders import CHINA
FREEZE=WORK/'execution-freeze.json'
EXPECTED='06537603a69c9b84e45564dad685c8b20b35f0a21b3ceb535c7764100c00f134'

def text_hash(value):return hashlib.sha256(value.encode()).hexdigest()
def events(raw):
    kind,data='message',[];rows=[]
    for line in raw.splitlines()+['']:
        if not line:
            if data:rows.append((kind,json.loads('\n'.join(data))))
            kind,data='message',[]
        elif line.startswith('event:'):kind=line[6:].strip()
        elif line.startswith('data:'):data.append(line[5:].lstrip())
    return rows

def verify_group(folder):
    report=read(folder/'evaluation.json');frozen=verify_source(FREEZE,EXPECTED,report['model_id'])
    assert report['frozen_inputs']==frozen and report['freeze_sha256']==EXPECTED
    assert report['completed'] and report['engineering_passed'] and report['cleanup_passed'] and not report['failure']
    assert report['provider_exit']==report['sampler_exit']==0 and not report['forced_sampler_cleanup'] and report['relay_closed']
    assert not has_pid(report['processes_after'],report['provider_pid'])
    ready=read(folder/'provider-ready.json');assert ready['pid']==report['provider_pid']
    validate_provider_identity(ready,read(PROTOCOL))
    assert digest(folder/'provider-ready.json')==report['provider_ready_sha256']
    runtime=read(RUNTIME)
    for when in ('runtime_before','runtime_after'):
        assert report[when]['files_sha256']==runtime['files_sha256'] and len(runtime['files_sha256'])==54
        assert report[when]['reference_sha256']==frozen['sha256'][str(REFERENCE.relative_to(ROOT))]
    wire=[json.loads(line) for line in (folder/'wire.jsonl').read_text().splitlines()]
    trace=[json.loads(line) for line in (folder/'provider-trace.jsonl').read_text().splitlines()]
    assert len(wire)==len(trace)==report['native_calls']
    parsed=[]
    for index,(row,actual) in enumerate(zip(wire,trace,strict=True)):
        assert row['ordinal']==index+1 and json.loads(row['raw_request_json'])==row['request']
        assert text_hash(row['raw_request_json'])==row['request_body_sha256']==actual['request_body_sha256']
        assert text_hash(row['raw_http_body'])==row['response_body_sha256']
        value=parse_wire(row);parsed.append(value)
        assert value['reply']==actual['response'] and value['id']==actual['id'] and value['finish_reason']==actual['finish_reason']
        assert actual['outcome']=='completed' and actual['messages']==row['request']['messages']
        fmt=row['request'].get('response_format');schema=fmt.get('json_schema',{}).get('schema') if fmt else None
        canonical=lambda x:text_hash(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))) if x is not None else None
        assert actual['response_format']==fmt and actual['response_format_sha256']==canonical(fmt)
        assert actual['response_schema_sha256']==canonical(schema) and actual['grammar_enabled']==bool(fmt)
    sample=read(folder/'sample/native-output.json');assert sample['engineering_passed'] and sample['execution_complete']
    assert sample['executionFreezeSha256']==EXPECTED
    for name,sha in sample['sourceSha256'].items():assert frozen['sha256'][name]==sha
    for value in sample['runtime_modules'].values():
        path=Path(value['path']);assert path.is_relative_to(ROOT/'src')
        assert value['sha256']==frozen['sha256'][str(path.relative_to(ROOT))]
    assert [c['id'] for c in sample['cases']]==frozen['case_ids']
    assigned=[];app=0;generated=0;reminders=[]
    for case,protocol in zip(sample['cases'],read(PROTOCOL)['cases'],strict=True):
        assert case['completed'] and not case['error']
        assert [t['input'] for t in case['turns']]==protocol['turns']
        for index,turn in enumerate(case['turns']):
            assert turn['terminal']=='result';app+=1
            row=turn['result'];frames=events(turn['raw_sse'])
            assert [data for kind,data in frames if kind=='result']==[row]
            visible=''.join(data['text'] for kind,data in frames if kind=='text');assert visible==turn['visible']
            mid=row['conversation']['assistant_message_id'];stored=next(m for m in turn['conversation']['items'] if m['id']==mid)
            assert stored['text']==row['reply'] and not stored['redacted']
            matches=[i for i,r in enumerate(wire) if i>=2 and r['request']['messages'][-1]['content']==turn['input']]
            assigned.extend(matches);gens=[i for i in matches if wire[i]['kind']=='generation']
            if row['generation_mode']=='llm':
                generated+=1;assert len(gens)==1 and parsed[gens[0]]['reply']==visible==row['reply']
            else:assert not gens
            assert not row['tool_calls']
            expected=protocol.get('expected_reminders',[0]*len(case['turns']))[index]
            assert len(turn['reminders'])==expected
            if expected:
                reminder=turn['reminders'][0];assert reminder['title']=='核对设备清单'
                assert datetime.fromtimestamp(reminder['due_at'],CHINA).hour==9
            reminders.append({'case':case['id'],'turn':index+1,'count':expected})
    assert sorted(assigned)==list(range(2,len(wire))) and app==24
    assert digest(folder/'sample/native-output.json')==report['sample_sha256']
    assert digest(folder/'wire.jsonl')==report['wire_sha256'] and digest(folder/'provider-trace.jsonl')==report['native_trace_sha256']
    return {'path':str((folder/'evaluation.json').relative_to(ROOT)),'sha256':digest(folder/'evaluation.json'),
        'repetition':report['repetition'],'model_id':report['model_id'],'verified':True,'application_results':app,'model_generated_turns':generated,
        'native_calls':len(wire),'quality_finish_exceptions':report['quality_truncations'],'runtime_module_bindings':len(sample['runtime_modules']),
        'gpu':report['chosen_gpu'],'cleanup_verified':True,'reminder_controls':reminders}


def main():
    p=argparse.ArgumentParser();p.add_argument('--model',choices=('4b','32b'),required=True);args=p.parse_args()
    rows=[verify_group(BASE/'实验'/f'default-{args.model}-r{n}') for n in (1,2,3)]
    result={'freeze_sha256':EXPECTED,'model':args.model,'runs':rows,'verified':True,
        'actual_native_calls':sum(r['native_calls'] for r in rows),'application_results':sum(r['application_results'] for r in rows),
        'verifier_sha256':digest(Path(__file__)),'gate_scope':'engineering admission only, not semantic approval'}
    target=WORK/('4b-three-run-gate.json' if args.model=='4b' else '32b-three-run-engineering-proof.json')
    assert not target.exists();target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(args.model,'verified3runs/',result['application_results'],'app/',result['actual_native_calls'],'native;SHA',digest(target))
if __name__=='__main__':main()

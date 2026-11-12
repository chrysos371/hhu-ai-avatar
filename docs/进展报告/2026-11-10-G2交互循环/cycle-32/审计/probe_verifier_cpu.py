"""Reject controlled in-memory evidence corruption, preserving all native files."""
import argparse
import copy
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch
from verify_state_replay import verify


def main(args):
    evaluation=args.evaluation.resolve();baseline=verify(evaluation);original=Path.read_text
    report=json.loads(original(evaluation));controls=[]
    for name in ('sender_reply','raw_response','schedule','native_state','closeout'):
        changed=copy.deepcopy(report);target=evaluation
        if name=='sender_reply':changed['policies'][0]['requests'][2]['reply']+='篡改'
        elif name=='raw_response':changed['policies'][0]['requests'][2]['raw_http_body']+=' '
        elif name=='schedule':changed['policies'][0]['requests'][2]['source_ordinal']=5
        elif name=='native_state':
            policy=next(p for p in report['policies'] if p['state_policy']=='logical_reset');target=Path(policy['trace_path']).resolve()
            rows=[json.loads(line) for line in original(target).splitlines()];rows[0]['state_observation']['logical_tokens_after_policy']=99
        else:
            target=evaluation.parent/report['policies'][0]['state_policy']/'provider-closeout.json';target=target.resolve();changed=json.loads(original(target));changed['model_closed']=False
        replacement='\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n' if name=='native_state' else json.dumps(changed,ensure_ascii=False)
        def substituted(path,*pos,**kw):return replacement if path.resolve()==target else original(path,*pos,**kw)
        try:
            with patch.object(Path,'read_text',substituted):verify(evaluation)
        except AssertionError:rejected=True
        else:raise AssertionError('Verifier accepted corruption: '+name)
        controls.append({'control':name,'virtual_modified_path':str(target),'replacement_sha256':sha256(replacement.encode()).hexdigest(),'rejected':rejected,'native_files_modified':False})
    assert verify(evaluation)==baseline
    result={'passed':True,'actual_llm_or_gpu':False,'uses_existing_native_evidence':True,'evaluation_sha256':sha256(evaluation.read_bytes()).hexdigest(),'controls':controls,'unmodified_baseline_passes_before_and_after':True}
    with args.output.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('5 in-memory evidence corruption controls rejected; native files unchanged, baseline passes before/after; no new model or GPU calls.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('evaluation',type=Path);parser.add_argument('--output',type=Path,required=True);main(parser.parse_args())

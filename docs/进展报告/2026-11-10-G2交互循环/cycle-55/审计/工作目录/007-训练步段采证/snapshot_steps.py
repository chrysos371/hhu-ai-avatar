"""Verify only already-finished optimizer log prefixes; never touch the worker."""
import argparse
import math
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
AUDIT=HERE.parents[1]
sys.path.insert(0,str(AUDIT))
from execution_common import RUN,TOKEN_RUN,read,sha,write_new,require
from reuse import load
from labeled_forward_capture import expected_records,fingerprint


def main(through):
    target=HERE/f'through-{through:02}'
    require(not target.exists(),'step prefix already archived')
    observed=read(RUN/'adapter/steps.json')
    require(len(observed)>=through,'requested closed optimizer prefix not yet present')
    steps=observed[:through]
    require([s['step'] for s in steps]==list(range(1,through+1)),'step order differs')
    expected=expected_records(read(TOKEN_RUN/'tokens.json'))
    validator=load('verify_execution').validate_transition
    rows=[];files={}
    for ordinal in range(1,through*4+1):
        entry=RUN/'train/actual-labeled-forwards'/f'{ordinal:04}-entry.json'
        result=entry.with_name(f'{ordinal:04}-result.json')
        start=read(entry);row=read(result);validator(start,row)
        key=fingerprint(row['input_ids'][0],row['labels'][0]);source=expected[key]
        require(row['completed'] and not row['fixture_cpu'] and row['split']==source['split']=='train'
            and row['id']==source['id'] and row['supervised_tokens']==source['supervised_tokens']
            and row['input_labels_sha256']==key and row['ordinal']==ordinal
            and row['model_training'] and row['grad_enabled'] and math.isfinite(row['loss'])
            and row['embedding_dtype']=='torch.bfloat16' and row['input_device'].startswith('cuda:')
            and row['input_device']==row['labels_device']==row['embedding_device'],'actual closed labeled training row differs')
        rows.append(row)
        files.update({str(p.relative_to(RUN)):sha(p) for p in (entry,result)})
    require(len({r['id'] for r in rows})==through*4,'closed prefix repeats sample identity')
    for i,step in enumerate(steps):
        group=rows[i*4:(i+1)*4]
        require(step['samples']==4 and step['sample_ids']==[r['id'] for r in group]
            and step['supervised_tokens']==sum(r['supervised_tokens'] for r in group)
            and math.isclose(step['loss'],sum(r['loss']/4 for r in group),rel_tol=1e-7,abs_tol=1e-7)
            and math.isfinite(step['gradient_norm']),'actual optimizer prefix differs from labeled tensor observations')
    write_new(target/'steps-prefix.json',steps)
    write_new(target/'external-files.json',files)
    write_new(target/'verification.json',{'verified':True,'through_optimizer_step':through,
        'actual_labeled_train_forwards_in_prefix':through*4,'prefix_sample_ids_unique':True,
        'actual_prefix_supervised_tokens':sum(r['supervised_tokens'] for r in rows),
        'step_ids_supervision_losses_equal_actual_tensor_rows':True,
        'external_closed_files':len(files),'external_manifest_sha256':sha(target/'external-files.json'),
        'steps_prefix_sha256':sha(target/'steps-prefix.json'),'collector_sha256':sha(Path(__file__)),
        'scope':'overlapping observed completed prefix;not additional optimizer steps or whole-training verification',
        'whole_train_stage_verified':False,'new_model_calls':0,'new_training_steps':0})
    print('verified closed train prefix',through,'steps/',through*4,'actual labeled forwards;no extra model call')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--through-step',type=int,choices=[11,22,33,44],required=True)
    main(p.parse_args().through_step)

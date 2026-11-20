"""C55 independent GPU retirement plus real supervisor wait terminal evidence."""
import argparse
import os
from pathlib import Path
from execution_common import RUN,STAGES,EVAL_STAGES,read,sha,require,write_new,verify_freeze
from reuse import load
from supervision import terminal

reference=load('verify_execution')
verify_labeled_training=reference.verify_labeled_training


def run(args):
    os.environ['CUDA_VISIBLE_DEVICES']=''
    verify_freeze(args.freeze,args.expected_freeze_sha256)
    folder=RUN/args.stage
    marker=read(folder/'process-result.json')
    require(marker['completed'] is True and marker['freeze_sha256']==args.expected_freeze_sha256,
        'stage did not complete; retain original failure without retry')
    supervised=terminal(args.stage,args.expected_freeze_sha256,marker)
    cleanup=reference.retired(marker)
    allocation=read(folder/'gpu-allocation.json')
    require(allocation['pid']==marker['pid'] and allocation['selected']['uuid']==marker['selected_gpu']['uuid'],
        'actual GPU allocation differs')
    proof_path=RUN/'ledger'/f'{args.stage}-verified.json'
    require(not proof_path.exists(),'stage already independently retired')
    result=reference.verify_evaluation(args.stage,folder) if args.stage in EVAL_STAGES else reference.verify_training(args.stage,folder)
    artifact=folder/'artifact-manifest.json'
    write_new(artifact,{str(p.relative_to(folder)):sha(p) for p in folder.rglob('*') if p.is_file()})
    result.update(execution_verified=True,process_retired=True,cleanup=cleanup,supervised_retirement=supervised,
        stage=args.stage,freeze_sha256=args.expected_freeze_sha256,process_result_sha256=sha(folder/'process-result.json'),
        artifact_manifest=str(artifact),artifact_manifest_sha256=sha(artifact),verifier_sha256=sha(Path(__file__)),
        reused_verifier_sha256=sha(Path(reference.__file__)),semantic_quality_approved=False,default_activation_authorized=False)
    write_new(proof_path,result)
    print('C55',args.stage,'independently verified; real wait0 and both processes retired;quality unapproved')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--freeze',type=Path,required=True)
    p.add_argument('--expected-freeze-sha256',required=True)
    p.add_argument('--stage',choices=STAGES,required=True)
    run(p.parse_args())

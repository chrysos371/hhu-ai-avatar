"""Short launcher for one admitted C55 stage; never retries or advances stages."""
import argparse
import json
from pathlib import Path
from execution_common import JOBS,STAGES,verify_freeze
from reuse import load
from supervision import jobs,command,context


def run(args):
    verify_freeze(args.freeze,args.expected_freeze_sha256)
    load('run_execution').previous_stage_check(args.stage,args.expected_freeze_sha256)
    print(json.dumps(jobs.launch(command(args.stage,args.expected_freeze_sha256),JOBS/args.stage,
        context=context(args.stage,args.expected_freeze_sha256),
        environment={'OMP_NUM_THREADS':'4','OPENBLAS_NUM_THREADS':'4'}),ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--freeze',type=Path,required=True)
    p.add_argument('--expected-freeze-sha256',required=True)
    p.add_argument('--stage',choices=STAGES,required=True)
    run(p.parse_args())

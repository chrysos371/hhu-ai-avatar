"""One fresh C55 GPU worker, admitted only as the frozen supervisor's child."""
import argparse
from pathlib import Path
from execution_common import STAGES,verify_freeze
from reuse import load
from supervision import admission,previous_jobs


def run(args):
    verify_freeze(args.freeze,args.expected_freeze_sha256)
    admission(args.stage,args.expected_freeze_sha256)
    previous_jobs(args.stage,args.expected_freeze_sha256)
    # Reused functions import C55 execution_common; their immutable __file__
    # remains C54, correctly binding the existing labeled observer's source.
    load('run_execution').run(args)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--freeze',type=Path,required=True)
    p.add_argument('--expected-freeze-sha256',required=True)
    p.add_argument('--stage',choices=STAGES,required=True)
    p.set_defaults(gpu=None)
    run(p.parse_args())

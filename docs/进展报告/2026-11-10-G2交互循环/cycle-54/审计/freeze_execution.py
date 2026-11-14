"""Freeze all five C54 stages after prepared CPU evidence; no model construction."""
import argparse
import subprocess
from execution_common import (ROOT,WORK,RUN,SEALS,STAGES,required_inputs,historical,
    protocol_check,preparation_check,external_inputs,sha,write_new,require)


def main(seal):
    require(seal==SEALS[53],'C54 explicit sealed C53 identity required')
    protocol_check();preparation_check()
    require(not RUN.exists(),'C54 real output already exists; do not repeat')
    path=WORK/'freeze-v1.json';require(not path.exists(),'C54 execution already frozen')
    names=required_inputs();hashes={n:sha(ROOT/n) for n in names}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(historical(head,names)==hashes,'commit all C54 execution inputs first')
    write_new(path,{'source_ref':head,'sha256':hashes,'run_root':str(RUN),'stages':list(STAGES),
        'prior_seals_sha256':{str(k):v for k,v in SEALS.items()},'external_sha256':external_inputs(),
        'scope':'single five-stage BF16 target-expression package experiment;no retries or default promotion',
        'total_generation_cap':404,'default_activation_authorized':False,'model_constructions':0,'training_steps':0})
    print('C54 five stages frozen',head,'inputs',len(hashes),'SHA',sha(path))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--c53-seal-sha256',required=True)
    main(parser.parse_args().c53_seal_sha256)

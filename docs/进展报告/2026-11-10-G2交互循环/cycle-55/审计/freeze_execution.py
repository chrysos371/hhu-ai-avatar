"""Freeze the fresh C55 five-stage experiment after CPU lifecycle admission."""
import argparse
import subprocess
from execution_common import ROOT,RUN,JOBS,WORK,SEALS,STAGES,require,sha,write_new,protocol_check,preparation_check,required_inputs,historical,external_inputs


def main(expected):
    require(expected==SEALS[54],'C55 explicit sealed C54 identity required')
    protocol_check();preparation_check()
    require(not RUN.exists() and not JOBS.exists(),'fresh C55 real/job roots required')
    target=WORK/'freeze-v1.json'
    require(not target.exists(),'C55 already frozen')
    names=required_inputs();hashes={n:sha(ROOT/n) for n in names}
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    require(historical(head,names)==hashes,'commit all C55 execution inputs before freezing')
    write_new(target,{'source_ref':head,'sha256':hashes,'run_root':str(RUN),'job_root':str(JOBS),'stages':list(STAGES),
        'prior_seals_sha256':{str(k):v for k,v in SEALS.items()},'external_sha256':external_inputs(),
        'scope':'new complete developmental target-expression package comparison; no retries or default promotion',
        'total_generation_cap':404,'prior_complete_generations':28,'prior_incomplete_boundary_entries':1,
        'default_activation_authorized':False,'model_constructions':0,'training_steps':0})
    print('C55 frozen',head,'inputs',len(hashes),'external',len(external_inputs()),'SHA',sha(target))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--c54-seal-sha256',required=True)
    main(p.parse_args().c54_seal_sha256)

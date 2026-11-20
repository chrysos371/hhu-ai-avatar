"""Fresh C55 admission; sealed C54 materials and mechanics remain read-only."""
from pathlib import Path
import re
from reuse import C54,load

reference=load('execution_common')
ROOT=reference.ROOT
BASE=Path(__file__).resolve().parents[1]
AUDIT=BASE/'审计'
ASSETS=reference.ASSETS
WORK=AUDIT/'工作目录/002-真实执行输入'
RUN=ASSETS/'artifacts/c55/real-target-transfer-v1'
JOBS=ASSETS/'artifacts/c55/supervised-stages-v1'
PROTOCOL=ROOT/'evals/interaction/cycle-55/correction-transfer-protocol.json'
DATA=reference.DATA
CASES=reference.CASES
TOKEN_RUN=reference.TOKEN_RUN
TOKENIZATION=reference.TOKENIZATION
LOCK=reference.LOCK
OLD_ADAPTER=reference.OLD_ADAPTER
STAGES=reference.STAGES
EVAL_STAGES=reference.EVAL_STAGES
SEALS={**reference.SEALS,54:'db7886f3532c1d8a5ec6212a1772f0c282fafe6ed9db7e2a4c50b5a4a5f5e708'}
read,sha,require,write_new,historical=(getattr(reference,n) for n in ('read','sha','require','write_new','historical'))
environment_reader=reference.environment_reader


def protocol_check():
    original=reference.protocol_check()
    actual=read(PROTOCOL)
    extra={'scope','supervision','prior_attempt'}
    require({k:v for k,v in actual.items() if k not in extra}=={k:v for k,v in original.items() if k not in extra},
        'C55 model/data/training/evaluation settings differ from registered C54 package')
    require(actual['supervision']=={'controller':'scripts/lab/run_frozen_capability_job.py',
        'independent_session':True,'real_wait_exit_code_required':True,'frozen_argv_context_parent_child_binding':True,
        'new_job_directory_per_stage_no_retry':True,'user_pause_stops_progression':True},'C55 supervision contract differs')
    prior=actual['prior_attempt']
    require(prior=={'cycle':54,'retired_incomplete':True,'complete_generations':28,'incomplete_boundary_entries':1,
        'complete_trials':13,'worker_exit_code':None,'old_cases_are_known_development':True,
        'combined_complete_generate_cap':432,'combined_boundary_entry_cap':433,'seal_sha256':SEALS[54]},
        'C54 partial costs or incomplete scope changed')
    return actual


def preparation_check():
    environment=reference.preparation_check()
    seal=C54/'审计/证据清单.json'
    require(sha(seal)==SEALS[54] and all(sha(C54/n)==v for n,v in read(seal).items()),'C54 sealed bytes changed')
    controls=read(AUDIT/'工作目录/001-独立托管控制/lifecycle-v1.json')
    require(controls['verified'] and len(controls['controls'])==5
        and controls['probe_sha256']==sha(AUDIT/'probe_supervisor.py')
        and controls['supervisor_sha256']==sha(ROOT/'scripts/lab/run_frozen_capability_job.py'),
        'actual CPU lifecycle proof/source differs')
    require(all(sha(Path(controls['external_root'])/n)==v for n,v in controls['external_sha256'].items()),'CPU lifecycle raw bytes changed')
    tests=read(AUDIT/'工作目录/001-独立托管控制/existing-tests-binding-v1.json')
    require(tests['passed']==26 and tests['failed']==0 and all(sha(ROOT/n)==v for n,v in tests['files_sha256'].items()),'26-test source binding differs')
    return environment


def required_inputs():
    names=set(reference.required_inputs())
    names.update(str(p.relative_to(ROOT)) for p in AUDIT.glob('*.py'))
    for number in ('001','003'):
        for folder in (AUDIT/'工作目录').glob(number+'-*'):
            names.update(str(p.relative_to(ROOT)) for p in folder.rglob('*') if p.is_file())
    names.update(str((C54/'审计'/n).relative_to(ROOT)) for n in ('证据清单.json',))
    names.add('scripts/lab/run_frozen_capability_job.py')
    return sorted(names)


def external_inputs():
    result=reference.external_inputs()
    r=read(C54/'审计/工作目录/009-中断与退役审计/retirement-v1.json')
    manifest=Path(r['external_raw_manifest'])
    require(sha(manifest)==r['external_raw_manifest_sha256'],'C54 partial manifest changed')
    result[str(manifest)]=sha(manifest)
    result.update({str(reference.RUN/n):sha(reference.RUN/n) for n in read(manifest)})
    require({n:result[str(reference.RUN/n)] for n in read(manifest)}==read(manifest),'C54 partial raw bytes changed')
    return result


def verify_freeze(path,expected):
    path=Path(path).resolve()
    require(path==(WORK/'freeze-v1.json').resolve(),'C55 registered freeze path required')
    require(path.is_file(),'C55 frozen execution descriptor missing')
    require(type(expected) is str and re.fullmatch('[0-9a-f]{64}',expected) is not None and sha(path)==expected,'C55 freeze SHA differs')
    frozen=read(path);protocol_check();preparation_check()
    require(frozen['run_root']==str(RUN) and frozen['job_root']==str(JOBS) and frozen['stages']==list(STAGES)
        and frozen['prior_seals_sha256']=={str(k):v for k,v in SEALS.items()}
        and frozen['default_activation_authorized'] is False,'C55 execution identity differs')
    names=required_inputs()
    require(set(names)==set(frozen['sha256']) and all(sha(ROOT/n)==v for n,v in frozen['sha256'].items()),'C55 frozen execution inputs changed')
    require(historical(frozen['source_ref'],names)==frozen['sha256'],'C55 frozen inputs were not committed')
    require(external_inputs()==frozen['external_sha256'],'C55 external data/adapter/partial bytes changed')
    return frozen


def training_binding_files():
    return {k:RUN/p.relative_to(reference.RUN) for k,p in reference.training_binding_files().items()}


def verify_training_binding():
    proof=read(RUN/'ledger/train-verified.json')
    require(all(proof[k]==sha(p) for k,p in training_binding_files().items()),'verified C55 training artifacts changed')

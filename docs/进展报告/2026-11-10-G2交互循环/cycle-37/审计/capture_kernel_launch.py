"""Read only the known owned provider's parent arguments; never read environments."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[5]
parser=argparse.ArgumentParser();parser.add_argument('--evaluation',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--expected-gate-sha256',required=True);args=parser.parse_args();assert not args.output.exists()
started=time.monotonic()
while True:
    try:
        record=json.loads(args.evaluation.read_text())
        if record['provider_pid'] is not None:break
    except (FileNotFoundError,json.JSONDecodeError):pass
    if time.monotonic()-started>30:raise RuntimeError('Owned launch observation not ready; no fabricated witness')
    time.sleep(.1)
status=Path('/proc')/str(record['provider_pid'])/'status';ppid=int(next(line.split()[1] for line in status.read_text().splitlines() if line.startswith('PPid:')))
argv=[p.decode() for p in (Path('/proc')/str(ppid)/'cmdline').read_bytes().split(b'\0') if p]
def option(name):return argv[argv.index(name)+1]
assert option('--model')==record['model_id'] and int(option('--repetition'))==record['repetition']
assert option('--expected-freeze-sha256')==record['freeze_sha256']
gate=(ROOT/option('--prior-4b-gate')).resolve();sha=hashlib.sha256(gate.read_bytes()).hexdigest()
assert sha==option('--expected-prior-gate-sha256')==args.expected_gate_sha256
result={'scope':'live_kernel_argv_observation_of_owned_provider_parent_no_environ','observed_utc':datetime.now(timezone.utc).isoformat(),
 'observer_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'observer_git_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
 'provider_pid':record['provider_pid'],'controller_pid':ppid,'actual_kernel_controller_argv':argv,'model':record['model_id'],'repetition':record['repetition'],
 'actual_prior_gate_path':str(gate),'actual_prior_gate_sha256':sha,'actual_freeze_sha256':record['freeze_sha256'],'verified':True}
args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Observed owned32B controller argv and actual gate SHA from kernel')

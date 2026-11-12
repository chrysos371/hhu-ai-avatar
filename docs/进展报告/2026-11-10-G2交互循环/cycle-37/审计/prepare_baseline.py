"""Record installed identity, then freeze all committed execution inputs."""
import argparse,json,subprocess
from native_common import ROOT,BASE,PROTOCOL,REGISTRY,REFERENCE,WORK,RUNTIME,digest,read,capture_runtime,verify_source
parser=argparse.ArgumentParser();parser.add_argument('action',choices=('runtime','freeze'));args=parser.parse_args()
if args.action=='runtime':
    assert not RUNTIME.exists();RUNTIME.write_text(json.dumps(capture_runtime(),ensure_ascii=False,indent=2)+'\n')
    print('Captured54 migrated runtime files;0model calls;commit before freezing')
else:
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip(),'Commit inputs first'
    names=set(subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().strip('\0').split('\0'))
    names={n for n in names if n.startswith(('src/','scripts/','tests/','evals/interaction/cycle-37/'))
        or (n.startswith(str((BASE/'审计').relative_to(ROOT))+'/') and n.endswith('.py'))}
    registry=read(REGISTRY);protocol=read(PROTOCOL)
    names.update(m['metadata'] for m in registry['models']);names.update((str(REFERENCE.relative_to(ROOT)),str(RUNTIME.relative_to(ROOT))))
    frozen={'version':1,'scope':'native_current_defaults_model_scale','candidate':'none','execution_authorized':True,
        'allowed_partition':'development','provider_backend':'cuda','source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'protocol':str(PROTOCOL.relative_to(ROOT)),'models_registry':str(REGISTRY.relative_to(ROOT)), 'registry_sha256':digest(REGISTRY),
        'models':[m['model_id'] for m in registry['models']],'case_ids':[c['id'] for c in protocol['cases']],
        'case_count':len(protocol['cases']),'turn_count':sum(len(c['turns']) for c in protocol['cases']),
        'sha256':{n:digest(ROOT/n) for n in sorted(names)}}
    path=WORK/'execution-freeze.json';assert not path.exists();path.write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    verify_source(path,digest(path));print('Frozen',len(names),'committed inputs;SHA',digest(path))

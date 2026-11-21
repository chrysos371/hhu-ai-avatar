"""Source-bound standard-configuration browser gates with retained fixtures."""
import argparse
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import runpy
import subprocess
import tarfile
import time
import os

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
UI=ASSETS/'artifacts/release/final-build-v7/frontend'
SUITES={'base':([],{}),'playback':(['playback-audit.spec.ts'],{'AVATAR_E2E_PLAYBACK_AUDIT':'1'})}
for key,file,flag in [
    ('external-erase','external-erase','EXTERNAL_ERASE'),('history-restore','history-restore','RESTORE_AUDIT'),
    ('history-audit','history-audit','HISTORY_AUDIT'),('notification','notification-audit','NOTIFICATION_AUDIT'),
    ('navigation','navigation-audio-audit','NAVIGATION_AUDIO'),('reminder-privacy','reminder-delivery-privacy','REMINDER_PRIVACY_AUDIT'),
    ('receipts','action-receipts','ACTION_RECEIPTS')]:
    SUITES[key]=([file+'.spec.ts'],{'AVATAR_E2E_'+flag:'1'})
for case in ('normal_claim','response_drop_after_commit','navigation_before_response','ack_response_drop_after_commit'):
    for kind in ('recovery',):
        SUITES['reminder-'+case.replace('_','-')+'-'+kind]=(['reminder-delivery-'+kind+'.spec.ts'],
            {'AVATAR_E2E_REMINDER_DELIVERY_CASE':case})

# Current privacy contract requires one controlled due reminder; old baseline remains unchanged.
SUITES['reminder-privacy'][1]['AVATAR_E2E_REMINDER_DELIVERY_CASE']='normal_claim'

SUITES['real-voice']=(['real-voice.spec.ts'],dict(AVATAR_E2E_REAL_ASR_MODEL=str(ASSETS/'models/faster-whisper-small'),AVATAR_E2E_ASR_BACKEND='faster-whisper',AVATAR_E2E_ASR_DEVICE='cpu',AVATAR_E2E_REAL_TTS='1'))


def digest(p):return sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--suite',choices=sorted(SUITES),required=True);p.add_argument('--label',required=True)
    args=p.parse_args();assert re.fullmatch(r'browser-[a-z0-9-]+-v[1-9][0-9]*',args.label)
    proof_path=HERE/(args.label+'.json');assert not proof_path.exists()
    raw=ASSETS/'artifacts/release'/args.label;assert not raw.exists()
    common=runpy.run_path(str(HERE.parent/'006-写作交付与严格格式/run_current_python.py'))
    before=common['snapshot']();before[str(Path(__file__).relative_to(ROOT))]=digest(Path(__file__))
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        assert {m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}==before
    ui={str(f.relative_to(UI)):digest(f) for f in sorted(UI.rglob('*')) if f.is_file()}
    assert ui==json.loads((UI.parent/'build-result.json').read_text())['ui_sha256']
    raw.mkdir(parents=True)
    files,options=SUITES[args.suite]
    env={k:v for k,v in os.environ.items() if not k.startswith('AVATAR_E2E_')}
    env.update(options,HHU_AVATAR_DATA_ROOT=str(ASSETS),EMBEDDING_MODEL='',
        AVATAR_E2E_CAPABILITY_CONTRACT='1',AVATAR_E2E_ROLE_STATE='1',
        AVATAR_E2E_FRONTEND_DIR=str(UI),AVATAR_E2E_RETAIN_STATE=str(raw/'server-state'),
        AVATAR_E2E_RUNTIME_EVIDENCE=str(raw/'fixture-runtime.json'),AVATAR_E2E_OUTPUT_DIR=str(raw/'playwright'),
        PLAYWRIGHT_JSON_OUTPUT_FILE=str(raw/'report.json'),PLAYWRIGHT_HTML_OPEN='never')
    argv=[str(ROOT/'scripts/frontend.sh'),'run','e2e','--',*files,'--reporter=json','--timeout=0']
    started=time.monotonic()
    with (raw/'stdout.log').open('x') as out,(raw/'stderr.log').open('x') as err:
        result=subprocess.run(argv,cwd=ROOT/'frontend',env=env,stdout=out,stderr=err)
    report=json.loads((raw/'report.json').read_text()) if (raw/'report.json').exists() else {}
    stats=report.get('stats',{});runtime=json.loads((raw/'fixture-runtime.json').read_text()) if (raw/'fixture-runtime.json').exists() else {}
    stable=all(digest(ROOT/f)==h for f,h in before.items())
    ui_stable=all(digest(UI/f)==h for f,h in ui.items())
    passed=bool(result.returncode==0 and stable and ui_stable and stats.get('unexpected')==0
        and stats.get('expected',0)>0 and not report.get('errors') and runtime.get('capability_contract_enabled') is True
        and runtime.get('role_state_enabled') is True and runtime.get('frontend_dir')==str(UI.resolve()))
    proof=dict(suite=args.suite,source_ref=head,source_sha256=before,source_inputs=len(before),source_unchanged=stable,
        ui_sha256=ui,ui_unchanged=ui_stable,argv=argv,actual_returncode=result.returncode,
        stats=stats,passed=passed,seconds_including_server_browser_cleanup=time.monotonic()-started,
        whole_stage_wallclock_cutoff=None,required_fixture_options=options,
        scope='actual browser/local HTTP/SSE with standard source/role configuration and retained controlled fixtures; no native model/physical or human approval',
        raw=str(raw),raw_sha256={str(f.relative_to(raw)):digest(f) for f in sorted(raw.rglob('*')) if f.is_file()})
    with proof_path.open('x') as f:json.dump(proof,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({k:proof[k] for k in ('suite','actual_returncode','stats','passed','seconds_including_server_browser_cleanup')}))
    assert passed,'browser failure retained'


if __name__=='__main__':main()

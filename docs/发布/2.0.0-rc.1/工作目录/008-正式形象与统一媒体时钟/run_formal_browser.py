"""Actual software-WebGL/HTTP/media fixture, protected direct children, no model."""
import argparse
from contextlib import ExitStack
from hashlib import sha256
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import tarfile
import time
from urllib.request import urlopen

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
ASSETS=Path('/data/Users/zrh/data/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'scripts/lab'))
from owned_provider import start_provider,finish_provider
import run_frozen_capability_job as jobs


def digest(path):return sha256(path.read_bytes()).hexdigest()


def snapshot(extra=()):
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected={p for p in names if p.startswith(('src/','scripts/','tests/','frontend/','evals/','training/'))
        or p=='pyproject.toml' or p.startswith('requirements') and p.endswith('.txt')}
    selected.update(str(p.relative_to(ROOT)) for p in (Path(__file__),HERE/'formal_browser.cjs',HERE/'浏览器门控协议-v1.md'))
    selected.update(str(p.relative_to(ROOT)) for p in extra)
    return {p:digest(ROOT/p) for p in sorted(selected)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--version',type=int,required=True)
    parser.add_argument('--ui-proof',default='development-ui-promotion-v1.json')
    parser.add_argument('--failure-control',action='store_true');args=parser.parse_args()
    assert 1<=args.version<=99
    assert re.fullmatch(r'development-ui-promotion-v[1-9][0-9]*\.json',args.ui_proof)
    extra=(HERE/args.ui_proof,)
    raw=ASSETS/'artifacts/release'/('formal-browser-v'+str(args.version));raw.mkdir(parents=True,exist_ok=False)
    proof_path=HERE/('formal-browser-v'+str(args.version)+'.json');assert not proof_path.exists()
    before=snapshot(extra);head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    archive=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        assert {m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}==before
    assert not any(p and p.startswith(('src/','scripts/','tests/','frontend/','evals/')) for p in subprocess.check_output(
        ['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0'))
    ui={str(p.relative_to(ROOT/'frontend/dist')):digest(p) for p in (ROOT/'frontend/dist').rglob('*') if p.is_file()}
    assert ui==json.loads((HERE/args.ui_proof).read_text())['ui_sha256']
    env=os.environ.copy();env.update(PYTHONPATH=str(ROOT/'src'),HHU_AVATAR_DATA_ROOT=str(ASSETS),
        PLAYWRIGHT_BROWSERS_PATH=str(ASSETS/'runtime/playwright'),AVATAR_E2E_RUNTIME_EVIDENCE=str(raw/'server-runtime.json'),
        AVATAR_E2E_RETAIN_STATE=str(raw/'server-state'),AVATAR_E2E_CAPABILITY_CONTRACT='1',AVATAR_E2E_ROLE_STATE='1')
    for key in ('AVATAR_E2E_LLM_PROVIDER','AVATAR_E2E_REAL_ASR_MODEL','AVATAR_E2E_REMINDER_DELIVERY_CASE'):
        env.pop(key,None)
    for key in ('IDENTITY_GROUNDING','PROFILE_GROUNDING','TASK_DELIVERY','LITERAL_COMPOSITION'):
        env['AVATAR_E2E_'+key]='0'
    libs=ASSETS/'runtime/browser-libs/extracted/usr/lib/x86_64-linux-gnu'
    if libs.is_dir():env['LD_LIBRARY_PATH']=str(libs)+os.pathsep+env.get('LD_LIBRARY_PATH','')
    fonts=ASSETS/'runtime/browser-libs/fontconfig.xml'
    if fonts.is_file():env['FONTCONFIG_FILE']=str(fonts)
    node=ASSETS/'runtime/node-npm/node_modules/node/bin/node'
    with socket.socket() as check:
        check.settimeout(1);assert check.connect_ex(('127.0.0.1',18765))!=0,'refuse occupied fixture port'
    proof=dict(passed=False,source_ref=head,source_sha256=before,source_unchanged=False,ui_sha256=ui,
        failure_control=args.failure_control,ui_proof=args.ui_proof,completed_browser_viewports=0,
        node_sha256=digest(node),core_python=sys.executable,
        core_versions={p:importlib.metadata.version(p) for p in ('openai','httpx','numpy')},
        actual_native_model_calls=0,physical_or_human_approval=False,whole_stage_deadline=None,raw_root=str(raw))
    proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    server=None;probe=None;server_identity=None;probe_identity=None;failure=None;started=time.monotonic()
    with ExitStack() as stack:
        try:
            server_log=stack.enter_context((raw/'server.log').open('x'))
            server,launch=start_provider([sys.executable,'-B',str(ROOT/'tests/helpers/serve_admin_e2e.py')],
                raw/'server-edge',cwd=ROOT/'frontend',env=env,stdout=server_log,process_role='browser_fixture')
            server_identity=launch['provider_identity'];proof['server_launch']=launch
            ready_started=time.monotonic()
            while True:
                assert server.poll() is None,'fixture exited before readiness'
                try:
                    with urlopen('http://127.0.0.1:18765/',timeout=2) as response:
                        if response.status==200:break
                except OSError:pass
                assert time.monotonic()-ready_started<30,'fixture readiness engineering boundary'
                time.sleep(.1)
            probe_log=stack.enter_context((raw/'probe.log').open('x'))
            command=([str(node),'-e','setTimeout(()=>process.exit(7),200)'] if args.failure_control
                else [str(node),str(HERE/'formal_browser.cjs'),str(raw)])
            probe,launch=start_provider(command,raw/'probe-edge',
                cwd=ROOT,env=env,stdout=probe_log,process_role='browser_probe')
            probe_identity=launch['provider_identity'];proof['probe_launch']=launch
            proof['actual_probe_wait_code']=probe.wait()
            proof['probe_terminal']=finish_provider(probe,raw/'probe-edge')
            assert proof['actual_probe_wait_code']==0,'browser failures retained'
            browser=json.loads((raw/'browser-result.json').read_text());assert browser['passed']
            proof['completed_browser_viewports']=sum(row.get('disposed') is True for row in browser['viewports'])
            proof['browser_summary']={k:v for k,v in browser.items() if k not in ('viewports',)}
            proof['browser_executable_sha256']=digest(Path(browser['executable']))
            proof['source_unchanged']=snapshot(extra)==before;assert proof['source_unchanged']
            proof['passed']=True
        except BaseException as error:
            proof['error']=repr(error);failure=error
        finally:
            for child,identity,name in ((probe,probe_identity,'probe'),(server,server_identity,'server')):
                if child is None:continue
                try:
                    if child.poll() is None:jobs.signal_owned_child(child,identity,signal.SIGINT)
                    try:code=child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        jobs.signal_owned_child(child,identity,signal.SIGKILL);code=child.wait()
                    proof['actual_'+name+'_wait_code']=code
                    terminal=raw/(name+'-edge')/'terminal.json'
                    if not terminal.exists():proof[name+'_terminal']=finish_provider(child,raw/(name+'-edge'))
                    proof[name+'_identity_retired']=not jobs.matches(identity)
                    if code!=0 or not proof[name+'_identity_retired']:proof['passed']=False
                except BaseException as error:
                    proof['passed']=False;proof[name+'_cleanup_error']=repr(error);failure=failure or error
            proof['seconds_including_fixture_and_cleanup']=time.monotonic()-started
    proof['raw_sha256']={str(p.relative_to(raw)):digest(p) for p in sorted(raw.rglob('*')) if p.is_file()}
    proof['source_unchanged']=snapshot(extra)==before
    proof['finalized_after_cleanup']=True
    proof_path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    if failure is not None:raise failure
    assert proof['passed']
    print('Formal browser passed; source inputs',len(before),'raw files',len(proof['raw_sha256']))


if __name__=='__main__':main()

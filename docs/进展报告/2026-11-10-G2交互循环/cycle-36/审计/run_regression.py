"""Run stable-source C36 regressions with separate runtime artifact hashes."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
WORK = Path(__file__).resolve().parent / '工作目录/001-日常浏览器回归'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot():
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = {name for name in names if name.startswith(('src/', 'scripts/', 'tests/', 'frontend/'))}
    selected.add('evals/interaction/cycle-36/maintained-state-privacy-protocol.json')
    return {name: digest(ROOT / name) for name in sorted(selected)}


def artifacts():
    return {str(path.relative_to(ROOT)): digest(path) for path in sorted((ROOT / 'frontend/dist').rglob('*')) if path.is_file()}


def main(mode, tag=''):
    assert not tag or re.fullmatch(r'[a-z0-9_-]+', tag)
    prefix = tag + '-' if tag else ''
    output = WORK / (prefix + mode + '-final-binding.json')
    log = WORK / (prefix + mode + '-final.log')
    assert not output.exists() and not log.exists()
    before = snapshot()
    commands = {'python': [sys.executable, '-m', 'pytest', 'tests/', '-q'],
        'frontend': ['./scripts/frontend.sh', 'run', 'test', '--', '--run'],
        'build': ['./scripts/frontend.sh', 'run', 'build'],
        'browser': ['./scripts/frontend.sh', 'run', 'e2e'],
        'browser_targeted': ['./scripts/frontend.sh', 'run', 'e2e', '--', 'state-privacy.spec.ts',
            '--output', str(Path(os.environ['HHU_AVATAR_DATA_ROOT']) / 'tmp/c36-targeted-browser-results')]}
    env = dict(os.environ)
    runtime = WORK / (prefix + 'browser-final-runtime.json')
    if mode.startswith('browser'):
        for key in list(env):
            if key.startswith('AVATAR_E2E_'):
                del env[key]
        env['AVATAR_E2E_RUNTIME_EVIDENCE'] = str(runtime)
    report = {'scope': 'cycle36_privacy_state_regression_only', 'mode': mode,
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'argv': commands[mode], 'source_git_sha256': before,
        'python_prefix': sys.prefix, 'driver_sha256': digest(Path(__file__)),
        'exit_code': None, 'source_unchanged': False, 'gpu_inference_claim': False}
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    started = time.monotonic()
    with log.open('x') as stream:
        completed = subprocess.run(commands[mode], cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    report.update(exit_code=completed.returncode, source_unchanged=snapshot() == before,
        seconds=time.monotonic() - started, log_sha256=digest(log))
    if mode.startswith('browser') or mode == 'build':
        report['runtime_artifact_sha256'] = artifacts()
    if mode.startswith('browser') and runtime.exists():
        actual = json.loads(runtime.read_text())
        matches = (actual['python_prefix'] == sys.prefix and actual['project_root'] == str(ROOT)
            and actual['state_privacy_protocol_sha256'] == before['evals/interaction/cycle-36/maintained-state-privacy-protocol.json'])
        for name, path in actual['module_paths'].items():
            relative = str(Path(path).relative_to(ROOT))
            matches = matches and actual['module_sha256'][name] == before[relative]
        matches = matches and actual['frontend_sha256'] == report['runtime_artifact_sha256']
        report.update(runtime_sha256=digest(runtime), runtime_matches=matches,
            default_controlled_provider=True, optional_e2e_flags_cleared=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    assert completed.returncode == 0 and report['source_unchanged'], mode + ' failed; retained log and binding'
    if mode.startswith('browser'):
        assert report.get('runtime_matches') is True
    print(mode, 'passed:', len(before), 'stable committed inputs;', report['seconds'], 'seconds')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('python', 'frontend', 'build', 'browser', 'browser_targeted'))
    parser.add_argument('--tag', default='', help='Fresh output namespace; never overwrite a previous run')
    args = parser.parse_args()
    main(args.mode, args.tag)

"""Run one stable-source product check; preserve logs, status and runtime identity."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[5]
WORK = Path(__file__).resolve().parents[1] / '审计/工作目录/002-系统回归'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sources(mode):
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = {name for name in names if name and (
        name.startswith(('src/', 'tests/', 'scripts/'))
        or name in ('pyproject.toml', 'requirements.txt', 'requirements-web.txt'))}
    selected.add(str(Path(__file__).relative_to(ROOT)))
    if mode == 'default-browser':
        selected.update(name for name in names if name.startswith('frontend/'))
        selected.update(str(path.relative_to(ROOT)) for path in (ROOT / 'frontend/dist').rglob('*') if path.is_file())
    return {name: digest(ROOT / name) for name in sorted(selected)}


def main(mode):
    binding = WORK / (mode + '-binding.json')
    log = WORK / (mode + '.log')
    assert not binding.exists() and not log.exists(), 'Never overwrite a completed or failed run'
    source = sources(mode)
    env = dict(os.environ)
    env['PYTHONPATH'] = str(ROOT / 'src')
    runtime = WORK / 'browser-runtime.json'
    if mode == 'full-python':
        argv = [sys.executable, '-m', 'pytest', 'tests/', '-q']
    else:
        for key in list(env):
            if key.startswith('AVATAR_E2E_'):
                del env[key]
        env['AVATAR_E2E_RUNTIME_EVIDENCE'] = str(runtime)
        argv = ['./scripts/frontend.sh', 'run', 'e2e']
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'argv': argv, 'source_sha256': source, 'source_unchanged': False, 'exit_code': None,
        'actual_native_model_claim': False, 'mode': mode}
    binding.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    start = time.monotonic()
    with log.open('x') as stream:
        completed = subprocess.run(argv, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
    report.update(exit_code=completed.returncode, seconds=time.monotonic() - start,
        source_unchanged=sources(mode) == source, log_sha256=digest(log))
    if mode == 'default-browser':
        actual = json.loads(runtime.read_text())
        expected_modules = ('avatar.main', 'avatar.web', 'avatar.web_api', 'avatar.web_state',
            'avatar.brain.emotion', 'avatar.brain.memory', 'avatar.brain.reminders')
        matches = actual['project_root'] == str(ROOT)
        for name in expected_modules:
            path = ROOT / 'src' / Path(*name.split('.')).with_suffix('.py')
            matches = matches and actual['module_paths'].get(name) == str(path)
            matches = matches and actual['module_sha256'].get(name) == source[str(path.relative_to(ROOT))]
        matches = matches and all(source.get(name) == value for name, value in actual['frontend_sha256'].items())
        report.update(runtime_sha256=digest(runtime), runtime_matches=matches,
            default_controlled_provider=True, optional_e2e_flags_cleared=True)
    binding.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    assert report['exit_code'] == 0 and report['source_unchanged'], report
    if mode == 'default-browser':
        assert report['runtime_matches'], 'Browser imported different source or bundle'
    print(mode, 'passed; stable inputs:', len(source), 'seconds:', report['seconds'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('full-python', 'default-browser'))
    main(parser.parse_args().mode)

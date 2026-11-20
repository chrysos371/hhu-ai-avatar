"""Build a source-bound wheel+sdist with its UI. This does not approve a release.

Run with the isolated interpreter provisioned from requirements-build.txt.
All staging/build/output bytes go into a fresh directory in the project data root.
"""
import argparse
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from avatar import __version__
from avatar.application_assets import check_frontend
from avatar.paths import project_data_root


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def sources():
    names = subprocess.check_output(['git', 'ls-files', '-z', '--', 'src', 'scripts', 'frontend',
        'pyproject.toml', 'README.md', 'requirements-build.txt'], cwd=ROOT).decode().split('\0')
    return {n: sha(ROOT/n) for n in names if n}


def unpack(raw, target):
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            dest = target/member.name
            if not dest.resolve().is_relative_to(target) or not (member.isfile() or member.isdir()):
                raise ValueError('Only contained regular source files/directories are build inputs')
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(member).read())
                dest.chmod(member.mode)


def build(output):
    data = project_data_root(ROOT).resolve()
    output = output.absolute()
    if not output.resolve().is_relative_to(data) or output.resolve() == data:
        raise ValueError('Use a new output directory inside the project data root')
    if data.is_relative_to(Path('/data')) and not os.path.ismount('/data'):
        raise ValueError('/data must be mounted before writing')
    before = sources()
    untracked = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '--',
        'src', 'scripts', 'frontend'], cwd=ROOT, text=True)
    if untracked.strip():
        raise ValueError('Commit new execution inputs before building')
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    raw = subprocess.check_output(['git', 'archive', '--format=tar', ref, '--', *before], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        archived = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
            for m in archive if m.isfile()}
    if archived != before:
        raise ValueError('Commit all changed execution inputs before building')
    versions = {}
    for line in (ROOT/'requirements-build.txt').read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, expected = line.split('==')
        versions[name] = importlib.metadata.version(name)
        if versions[name] != expected:
            raise ValueError('Build package differs from pinned version: '+name)
    front = json.loads((ROOT/'frontend/package.json').read_text())
    normalized = re.sub(r'rc(\d+)$', r'-rc.\1', __version__)
    if front['version'] != normalized:
        raise ValueError('Frontend/Python versions differ')
    output.mkdir(parents=True, exist_ok=False)
    state = dict(artifact_status='candidate_not_release_approved', source_ref=ref,
        version=__version__, source_sha256=before, build_packages=versions, passed=False)
    write(output/'build-start.json', state)
    try:
        staging = output/'source'
        staging.mkdir()
        unpack(raw, staging)
        env = dict(os.environ, SOURCE_DATE_EPOCH=subprocess.check_output(
            ['git', 'show', '-s', '--format=%ct', ref], cwd=ROOT, text=True).strip())
        with (output/'frontend-build.log').open('x') as log:
            subprocess.run([str(ROOT/'scripts/frontend.sh'), 'run', 'build', '--',
                '--outDir', str(output/'frontend')], cwd=ROOT, env=env,
                stdout=log, stderr=subprocess.STDOUT, check=True)
        if not check_frontend(output/'frontend')['available']:
            raise ValueError('Frontend build is incomplete')
        ui = {str(p.relative_to(output/'frontend')): sha(p)
            for p in sorted((output/'frontend').rglob('*')) if p.is_file()}
        if any(p.is_symlink() for p in (output/'frontend').rglob('*')):
            raise ValueError('Do not bundle external asset symlinks')
        shutil.copytree(output/'frontend', staging/'src/avatar/static')
        write(staging/'src/avatar/release-build.json', dict(source_ref=ref,
            source_sha256=before, ui_sha256=ui, artifact_status=state['artifact_status']))
        with (output/'python-build.log').open('x') as log:
            subprocess.run([sys.executable, '-B', '-m', 'build', '--no-isolation',
                '--sdist', '--wheel', '--outdir', str(output/'dist')], cwd=staging,
                env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        wheels = list((output/'dist').glob('*.whl'))
        sdists = list((output/'dist').glob('*.tar.gz'))
        if len(wheels) != 1 or len(sdists) != 1:
            raise ValueError('Require exactly one wheel and one sdist')
        with zipfile.ZipFile(wheels[0]) as wheel:
            for name, expected in ui.items():
                if hashlib.sha256(wheel.read('avatar/static/'+name)).hexdigest() != expected:
                    raise ValueError('Wheel UI bytes differ')
            if 'avatar/release-build.json' not in wheel.namelist():
                raise ValueError('Wheel provenance missing')
        with tarfile.open(sdists[0]) as archive:
            for name, expected in ui.items():
                member = next(m for m in archive if m.name.endswith('/src/avatar/static/'+name))
                if hashlib.sha256(archive.extractfile(member).read()).hexdigest() != expected:
                    raise ValueError('Sdist UI bytes differ')
        if sources() != before:
            raise ValueError('Build inputs changed during execution')
        state.update(passed=True, ui_sha256=ui, source_unchanged=True,
            artifacts={str(p.relative_to(output)): sha(p) for p in wheels+sdists})
    except BaseException as error:
        state['error'] = repr(error)
        raise
    finally:
        write(output/'build-result.json', state)
    print(json.dumps({'output': str(output), 'artifacts': state['artifacts'],
        'status': state['artifact_status']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    build(parser.parse_args().output)

"""Fresh lock-bound frontend install/build, retaining all old dependency trees."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
DATA = Path('/data/Users/zrh/data/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent
OUTPUT = DATA/'artifacts/release/frontend-clean-v2'
NODE = DATA/'runtime/node-npm/node_modules/node/bin/node'
NPM = DATA/'runtime/node-v22.14.0-linux-x64/lib/node_modules/npm/bin/npm-cli.js'
RESOLVER = DATA/'runtime/npm-registry-ipv4.cjs'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    assert os.path.ismount('/data')
    OUTPUT.mkdir(parents=True, exist_ok=False)
    ref = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '-z', '--', 'frontend'], cwd=ROOT).decode().split('\0')
    before = {n: digest(ROOT/n) for n in names if n}
    source = OUTPUT/'source'
    source.mkdir()
    raw = subprocess.check_output(['git', 'archive', '--format=tar', ref, '--', 'frontend'], cwd=ROOT)
    archived = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive:
            target = source/member.name
            assert target.resolve().is_relative_to(source) and (member.isfile() or member.isdir())
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                body = archive.extractfile(member).read()
                target.write_bytes(body)
                archived[member.name] = hashlib.sha256(body).hexdigest()
    assert archived == before
    (OUTPUT/'npmrc-user').touch(exist_ok=False)
    (OUTPUT/'npmrc-global').touch(exist_ok=False)
    env = dict(os.environ, PATH=str(NODE.parent)+os.pathsep+os.environ['PATH'],
        HHU_AVATAR_DATA_ROOT=str(DATA), NPM_CONFIG_CACHE=str(DATA/'cache/npm'), TMPDIR=str(DATA/'tmp'),
        NPM_CONFIG_USERCONFIG=str(OUTPUT/'npmrc-user'), NPM_CONFIG_GLOBALCONFIG=str(OUTPUT/'npmrc-global'),
        NODE_OPTIONS='--require='+str(RESOLVER), TZ='UTC',
        SOURCE_DATE_EPOCH=subprocess.check_output(['git', 'show', '-s', '--format=%ct', ref], cwd=ROOT, text=True).strip())
    front = source/'frontend'
    prefix = [str(NODE), str(NPM), '--prefix', str(front)]
    state = dict(source_ref=ref, source_sha256=before, driver_sha256=digest(Path(__file__)),
        tool_sha256={str(p): digest(p) for p in (NODE, NPM, RESOLVER)},
        node_version=subprocess.check_output([str(NODE), '--version'], env=env, text=True).strip(),
        npm_version=subprocess.check_output(prefix+['--version'], env=env, text=True).strip(),
        passed=False, whole_stage_deadline=None, steps=[], scope='fresh install/build identity; not release or security approval')
    save(OUTPUT/'start.json', state)
    started = time.monotonic()
    def run(label, args):
        tick = time.monotonic()
        with (OUTPUT/(label+'.log')).open('x') as log:
            process = subprocess.run(prefix+args, cwd=front, env=env, stdout=log, stderr=subprocess.STDOUT)
        state['steps'].append(dict(label=label, argv=prefix+args, actual_returncode=process.returncode,
            seconds=time.monotonic()-tick, log_sha256=digest(OUTPUT/(label+'.log'))))
        assert process.returncode == 0, label+' failed; original log retained'
    try:
        run('install', ['ci', '--no-audit', '--no-fund', '--registry=https://registry.npmjs.org'])
        assert digest(front/'package-lock.json') == before['frontend/package-lock.json']
        run('installed-tree-all', ['ls', '--all', '--json'])
        run('installed-tree-runtime', ['ls', '--omit=dev', '--json'])
        installed = front/'node_modules'
        files = {str(p.relative_to(installed)): digest(p) for p in sorted(installed.rglob('*')) if p.is_file()}
        links = {str(p.relative_to(installed)): os.readlink(p) for p in sorted(installed.rglob('*')) if p.is_symlink()}
        save(OUTPUT/'installed-files-sha256.json', dict(sha256=files, symlinks=links))
        state['installed_file_count'] = len(files)
        state['installed_files_manifest_sha256'] = digest(OUTPUT/'installed-files-sha256.json')
        run('unit', ['run', 'test', '--', '--run'])
        run('lint', ['run', 'lint'])
        hashes = []
        for suffix in ('a', 'b'):
            directory = OUTPUT/('build-'+suffix)
            run('build-'+suffix, ['run', 'build', '--', '--outDir', str(directory)])
            hashes.append({str(p.relative_to(directory)): digest(p) for p in sorted(directory.rglob('*')) if p.is_file()})
        assert hashes[0] and hashes[0] == hashes[1], 'two clean builds produced different UI bytes'
        state['ui_sha256'] = hashes[0]
        state['two_builds_equal'] = True
        assert {n: digest(ROOT/n) for n in before} == before
        state['source_unchanged'] = True
        state['passed'] = True
    except BaseException as error:
        state['error'] = repr(error)
        raise
    finally:
        state['elapsed_seconds'] = time.monotonic()-started
        save(OUTPUT/'result.json', state)
        save(HERE/'frontend-clean-v2-result.json', state)
        # Logs and output resources remain centrally archived; node_modules is
        # independently installed, never copied from the migrated old tree.
        paths = [p for p in OUTPUT.iterdir() if p.is_file()]
        paths += [p for name in ('build-a', 'build-b') for p in (OUTPUT/name).rglob('*') if p.is_file()]
        save(HERE/'frontend-clean-v2-manifest.json', dict(root=str(OUTPUT),
            sha256={str(p.relative_to(OUTPUT)): digest(p) for p in sorted(paths)}))
    print(json.dumps({k: state[k] for k in ('passed', 'node_version', 'npm_version', 'elapsed_seconds')}))


if __name__ == '__main__':
    main()

"""Build only from a fresh archived frontend and its actual lock-installed bytes."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def build_frontend(front, output, data, environment):
    front, output, data = (Path(p).resolve() for p in (front, output, data))
    if (not front.is_relative_to(output) or not output.is_relative_to(data)
            or os.path.lexists(front/'node_modules') or (output/'frontend').exists()):
        raise ValueError('Frontend release build requires a fresh contained source and dependency directory')
    if data.is_relative_to(Path('/data')) and not os.path.ismount('/data'):
        raise ValueError('/data must be mounted')
    node = data/'runtime/node-npm/node_modules/node/bin/node'
    npm = data/'runtime/node-v22.14.0-linux-x64/lib/node_modules/npm/bin/npm-cli.js'
    if not node.is_file():
        node = Path(shutil.which('node') or '/missing-node')
    if not npm.is_file():
        npm = Path(shutil.which('npm') or '/missing-npm').resolve()
    required = json.loads((front/'build-toolchain.json').read_text())
    env = dict(environment, PATH=str(node.parent)+os.pathsep+environment.get('PATH', ''),
        HHU_AVATAR_DATA_ROOT=str(data), NPM_CONFIG_CACHE=str(data/'cache/npm'), TMPDIR=str(data/'tmp'), TZ='UTC')
    for kind in ('user', 'global'):
        config = output/('frontend-npmrc-'+kind)
        config.touch(exist_ok=False)
        env['NPM_CONFIG_'+kind.upper()+'CONFIG'] = str(config)
    resolver = data/'runtime/npm-registry-ipv4.cjs'
    tools = [node, npm]
    if resolver.is_file():
        env['NODE_OPTIONS'] = '--require='+str(resolver)
        tools.append(resolver)
    else:
        env.pop('NODE_OPTIONS', None)
    actual = dict(node=subprocess.check_output([str(node), '--version'], env=env, text=True).strip(),
        npm=subprocess.check_output([str(node), str(npm), '--version'], env=env, text=True).strip())
    if any(actual[k] != required[k] for k in ('node', 'npm')):
        raise ValueError('Release frontend tool versions differ from build-toolchain.json')
    # Include the npm implementation's dependencies, not just its tiny CLI stub.
    npm_root = npm.parent.parent
    tool_hashes = {str(p): digest(p) for p in sorted(npm_root.rglob('*')) if p.is_file()}
    tool_hashes.update({str(p): digest(p) for p in tools})
    write(output/'frontend-toolchain-files.json', tool_hashes)
    before = {str(p.relative_to(front)): digest(p) for p in front.rglob('*') if p.is_file()}
    state = dict(passed=False, tool_versions=actual, toolchain_sha256=digest(output/'frontend-toolchain-files.json'),
        source_sha256=before, lock_sha256=before['package-lock.json'], steps=[], whole_stage_deadline=None)
    started = time.monotonic()
    prefix = [str(node), str(npm), '--prefix', str(front)]
    def run(label, args):
        tick = time.monotonic()
        with (output/(label+'.log')).open('x') as stdout, (output/(label+'.stderr')).open('x') as stderr:
            result = subprocess.run(prefix+args, cwd=front, env=env, stdout=stdout, stderr=stderr)
        state['steps'].append(dict(argv=prefix+args, actual_returncode=result.returncode,
            seconds=time.monotonic()-tick, stdout_sha256=digest(output/(label+'.log')),
            stderr_sha256=digest(output/(label+'.stderr'))))
        if result.returncode:
            raise RuntimeError(label+' failed; original logs retained')
    try:
        run('frontend-ci', ['ci', '--no-audit', '--no-fund', '--registry=https://registry.npmjs.org'])
        run('frontend-tree-all', ['ls', '--all', '--json'])
        run('frontend-tree-runtime', ['ls', '--omit=dev', '--json'])
        modules = front/'node_modules'
        installed = {str(p.relative_to(modules)): digest(p) for p in sorted(modules.rglob('*')) if p.is_file()}
        links = {str(p.relative_to(modules)): os.readlink(p) for p in sorted(modules.rglob('*')) if p.is_symlink()}
        write(output/'frontend-installed-files.json', dict(sha256=installed, symlinks=links))
        state.update(installed_file_count=len(installed),
            installed_manifest_sha256=digest(output/'frontend-installed-files.json'))
        run('frontend-build', ['run', 'build', '--', '--outDir', str(output/'frontend')])
        if ({n: digest(front/n) for n in before} != before
                or {str(p): digest(Path(p)) for p in tool_hashes} != tool_hashes
                or {str(p.relative_to(modules)): digest(p) for p in sorted(modules.rglob('*')) if p.is_file()} != installed
                or {str(p.relative_to(modules)): os.readlink(p) for p in sorted(modules.rglob('*')) if p.is_symlink()} != links):
            raise RuntimeError('Frontend source, toolchain or installed bytes changed during build')
        state.update(passed=True, source_unchanged=True, installed_bytes_unchanged=True,
            toolchain_unchanged=True, ui_sha256={str(p.relative_to(output/'frontend')): digest(p)
                for p in sorted((output/'frontend').rglob('*')) if p.is_file()})
    except BaseException as error:
        state['error'] = repr(error)
        raise
    finally:
        state['elapsed_seconds'] = time.monotonic()-started
        write(output/'frontend-provenance.json', state)
    return state

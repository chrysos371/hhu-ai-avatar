"""Build only from a fresh archived frontend and its actual lock-installed bytes."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def collect_notices(front, target, *, runtime_tree):
    """Preserve available installed texts; inventory includes build dependencies.

    Do not synthesize a license or assert that a package lacking a standalone
    notice file is covered by an unrelated package's text.
    """
    front, target = Path(front).resolve(), Path(target).resolve()
    target.mkdir(parents=True, exist_ok=False)
    lock = json.loads((front/'package-lock.json').read_text())
    packages = []
    for name, entry in sorted(lock['packages'].items()):
        if not name.startswith('node_modules/') or not (front/name/'package.json').is_file():
            continue  # Platform-specific packages absent from this installation.
        folder = (front/name).resolve()
        if not folder.is_relative_to(front/'node_modules'):
            raise ValueError('Notice source escapes installed dependency root')
        metadata = json.loads((folder/'package.json').read_text())
        texts = []
        for item in sorted(folder.iterdir()):
            if not re.match(r'(?i)^(?:licen[cs]es?|copying|notices?)(?:$|[._-])', item.name):
                continue
            for source in sorted(item.rglob('*')) if item.is_dir() else [item]:
                if not source.is_file():
                    continue
                if source.is_symlink() or not source.resolve().is_relative_to(folder):
                    raise ValueError('License text must be a contained regular file')
                relative = Path('licenses')/hashlib.sha256(name.encode()).hexdigest()[:16]/source.relative_to(folder)
                destination = target/relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open('xb') as stream:
                    stream.write(source.read_bytes())
                texts.append(dict(path=str(relative), sha256=digest(source)))
        packages.append(dict(installed_path=name, name=metadata['name'], version=metadata['version'],
            declared_license=metadata.get('license'), development_dependency=bool(entry.get('dev')),
            optional_dependency=bool(entry.get('optional') or entry.get('devOptional')), texts=texts))
    runtime = set()
    def visit(dependencies):
        for name, node in dependencies.items():
            if not isinstance(node.get('version'), str):
                raise ValueError('Runtime dependency has no installed version')
            runtime.add((name, node['version']))
            visit(node.get('dependencies', {}))
    visit(json.loads(Path(runtime_tree).read_text())['dependencies'])
    covered = {(p['name'], p['version']) for p in packages if p['texts']}
    if runtime - covered:
        raise ValueError('Installed runtime dependencies missing original notice text: '+repr(sorted(runtime-covered)))
    write(target/'index.json', dict(version=1,
        scope='Over-inclusive installed frontend build/runtime dependency inventory; not a bundle-usage assertion. '
            'Available original notice/license texts are copied unchanged; absent standalone texts are recorded.',
        package_lock_sha256=digest(front/'package-lock.json'),
        runtime_dependencies=[dict(name=name, version=version) for name, version in sorted(runtime)],
        runtime_original_notice_coverage=True, packages=packages))
    (target/'README.txt').write_text('Third-party frontend notices\n\n'
        'index.json identifies the exact installed frontend dependencies and their declared licenses. '
        'The inventory includes build and development dependencies as well as runtime dependencies. '
        'It does not claim that every listed dependency is present in the JavaScript bundle.\n\n'
        'Original notice/license files supplied by installed packages are preserved byte for byte under licenses/. '
        'An empty texts list means no matching standalone text was found in that package; '
        'no license or copyright attribution has been invented. Python dependencies and external models '
        'are installed separately and retain their own distribution notices.\n', encoding='utf-8')
    return {str(p.relative_to(target)): digest(p) for p in sorted(target.rglob('*')) if p.is_file()}


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
        run('frontend-tree-runtime', ['ls', '--all', '--omit=dev', '--json'])
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

"""Run with the fresh installed-wheel interpreter using -I, outside the checkout."""
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import tarfile
import time
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
import zipfile

import avatar
from avatar.application_assets import frontend_directory
from avatar.brain.memory import MemoryStore

ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
ASSETS = Path('/data/Users/zrh/data/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent
BUILD = ASSETS/'artifacts/release/final-build-v7'
OUT = ASSETS/'artifacts/release/install-smoke-v10'
LEGACY = '349160c2'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def seed_legacy(env):
    raw = subprocess.check_output(['git', 'archive', '--format=tar', LEGACY, '--', 'src'], cwd=ROOT)
    dest = OUT/'legacy-source'
    dest.mkdir()
    hashes = {}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for m in archive:
            if m.isdir():
                continue
            p = dest/m.name
            assert m.isfile() and p.resolve().is_relative_to(dest)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(archive.extractfile(m).read())
            hashes[m.name] = sha(p)
    code = ('import sys,json;sys.path.insert(0,sys.argv[1]);from avatar.brain.memory import MemoryStore;'
        'm=MemoryStore(sys.argv[2]);m.remember_user("名字","发布迁移样本");'
        'm.remember_user("偏好","喜欢看海");print(json.dumps(m.get_user_profile(),ensure_ascii=False));m.close()')
    result = subprocess.run([sys.executable, '-I', '-B', '-c', code, str(dest/'src'), str(OUT/'upgrade.db')],
        cwd=OUT, env=env, text=True, capture_output=True, check=True)
    write(OUT/'legacy-seed.json', dict(source_ref=LEGACY, source_sha256=hashes,
        actual_wait_code=result.returncode, profile=json.loads(result.stdout)))
    with sqlite3.connect(OUT/'upgrade.db') as source, sqlite3.connect(OUT/'before-upgrade-backup.db') as backup:
        source.backup(backup)
    return sha(OUT/'before-upgrade-backup.db')


def request(base, token, path, payload=None):
    req = Request(base+path, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
        headers={'Content-Type': 'application/json', **({'X-Avatar-Token': token} if token else {})})
    try:
        with build_opener(ProxyHandler({})).open(req, timeout=15) as response:
            return response.status, response.read()
    except HTTPError as response:
        return response.code, response.read()


def run_server(env, number):
    command = [str(Path(sys.executable).parent/'hhu-avatar'), 'web', '--port', '0', '--db', str(OUT/'upgrade.db')]
    log_path = OUT/f'server-{number}.log'
    with log_path.open('x') as log:
        child = subprocess.Popen(command, cwd=OUT, env=env, stdin=subprocess.DEVNULL,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            end = time.monotonic()+15
            while time.monotonic() < end:
                assert child.poll() is None, log_path.read_text()
                match = re.search(r'(http://127\.0\.0\.1:\d+)/#([A-Za-z0-9_-]+)', log_path.read_text())
                if match:
                    break
                time.sleep(.05)
            else:
                raise RuntimeError('Installed server readiness timeout')
            base, token = match.groups()
            assert request(base, None, '/api/v1/system')[0] == 403
            status, body = request(base, token, '/api/v1/system')
            assert status == 200 and json.loads(body)['data']['mode'] == 'single-user-local'
            assert b'<html' in request(base, None, '/')[1].lower()
            provenance = json.loads((Path(avatar.__file__).parent/'release-build.json').read_text())
            for name, expected in provenance['ui_sha256'].items():
                path = '/' if name == 'index.html' else '/'+name
                code, data = request(base, None, path)
                assert code == 200 and hashlib.sha256(data).hexdigest() == expected
            payload = dict(request_id='release_install_turn_'+str(number)+'_1234567890', text='我喜欢看海。')
            code, body = request(base, token, '/api/v1/turns', payload)
            assert code == 202
            job = json.loads(body)['data']['job_id']
            code, stream = request(base, token, f'/api/v1/turns/{job}/events')
            assert code == 200 and b'event: result\n' in stream
            records = [json.loads(line[6:]) for line in stream.decode().splitlines() if line.startswith('data: ')]
            final = records[-1]
            assert final['profile_contract']['owner']=='current_user'
            assert final['profile_contract']['action']=='profile_disclosure'
            assert final['capability_contract']['semantic_verifier'] is False
            assert final['reply'] and final['generation_mode'] == final['trace']['decision']['generation_mode'] == 'rules_profile_source'
            assert request(base, token, '/api/v1/turns', payload)[0] == 202
            page = json.loads(request(base, token, '/api/v1/conversation')[1])['data']
            assert len(page['items']) == number*2
            with sqlite3.connect(OUT/'upgrade.db') as conn:
                assert conn.execute('SELECT COUNT(*) FROM memory_role_state').fetchone()[0]==1
            return dict(run=number, installed_console=str(command[0]), http_auth_required=True,
                ui_assets_verified=len(provenance['ui_sha256']), generation_mode=final['generation_mode'],
                conversation_items=len(page['items']), duplicate_did_not_reexecute=True)
        finally:
            if child.poll() is None:
                child.send_signal(signal.SIGINT)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            write(OUT/f'server-{number}-terminal.json', dict(actual_wait_code=child.returncode))
            assert child.returncode == 0


def main():
    assert os.path.ismount('/data') and not OUT.exists()
    assert 'site-packages' in str(Path(avatar.__file__)) and not Path(avatar.__file__).is_relative_to(ROOT)
    assert Path(sys.prefix) == ASSETS/'envs/hhu-ai-avatar-release-final-v6'
    OUT.mkdir(parents=True)
    env = dict(os.environ, LLM_API_KEY='', EMBEDDING_MODEL='', HHU_AVATAR_DATA_ROOT=str(OUT/'runtime'))
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    result = dict(passed=False, driver_sha256=sha(Path(__file__)), installed_avatar=str(Path(avatar.__file__)),
        python_prefix=sys.prefix, version=avatar.__version__, build_source=json.loads((BUILD/'build-result.json').read_text())['source_ref'])
    try:
        for command in ([sys.executable, '-I', '-B', '-m', 'avatar', '--version'],
                [str(Path(sys.executable).parent/'hhu-avatar'), '--version']):
            value = subprocess.check_output(command, cwd=OUT, env=env, text=True).strip()
            assert value == avatar.__version__
        checked = subprocess.run([str(Path(sys.executable).parent/'hhu-avatar'), 'doctor', '--require-ui'],
            cwd=OUT, env=env, text=True, capture_output=True, check=True)
        doctor = json.loads(checked.stdout)
        assert importlib.metadata.version('hhu-ai-avatar')==avatar.__version__==doctor['version']
        assert doctor['core_ready'] and doctor['frontend']['available'] and not doctor['llm']['configured']
        assert doctor['standard_entry_features']==dict(capability_contract_enabled=True,role_state_enabled=True)
        write(OUT/'doctor.json', doctor)
        wheel = next((BUILD/'dist').glob('*.whl'))
        with zipfile.ZipFile(wheel) as archive:
            module_hashes = {}
            for n in archive.namelist():
                if n.startswith('avatar/') and not n.endswith('/'):
                    installed = Path(avatar.__file__).parent.parent/n
                    assert sha(installed) == hashlib.sha256(archive.read(n)).hexdigest()
                    module_hashes[n] = sha(installed)
        backup_sha = seed_legacy(env)
        memory = MemoryStore(str(OUT/'upgrade.db'))
        assert memory.get_user_profile() == {'名字': '发布迁移样本', '偏好': '喜欢看海'}
        memory.close()
        runs = [run_server(env, 1), run_server(env, 2)]
        assert sha(OUT/'before-upgrade-backup.db') == backup_sha
        with sqlite3.connect(OUT/'before-upgrade-backup.db') as source, sqlite3.connect(OUT/'rollback-restored.db') as restored:
            source.backup(restored)
        code = ('import sys,json;sys.path.insert(0,sys.argv[1]);from avatar.brain.memory import MemoryStore;'
            'm=MemoryStore(sys.argv[2]);print(json.dumps(m.get_user_profile(),ensure_ascii=False));m.close()')
        rollback = subprocess.check_output([sys.executable, '-I', '-B', '-c', code,
            str(OUT/'legacy-source/src'), str(OUT/'rollback-restored.db')], cwd=OUT, env=env, text=True)
        assert json.loads(rollback) == {'名字': '发布迁移样本', '偏好': '喜欢看海'}
        subprocess.run([sys.executable, '-I', '-B', '-m', 'pip', 'check'], cwd=OUT, env=env, check=True)
        result.update(passed=True, installed_files_sha256=module_hashes, server_runs=runs,
            legacy_database_migration_preserved_profile=True, backup_sha256=backup_sha,
            rollback_from_backup_with_original_source=True, ui_directory=str(frontend_directory()),
            scope='independent core-dependency installation, original-schema fixture upgrade, two HTTP restarts and backup rollback; no model, physical or multi-day acceptance')
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        write(OUT/'result.json', result)


if __name__ == '__main__':
    main()

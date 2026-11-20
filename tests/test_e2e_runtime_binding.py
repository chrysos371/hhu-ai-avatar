"""Probe fixture imports from npm's real cwd without starting a service."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('inherited', ['src', '/definitely-not-this-project'])
def test_fixture_binds_own_worktree_before_imports(tmp_path,inherited):
    env=dict(os.environ);env['PYTHONPATH']=inherited
    output=tmp_path/'binding.json';env['AVATAR_E2E_RUNTIME_EVIDENCE']=str(output)
    result=subprocess.run([sys.executable,str(ROOT/'tests/helpers/serve_admin_e2e.py'),'--check-project-runtime'],
                          cwd=ROOT/'frontend',env=env,capture_output=True,text=True,check=True,timeout=15)
    data=json.loads(result.stdout)
    assert data==json.loads(output.read_text())
    assert data['project_root']==str(ROOT) and Path(data['frontend_dir'])==(ROOT/'frontend/dist').resolve()
    for name,expected in data['frontend_sha256'].items():
        relative=Path(name).relative_to('frontend/dist')
        assert sha256((Path(data['frontend_dir'])/relative).read_bytes()).hexdigest()==expected
    for name,path in data['module_paths'].items():
        assert Path(path).is_relative_to(ROOT/'src')
        assert sha256(Path(path).read_bytes()).hexdigest()==data['module_sha256'][name]
    again=subprocess.run([sys.executable,str(ROOT/'tests/helpers/serve_admin_e2e.py'),'--check-project-runtime'],
                         cwd=ROOT/'frontend',env=env,capture_output=True,text=True,timeout=15)
    assert again.returncode!=0 and 'FileExistsError' in again.stderr


def test_fixture_records_explicit_packaged_ui_and_its_actual_bytes(tmp_path):
    ui=tmp_path/'packaged-ui';ui.mkdir();(ui/'index.html').write_text('<html>isolated package UI</html>')
    env=dict(os.environ,AVATAR_E2E_FRONTEND_DIR=str(ui));env.pop('AVATAR_E2E_RUNTIME_EVIDENCE',None)
    result=subprocess.run([sys.executable,str(ROOT/'tests/helpers/serve_admin_e2e.py'),'--check-project-runtime'],
        cwd=ROOT/'frontend',env=env,capture_output=True,text=True,check=True,timeout=15)
    data=json.loads(result.stdout)
    assert data['frontend_dir']==str(ui.resolve())
    assert data['frontend_sha256']=={'frontend/dist/index.html':sha256((ui/'index.html').read_bytes()).hexdigest()}
    assert all(Path(p).is_relative_to(ROOT/'src') for p in data['module_paths'].values())

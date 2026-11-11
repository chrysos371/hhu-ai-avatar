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
    assert data['project_root']==str(ROOT) and data['frontend_dir']==str(ROOT/'frontend/dist')
    for name,path in data['module_paths'].items():
        assert Path(path).is_relative_to(ROOT/'src')
        assert sha256(Path(path).read_bytes()).hexdigest()==data['module_sha256'][name]
    again=subprocess.run([sys.executable,str(ROOT/'tests/helpers/serve_admin_e2e.py'),'--check-project-runtime'],
                         cwd=ROOT/'frontend',env=env,capture_output=True,text=True,timeout=15)
    assert again.returncode!=0 and 'FileExistsError' in again.stderr

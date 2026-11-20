"""Distribution identity controls reproduce the actual rc/stable mismatch."""
import importlib.util
import io
from pathlib import Path
import tarfile
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def gate(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    spec=importlib.util.spec_from_file_location('release_metadata_identity_gate',ROOT/'scripts/build_release_candidate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('declared,front,runtime,valid',[
    ('2.0.0','2.0.0','2.0.0',True),
    ('2.0.0rc1','2.0.0','2.0.0',False),
    ('2.0.0','2.0.0-rc.1','2.0.0',False),
    ('2.0.0rc1','2.0.0-rc.1','2.0.0rc1',True),
])
def test_declared_runtime_and_frontend_versions_are_independent_checks(gate,tmp_path,declared,front,runtime,valid):
    (tmp_path/'pyproject.toml').write_text('[project]\nversion="'+declared+'"\n')
    (tmp_path/'frontend').mkdir();(tmp_path/'frontend/package.json').write_text('{"version":"'+front+'"}')
    if valid:gate.validate_source_versions(tmp_path,runtime)
    else:
        with pytest.raises(ValueError,match='Source versions disagree'):gate.validate_source_versions(tmp_path,runtime)


@pytest.mark.parametrize('fault',[None,'filename','wheel_metadata','wheel_runtime','sdist_metadata','sdist_runtime','nested_metadata','duplicate_version'])
def test_each_actual_artifact_identity_is_checked(gate,tmp_path,fault):
    version='2.0.0rc1' if fault=='filename' else '2.0.0'
    wheel=tmp_path/f'hhu_ai_avatar-{version}-py3-none-any.whl'
    sdist=tmp_path/f'hhu_ai_avatar-{version}.tar.gz'
    def metadata(bad=False):return ('Name: hhu-ai-avatar\nVersion: '+('2.0.0rc1' if bad else '2.0.0')+'\n').encode()
    def runtime(bad=False):return ('__version__ = '+repr('2.0.0rc1' if bad else '2.0.0')+'\n').encode()
    with zipfile.ZipFile(wheel,'w') as z:
        meta=metadata(fault=='wheel_metadata')
        if fault=='duplicate_version':meta+=b'Version: 2.0.0\n'
        z.writestr(f'hhu_ai_avatar-{version}.dist-info/METADATA',meta)
        z.writestr('avatar/__init__.py',runtime(fault=='wheel_runtime'))
    with tarfile.open(sdist,'w:gz') as t:
        for name,body in [('PKG-INFO',metadata(fault=='sdist_metadata')),
                ('src/avatar/__init__.py',runtime(fault=='sdist_runtime')),
                ('src/hhu_ai_avatar.egg-info/PKG-INFO',metadata(fault=='nested_metadata'))]:
            info=tarfile.TarInfo(f'hhu_ai_avatar-{version}/'+name);info.size=len(body);t.addfile(info,io.BytesIO(body))
    if fault is None:gate.validate_artifact_versions(wheel,sdist,'2.0.0')
    else:
        with pytest.raises(ValueError):gate.validate_artifact_versions(wheel,sdist,'2.0.0')

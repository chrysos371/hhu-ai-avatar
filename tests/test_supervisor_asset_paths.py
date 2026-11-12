"""Owned data is valid for generated inputs/outputs, never arbitrary code inputs."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts/lab'))
import run_frozen_capability_job as jobs


@pytest.fixture
def roots(tmp_path, monkeypatch):
    code, data = tmp_path / 'repo/project', tmp_path / 'data/project'
    code.mkdir(parents=True)
    data.mkdir(parents=True)
    monkeypatch.setattr(jobs, 'ROOT', code)
    monkeypatch.setattr(jobs, 'project_data_root', lambda root: data)
    return code, data


@pytest.mark.parametrize('role', ['candidate_freeze', 'output'])
def test_generated_paths_can_use_owned_data(roots, role):
    _, data = roots
    assert jobs.experiment_path(role, str(data / 'new.json')) == data / 'new.json'


@pytest.mark.parametrize('role', ['protocol', 'pair_protocol'])
def test_protocols_remain_project_inputs(roots, role):
    code, data = roots
    assert jobs.experiment_path(role, 'evals/spec.json') == code / 'evals/spec.json'
    with pytest.raises(ValueError, match='outside'):
        jobs.experiment_path(role, str(data / 'spec.json'))


@pytest.mark.parametrize('role', ['candidate_freeze', 'output', 'protocol', 'pair_protocol'])
def test_outside_and_traversal_paths_remain_rejected(roots, role):
    code, _ = roots
    with pytest.raises(ValueError, match='outside'):
        jobs.experiment_path(role, '../../unowned/file.json')
    with pytest.raises(ValueError, match='outside'):
        jobs.experiment_path(role, str(code.parent / 'other/file.json'))


def test_symlink_cannot_escape_owned_data(roots, tmp_path):
    code, data = roots
    outside = tmp_path / 'outside'
    outside.mkdir()
    (data / 'escape').symlink_to(outside, target_is_directory=True)
    (code / 'data').symlink_to(data, target_is_directory=True)
    with pytest.raises(ValueError, match='outside'):
        jobs.experiment_path('output', 'data/escape/output')
    assert jobs.experiment_path('output', 'data/owned/output') == data / 'owned/output'


def test_unknown_path_role_is_not_authorized(roots):
    with pytest.raises(ValueError, match='Unknown'):
        jobs.experiment_path('arbitrary-code', 'file')

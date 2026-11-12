from pathlib import Path

import pytest

from avatar.paths import environment_python, project_data_root, runtime_dir, temporary_dir


@pytest.fixture(autouse=True)
def isolated_data_environment(monkeypatch):
    monkeypatch.delenv('HHU_AVATAR_DATA_ROOT', raising=False)


def test_primary_checkout_uses_user_data_not_repo_siblings():
    assert project_data_root('/data/Users/zrh/repo/hhu-ai-avatar') == Path('/data/Users/zrh/data/hhu-ai-avatar')


def test_relocated_worktree_uses_the_same_project_data_root():
    assert project_data_root('/data/Users/zrh/data/hhu-ai-avatar/worktrees/research') == Path('/data/Users/zrh/data/hhu-ai-avatar')


def test_explicit_override_and_children_remain_contained(tmp_path, monkeypatch):
    monkeypatch.setenv('HHU_AVATAR_DATA_ROOT', str(tmp_path / 'assets'))
    assert runtime_dir() == tmp_path / 'assets/runtime'
    assert temporary_dir() == tmp_path / 'assets/tmp'
    assert environment_python() == tmp_path / 'assets/envs/hhu-ai-avatar/bin/python'
    assert environment_python(native=True) == tmp_path / 'assets/envs/hhu-ai-avatar-llm/bin/python'


def test_generic_checkout_uses_xdg_data_home(tmp_path, monkeypatch):
    monkeypatch.setenv('XDG_DATA_HOME', str(tmp_path / 'xdg'))
    assert project_data_root('/opt/checkouts/avatar') == tmp_path / 'xdg/hhu-ai-avatar'


def test_interpreter_path_is_not_resolved_out_of_virtual_environment(tmp_path, monkeypatch):
    monkeypatch.setenv('HHU_AVATAR_DATA_ROOT', str(tmp_path))
    executable = tmp_path / 'envs/hhu-ai-avatar/bin/python'
    executable.parent.mkdir(parents=True)
    executable.symlink_to('/usr/bin/python3')
    assert environment_python() == executable
    assert environment_python().resolve() != environment_python()

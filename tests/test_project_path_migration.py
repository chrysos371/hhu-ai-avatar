from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from resolve_project_path import resolve_recorded_path


def manifest():
    return {'entries': [
        {'source': '/data/Users/zrh/repo/runtime', 'destination': '/data/Users/zrh/data/hhu-ai-avatar/runtime'},
        {'source': '/data/Users/zrh/repo/hhu-ai-avatar-action-receipts', 'destination': '/data/Users/zrh/data/hhu-ai-avatar/worktrees/hhu-ai-avatar-action-receipts'},
    ]}


def test_old_root_alias_and_runtime_child_resolve_to_same_current_path():
    expected = Path('/data/Users/zrh/data/hhu-ai-avatar/runtime/tmp/example.db')
    assert resolve_recorded_path('/root/Users/zrh/repo/runtime/tmp/example.db', manifest()) == expected
    assert resolve_recorded_path('/data/Users/zrh/repo/runtime/tmp/example.db', manifest()) == expected


def test_relocated_worktree_child_is_preserved():
    assert resolve_recorded_path('/data/Users/zrh/repo/hhu-ai-avatar-action-receipts/README.md', manifest()) == Path(
        '/data/Users/zrh/data/hhu-ai-avatar/worktrees/hhu-ai-avatar-action-receipts/README.md')


def test_unrelated_similar_directory_name_is_not_rewritten():
    value = '/data/Users/zrh/repo/runtime-other/file'
    assert resolve_recorded_path(value, manifest()) == Path(value)


def test_independent_project_path_is_not_rewritten():
    value = '/data/Users/zrh/repo/local-qwen-multi-tier/README.md'
    assert resolve_recorded_path(value, manifest()) == Path(value)

"""Project-owned data locations, separate from the source checkout."""
import os
from pathlib import Path


def project_data_root(project_root=None):
    """Return the configured asset root without resolving venv executables."""
    configured = os.environ.get('HHU_AVATAR_DATA_ROOT')
    if configured:
        return Path(configured).expanduser().absolute()
    root = Path(project_root) if project_root is not None else Path(__file__).resolve().parents[2]
    for ancestor in (root, *root.parents):
        if ancestor.name == 'hhu-ai-avatar' and ancestor.parent.name == 'data':
            return ancestor
        if ancestor.name == 'repo':
            return ancestor.parent / 'data/hhu-ai-avatar'
    base = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    return base / 'hhu-ai-avatar'


def runtime_dir():
    return project_data_root() / 'runtime'


def temporary_dir():
    return project_data_root() / 'tmp'


def environment_python(native=False):
    name = 'hhu-ai-avatar-llm' if native else 'hhu-ai-avatar'
    return project_data_root() / 'envs' / name / 'bin/python'

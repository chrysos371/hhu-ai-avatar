"""Load sealed C54 mechanics without invoking their CLI or mutating old sources."""
import importlib.util
from pathlib import Path
import sys

C54=Path(__file__).resolve().parents[1].parent/'cycle-54'
sys.path.append(str(C54/'审计'))


def load(name):
    key='c55_sealed_reference_'+name
    if key not in sys.modules:
        spec=importlib.util.spec_from_file_location(key,C54/'审计'/f'{name}.py')
        module=importlib.util.module_from_spec(spec)
        sys.modules[key]=module
        spec.loader.exec_module(module)
    return sys.modules[key]

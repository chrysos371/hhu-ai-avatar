"""Resolve source-checkout or installed application assets without a cwd dependency."""
from pathlib import Path
import re


def frontend_directory():
    package = Path(__file__).resolve().parent
    bundled = package/'static'
    if (bundled/'index.html').is_file():
        return bundled
    return package.parents[1]/'frontend/dist'


def check_frontend(directory=None):
    root = Path(directory) if directory is not None else frontend_directory()
    root = root.resolve()
    try:
        index = root/'index.html'
        if not index.resolve().is_relative_to(root):
            raise ValueError('index outside application assets')
        html = index.read_text(encoding='utf-8')
        refs = re.findall(r'(?:src|href)=[\"\'](/assets/[^\"\']+)[\"\']', html)
        if '<html' not in html.lower() or not any(r.endswith('.js') for r in refs):
            raise ValueError('missing application HTML or entry script')
        for ref in refs:
            target = (root/ref.lstrip('/')).resolve()
            if not target.is_relative_to(root/'assets') or not target.is_file():
                raise ValueError('missing or external application asset')
        return {'available': True, 'path': str(root), 'entry_assets': len(refs)}
    except (OSError, UnicodeError, ValueError) as error:
        return {'available': False, 'path': str(root), 'error': str(error)}

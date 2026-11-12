"""Create/check ignored checkout links to centrally stored local assets."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar.paths import project_data_root

LINKS = {'data': 'artifacts', 'models': 'models', 'frontend/node_modules': 'frontend/node_modules',
    'frontend/dist': 'frontend/dist', 'frontend/test-results': 'frontend/test-results',
    '.pytest_cache': 'cache/pytest', '.test-tmp': 'tmp/tests',
    '.runtime': 'tmp/legacy-checkout-runtime',
    'src/hhu_ai_avatar.egg-info': 'cache/build-metadata/hhu_ai_avatar.egg-info'}


def check_links(*, create=False):
    data = project_data_root()
    rows = []
    for name, relative in LINKS.items():
        link, target = ROOT / name, data / relative
        if create and not link.is_symlink():
            if link.exists():
                raise ValueError('Refusing to replace a real checkout entry: ' + str(link))
            if not target.is_dir():
                raise ValueError('Data target is missing: ' + str(target))
            link.symlink_to(os.path.relpath(target, link.parent), target_is_directory=True)
        valid = link.is_symlink() and target.is_dir() and link.resolve() == target.resolve()
        rows.append({'checkout_entry': str(link), 'target': str(target), 'valid': valid})
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Read-only verification')
    rows = check_links(create=not parser.parse_args().check)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    if not all(row['valid'] for row in rows):
        raise SystemExit(1)

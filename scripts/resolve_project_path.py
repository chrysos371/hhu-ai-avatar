"""Resolve a historical recorded path without rewriting immutable evidence."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / 'docs/进展报告/2026-11-12-项目数据集中迁移/迁移清单.json'


def resolve_recorded_path(value, manifest=None):
    manifest = json.loads(MANIFEST.read_text()) if manifest is None else manifest
    path = Path(value).expanduser().absolute()
    alias = Path('/root/Users/zrh')
    if path.is_relative_to(alias):
        path = Path('/data/Users/zrh') / path.relative_to(alias)
    for row in sorted(manifest['entries'], key=lambda row: len(row['source']), reverse=True):
        source = Path(row['source'])
        if path.is_relative_to(source):
            return Path(row['destination']) / path.relative_to(source)
    return path


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path')
    args = parser.parse_args()
    print(resolve_recorded_path(args.path))

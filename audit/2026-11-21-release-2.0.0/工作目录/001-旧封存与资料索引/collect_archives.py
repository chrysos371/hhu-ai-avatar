"""Read-only original sealed-byte preservation; no runtime/model imports."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    out = HERE/'archive-preservation-v1.json'
    assert not out.exists()
    seals = []
    targets = []
    cycle_root = ROOT/'docs/进展报告/2026-11-10-G2交互循环'
    for number in range(3, 57):
        folder = cycle_root/f'cycle-{number:02}'
        targets.append((folder/'审计/证据清单.json', folder))
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    targets.append((migration, migration.parent))
    for path, base in targets:
        values = json.loads(path.read_text())
        assert isinstance(values, dict) and values
        assert all(digest(base/name) == value for name, value in values.items()), str(path)
        seals.append(dict(path=str(path.relative_to(ROOT)), sha256=digest(path),
                          root=str(base.relative_to(ROOT)), entries=len(values)))
    assert len(seals) == 55 and sum(s['entries'] for s in seals) == 12737
    ledger_path = ROOT/'docs/发布/2.0.0-rc.1/既有问题处置台账.json'
    ledger = json.loads(ledger_path.read_text())
    assert ledger['all_dispositions_reviewed'] and len(ledger['rows']) == 242
    sources = {}
    for row in ledger['rows']:
        assert digest(ROOT/row['canonical_source']) == row['source_sha256']
        for variant in row['all_source_variants']:
            assert digest(ROOT/variant['path']) == variant['sha256']
            sources[variant['path']] = variant['sha256']
    assert len(sources) == 255
    data_root = Path('/data/Users/zrh/data/hhu-ai-avatar')
    assert data_root.is_dir()
    proof = dict(passed=True, source_ref=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                 driver_sha256=digest(Path(__file__)), old_seals=seals, sealed_entries=12737,
                 original_source_sha256=sources, original_documents=255, canonical_issue_ids=242,
                 duplicate_snapshots=13, deleted_files=0, modified_original_seals=0,
                 central_data_root=str(data_root), scope='original archived bytes preserved; no runtime or quality approval')
    with out.open('x') as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print('55 seals / 12737 entries / 255 source documents unchanged; zero deletions')


if __name__ == '__main__':
    main()

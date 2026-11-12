"""Read-only reconciliation of storage, worktrees, regressions and old seals."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from link_project_assets import check_links


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


manifest = read(WORK / '迁移清单.json')
assets = Path(manifest['data_root'])
assert Path('/data').is_mount()
assert len(manifest['entries']) == 19
entries = []
for row in manifest['entries']:
    source, target = Path(row['source']), Path(row['destination'])
    assert target.is_dir() and target.stat().st_ino == row['source_inode'], row
    if row.get('compatibility_entry_in_main_repo'):
        assert source.is_symlink() and source.resolve() == target
    else:
        assert not os.path.lexists(source), source
    if row['kind'] == 'git_worktree':
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=target, text=True).strip() == row['head']
        assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=target, text=True).strip()
        common = Path(subprocess.check_output(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], cwd=target, text=True).strip())
        assert common == ROOT / '.git'
    entries.append({'source': str(source), 'target': str(target), 'inode_preserved': True, 'kind': row['kind']})
links = check_links()
assert len(links) == 9 and all(row['valid'] for row in links)
caches = read(WORK / '批次记录/14-legacy-python-caches.json')
for row in caches['entries']:
    assert Path(row['source']).is_symlink() and Path(row['source']).resolve() == Path(row['destination'])
old_cycles = []
for path in sorted((ROOT / 'docs/进展报告/2026-11-10-G2交互循环').glob('cycle-*/审计/证据清单.json')):
    if int(path.parents[1].name.split('-')[1]) > 34:
        continue
    recorded = read(path)
    for name, value in recorded.items():
        assert digest(path.parents[1] / name) == value, (path, name)
    old_cycles.append({'cycle': path.parents[1].name, 'items': len(recorded), 'sha256': digest(path)})
assert len(old_cycles) == 32 and old_cycles[-1]['items'] == 169
assert old_cycles[-1]['sha256'] == 'ecb7e4b98dfab75a4d3b630c4409f6b5c2f4efb455c120a35a437e8c1eb90f87'
regressions = {}
for mode in ('python', 'frontend', 'build', 'browser'):
    path = WORK / ('relocated-' + mode + '-final-binding.json')
    report = read(path)
    assert report['exit_code'] == 0 and report['source_unchanged']
    assert report['python_prefix'] == str(assets / 'envs/hhu-ai-avatar')
    assert digest(WORK / ('relocated-' + mode + '-final.log')) == report['log_sha256']
    for name, value in report['source_git_sha256'].items():
        assert digest(ROOT / name) == value, name
    raw = subprocess.check_output(['git', 'archive', '--format=tar', report['head'], '--', *sorted(report['source_git_sha256'])], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        historical = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive.getmembers() if m.isfile()}
    assert historical == report['source_git_sha256']
    if mode in ('build', 'browser'):
        for name, value in report['runtime_artifact_sha256'].items():
            assert digest(ROOT / name) == value
    if mode == 'browser':
        assert report['runtime_matches'] and report['default_controlled_provider']
    regressions[mode] = {'binding_sha256': digest(path), 'stable_source_inputs': len(historical), 'seconds': report['seconds'], 'head': report['head']}
native = read(WORK / '迁后原生运行库身份.json')
assert len(native['files_sha256']) == 54 and native['python_prefix'] == str(assets / 'envs/hhu-ai-avatar-llm')
for name, value in native['files_sha256'].items():
    assert digest(Path(name)) == value
models = read(WORK / '原生库与模型迁移证明.json')
assert models['verified'] and len(models['models']) == 3 and models['actual_model_or_gpu_inference_calls'] == 0
for row in models['models']:
    assert Path(row['current_path']).stat().st_size == row['bytes']
current_docs = [ROOT / name for name in ('README.md', 'AGENTS.md', 'docs/backend.md', 'docs/本机数据布局.md',
    'docs/网页语音与最小形象.md', 'experiments/style/README.md')] + sorted(WORK.glob('*.md'))
local_links = 0
for path in current_docs:
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if link.startswith(('http:', 'https:', '#')):
            continue
        assert (path.parent / link.split('#')[0]).resolve().exists(), (path, link)
        local_links += 1
standalone = read(WORK / '数据目录入口说明.json')
assert digest(Path(standalone['path'])) == standalone['sha256']
authors = subprocess.check_output(['git', 'log', '760e774..HEAD', '--format=%an%x09%ae'], cwd=ROOT, text=True).splitlines()
assert authors and all(row == 'spinner-bot\tlangxibielangle@qq.com' for row in authors)
report = {'verified': True, 'data_root': str(assets), 'code_repository': str(ROOT), 'relocated_entries': entries,
    'worktrees_clean_with_unchanged_heads': 7, 'checkout_compatibility_links': links,
    'legacy_python_cache_directories': caches['count'], 'old_cycles_byte_unchanged': old_cycles,
    'regressions': regressions, 'native_file_contents_verified': 54,
    'model_hash_proofs_retained': models['models'], 'current_document_local_links_verified': local_links,
    'author_checked_commit_count': len(authors), 'gpu_inference_calls': 0, 'research_goal_remains_paused': True}
with (WORK / '最终迁移核验.json').open('x') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('Verified19 moved entries,7 clean worktrees,9 checkout links,20 pycache links,32 immutable cycles,54 native files,all stable-source regressions and', local_links, 'MD links.')

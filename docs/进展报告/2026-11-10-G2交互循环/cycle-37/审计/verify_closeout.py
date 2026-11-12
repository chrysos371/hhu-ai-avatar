"""C37 final link/display/author/seal anchors; current and retired evidence separate."""
import json
import re
import subprocess
from pathlib import Path
from verify_system import ROOT, BASE, WORK, read, digest, history

out = BASE / '审计/收尾核验/final-closeout.json'
assert not out.exists()
proof = read(BASE / '审计/收尾核验/system-evidence.json')
assert proof['verified'] and proof['verifier_sha256'] == digest(BASE / '审计/verify_system.py')
current = read(WORK / 'title-boundary-browser-final-binding.json')['source_git_sha256']
assert len(current) == 431 and all(digest(ROOT / n) == sha for n, sha in current.items())
review = read(BASE / '审计/收尾核验/report-browser.json')
assert review['completed'] and not review['errors'] and len(review['views']) == 2
assert review['reportSha256'] == digest(BASE / '审计/系统审计与推进报告.html')
assert all(v['tableCount'] == 4 and not v['overflow'] and len(v['links']) == 40 for v in review['views'])
assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
meta = read(BASE / '审计/report-render-metadata.json')
assert meta['proof_sha256'] == digest(BASE / '审计/收尾核验/system-evidence.json')
assert meta['builder_sha256'] == digest(BASE / '审计/build_report.py')
assert meta['renderer_sha256'] == digest(BASE / '审计/render_report.py')
paths = [ROOT / 'README.md', ROOT / 'AGENTS.md', ROOT / 'docs/backend.md', BASE.parent / '远期目标与验收路线.md'] + sorted(BASE.rglob('*.md'))
links = []
for p in paths:
    for href in re.findall(r'\]\(([^)]+)\)', p.read_text()):
        if href.startswith(('http:', 'https:', '#')):
            continue
        assert (p.parent / href.split('#')[0]).resolve().is_file(), (p, href)
        links.append({'file': str(p.relative_to(ROOT)), 'href': href})
issues = sorted((BASE / '审计/问题单').glob('*.md'))
assert len(issues) == 7
for p in issues:
    state = p.read_text().splitlines()[2]
    assert ('关闭' in state) if p.stem[:7] in proof['closed_issues'] else ('开放' in state)
for p in paths[:3]:
    assert all(token in p.read_text() for token in ['1911', '192', '17', 'C37'])
authors = subprocess.check_output(['git', 'log', '64274de..HEAD', '--format=%H%x09%an%x09%ae'], cwd=ROOT, text=True).splitlines()
assert authors and all(r.split('\t')[1:] == ['spinner-bot', 'langxibielangle@qq.com'] for r in authors)
old = read(BASE.parent / 'cycle-36/审计/收尾核验/system-evidence.json')['old_cycle_seals']
assert proof['old_cycle_seals'][:-1] == old
assert proof['old_cycle_seals'][-1]['sha256'] == 'f504b2c5772b53c5cc5442d51067264bcc514907c9d83f4dc6a8e97ffda71dd9'
for row in proof['old_cycle_seals']:
    p = BASE.parent / row['cycle'] / '审计/证据清单.json'
    assert digest(p) == row['sha256']
    assert all(digest(p.parents[1] / n) == sha for n, sha in read(p).items())
migration = ROOT / 'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
assert digest(migration) == '717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
assert all(digest(migration.parent / n) == sha for n, sha in read(migration).items())
# Anchor the original completed native archival gate and retirement in committed
# history, rather than trusting only mutually consistent current JSON fields.
archived = [str(p.relative_to(ROOT)) for p in (BASE / '实验').rglob('*') if p.is_file()]
for p in [WORK / 'native-phase-retirement.json', WORK / '4b-three-run-gate.json', WORK / '32b-three-run-engineering-proof.json', WORK / 'fixed_order_repeatability.json']:
    archived.append(str(p.relative_to(ROOT)))
assert history('9511e08', archived) == {p: digest(ROOT / p) for p in archived}
result = {'verified': True, 'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'verifier_sha256': digest(Path(__file__)), 'current_source_count': 431, 'retired_native_archives_git_anchored': len(archived),
    'old_seals_unchanged': 35, 'old_entries_unchanged': 6026, 'local_md_links_count': len(links), 'local_md_links': links,
    'html_views': [v['viewport'] for v in review['views']], 'html_sha256': review['reportSha256'], 'html_links': 40,
    'issue_documents': 7, 'closed_issues': proof['closed_issues'], 'open_issues': proof['open_issues'],
    'required_author_commits': len(authors), 'entry_document_sha256': {str(p.relative_to(ROOT)): digest(p) for p in paths[:4]},
    'goal_remains_active': True, 'next_stage': 'C38 typed capability, source and execution state isolated research',
    'native_calls_completed_before_repair': 264, 'current_native_quality_retest_claim': False}
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print('C37 final closeout passed:', len(links), 'MD links;40HTMLlinks;7issues/4OPEN;35oldseals;431current;1440/390actual')

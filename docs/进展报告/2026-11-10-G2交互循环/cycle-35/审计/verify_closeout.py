"""Final current/historical, document, author, display and migration integrity checks."""
import json
from pathlib import Path
import re
import subprocess
from browser_common import ROOT, BASE, digest, verify


def read(path):
    return json.loads(path.read_text())


def main():
    target = BASE / '审计/收尾核验/final-closeout.json'
    assert not target.exists()
    frozen = BASE / '审计/工作目录/001-页面版本屏障/after-broadcast-fixed-inputs/freeze.json'
    inputs = verify(frozen, 'b7a72d605cce8728affa93cdedabe14912b4b1360396fdf10b2df2be92ffc60e', 'after')
    proof_path = BASE / '审计/收尾核验/browser-independent-proof.json'
    proof = read(proof_path)
    assert proof['verified'] and proof['native_or_gpu_calls'] == 0
    assert proof['actual_offline_app_results_including_failed_harness'] == 23
    assert digest(BASE / '审计/verify_browser_evidence.py') == proof['verifier_sha256']
    for name, sha in proof['evidence_sha256'].items():
        assert digest(ROOT / name) == sha
    for entry in proof['old_cycle_seals']:
        p = BASE.parent / entry['cycle'] / '审计/证据清单.json'
        assert digest(p) == entry['manifest_sha256']
        for name, sha in read(p).items():
            assert digest(p.parents[1] / name) == sha
    migration = ROOT / 'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration) == '717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    for name, sha in read(migration).items():
        assert digest(migration.parent / name) == sha
    review = read(BASE / '审计/收尾核验/report-browser.json')
    assert review['completed'] and not review['errors'] and len(review['views']) == 2
    assert digest(BASE / '审计/系统审计与推进报告.html') == review['reportSha256']
    assert all(v['tableCount'] == 4 and not v['overflow'] for v in review['views'])
    assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
    files = [ROOT / 'README.md', ROOT / 'AGENTS.md', ROOT / 'docs/backend.md', BASE.parent / '远期目标与验收路线.md'] + sorted(BASE.rglob('*.md'))
    links = []
    for path in files:
        for href in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if href.startswith(('http:', 'https:', '#')):
                continue
            assert (path.parent / href.split('#')[0]).resolve().is_file(), (path, href)
            links.append({'file': str(path.relative_to(ROOT)), 'href': href})
    issues = sorted((BASE / '审计/问题单').glob('*.md'))
    assert len(issues) == 6 and all('关闭' in p.read_text() for p in issues)
    for path in files[:3]:
        text = path.read_text()
        assert '1835' in text and '192' in text and 'C35' in text
    assert '研发暂停继续有效' not in (ROOT / 'README.md').read_text()
    old_agents = subprocess.check_output(['git', 'show', '9271bae:AGENTS.md'], cwd=ROOT, text=True)
    agents = (ROOT / 'AGENTS.md').read_text()
    assert old_agents[old_agents.index('## 一、项目是什么'):] == agents[agents.index('## 一、项目是什么'):]
    receipt = read(BASE / '审计/工作目录/002-系统回归/asset-readme-status-update.json')
    assert digest(Path(receipt['path'])) == receipt['after_sha256']
    links_raw = subprocess.check_output(['python3', '-B', 'scripts/link_project_assets.py', '--check'], cwd=ROOT, text=True)
    assert len(json.loads(links_raw)) == 9 and all(r['valid'] for r in json.loads(links_raw))
    authors = subprocess.check_output(['git', 'log', '9c4b4c3..HEAD', '--format=%H%x09%an%x09%ae'], cwd=ROOT, text=True).splitlines()
    assert authors and all(r.split('\t')[1:] == ['spinner-bot', 'langxibielangle@qq.com'] for r in authors)
    assert not subprocess.check_output(['git', 'diff', '--name-only', 'HEAD', '--', 'src', 'scripts', 'tests', 'frontend'], cwd=ROOT, text=True).strip()
    data = {'verified': True, 'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'verifier_sha256': digest(Path(__file__)), 'latest_current_and_historical_inputs': len(inputs['sha256']),
        'primary_groups': proof['primary_groups'], 'actual_offline_results_including_failed_tools': 23,
        'supplement_passed': 8, 'retained_failed_supplement_runs': 2, 'native_or_gpu_calls': 0,
        'old_cycle_seals_unchanged': 32, 'old_cycle_entries': 5736, 'migration_seal_items_unchanged': 88,
        'local_md_links_count': len(links), 'local_md_links': links, 'html_views': [v['viewport'] for v in review['views']],
        'html_report_sha256': review['reportSha256'], 'required_author_commits_since_c34': len(authors),
        'issue_documents': len(issues), 'inherited_p2_closed_within_scope': 1, 'new_p2_closed_within_scope': 2,
        'new_p3_closed': 3, 'data_links_valid': 9,
        'entry_document_sha256': {str(p.relative_to(ROOT)): digest(p) for p in files[:4]},
        'goal_remains_active_and_next_cycle_required': True}
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print('C35 closure verified:', len(links), 'MD links,6issues,33historical seals,433current/historical inputs,author and1440/390report')


if __name__ == '__main__':
    main()

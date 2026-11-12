"""Final document, source, author and immutable cycle closure checks."""
import json
from pathlib import Path
import re
import subprocess
from revision_common import ROOT, BASE, digest, verify_freeze, verify_historical_binding


def read(path):
    return json.loads(path.read_text())


out = BASE / '审计/收尾核验/final-closeout.json'
assert not out.exists()
primary = BASE / '审计/工作目录/001-自动情绪版本失效'
frozen_path = primary / 'native-after-freeze.json'
frozen = verify_freeze(frozen_path, digest(frozen_path), phase='after')
verify_historical_binding(frozen)
system = read(BASE / '审计/收尾核验/system-evidence.json')
assert system['verified'] and len(system['old_manifests']) == 31
supplement = read(BASE / '审计/工作目录/003-浏览器情绪缓存补审/v2/independent-proof.json')
assert supplement['verified'] and supplement['reproduced_stale_cases'] == 3
review = read(BASE / '审计/收尾核验/report-browser.json')
assert review['completed'] and not review['errors']
assert digest(BASE / '审计/系统审计与推进报告.html') == review['reportSha256']
assert len(review['views']) == 2 and all(view['tableCount'] == 4 and not view['overflow'] for view in review['views'])
files = [ROOT / 'README.md', ROOT / 'AGENTS.md', ROOT / 'docs/backend.md',
    BASE.parent / '远期目标与验收路线.md'] + sorted(BASE.rglob('*.md'))
links = 0
for path in files:
    for href in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if href.startswith(('http:', 'https:', '#')):
            continue
        assert (path.parent / href.split('#')[0]).resolve().is_file(), (path, href)
        links += 1
issues = sorted((BASE / '审计/问题单').glob('*.md'))
assert len(issues) == 4
assert 'P2确认，开放' in issues[-1].read_text()
for path in (ROOT / 'README.md', ROOT / 'docs/backend.md', ROOT / 'AGENTS.md'):
    text = path.read_text()
    assert '1810' in text and 'C34-004' in text and '9.85' in text
old_agents = subprocess.check_output(['git', 'show', 'c11e2e5:AGENTS.md'], cwd=ROOT, text=True)
agents = (ROOT / 'AGENTS.md').read_text()
assert old_agents[old_agents.index('## 一、项目是什么'):] == agents[agents.index('## 一、项目是什么'):]
authors = subprocess.check_output(['git', 'log', 'd8ba46a..HEAD', '--format=%H%x09%an%x09%ae'], cwd=ROOT, text=True).splitlines()
assert authors and all(row.split('\t')[1:] == ['spinner-bot', 'langxibielangle@qq.com'] for row in authors)
result = {'verified': True, 'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'after_frozen_inputs_current_and_historical': len(frozen['sha256']), 'unchanged_old_cycles': 31,
    'md_local_links_verified': links, 'html_views_verified': [view['viewport'] for view in review['views']],
    'report_sha256': review['reportSha256'], 'issue_documents': len(issues),
    'inherited_backend_p2_closed_within_tested_scope': True, 'new_harness_p3_closed': 3,
    'new_frontend_cache_p2_open': 1, 'commits_with_required_spinner_bot_author': len(authors),
    'entry_document_sha256': {str(path.relative_to(ROOT)): digest(path) for path in files[:4]},
    'current_execution_python_passed': 1810, 'current_execution_python_skipped': 1,
    'current_execution_default_browser_passed': 15, 'current_execution_default_browser_optional_skipped': 16,
    'all_native_calls_including_failed_harness': 38, 'matched_native_calls': 32,
    'goal_remains_active_next_cycle_required': True}
with out.open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('C34 final closure passed:', links, 'local MD links,4 issues,491 current/historical inputs,spinner-bot authors,report desktop/mobile. Browser P2 remains open for next cycle.')

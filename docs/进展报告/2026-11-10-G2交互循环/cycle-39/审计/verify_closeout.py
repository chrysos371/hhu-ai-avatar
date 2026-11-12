"""C39 final historical anchors, current identity, display, links and authors."""
import json
import re
import subprocess
from pathlib import Path
from verify_system import ROOT, BASE, WORK, REGRESS, BROWSER, read, digest, history

out=BASE/'审计/收尾核验/final-closeout.json'
assert not out.exists()
proof=read(BASE/'审计/收尾核验/system-evidence.json')
assert proof['verified'] and proof['verifier_sha256']==digest(BASE/'审计/verify_system.py')
current=read(REGRESS/'query-final-python-final-binding.json')['source_git_sha256']
assert len(current)==436 and all(digest(ROOT/n)==sha for n,sha in current.items())
review=read(BASE/'审计/收尾核验/report-browser.json')
assert review['completed'] and not review['errors'] and len(review['views'])==2
assert review['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
assert all(v['tableCount']==4 and not v['overflow'] and len(v['links'])==25 for v in review['views'])
assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
meta=read(BASE/'审计/report-render-metadata.json')
for key,p in [('proof_sha256','收尾核验/system-evidence.json'),('builder_sha256','build_report.py'),('renderer_sha256','render_report.py')]:
    assert meta[key]==digest(BASE/'审计'/p)
paths=[ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'docs/backend.md',BASE.parent/'远期目标与验收路线.md']+sorted(BASE.rglob('*.md'))
links=[]
for p in paths:
    for href in re.findall(r'\]\(([^)]+)\)',p.read_text()):
        if href.startswith(('http:','https:','#')):continue
        assert (p.parent/href.split('#')[0]).resolve().is_file(),(p,href)
        links.append({'file':str(p.relative_to(ROOT)),'href':href})
issues=sorted((BASE/'审计/问题单').glob('*.md'))
assert len(issues)==3 and all('关闭' in p.read_text().splitlines()[2] for p in issues)
for p in paths[:3]:
    assert all(token in p.read_text() for token in ['C39','2017','192','436'])
authors=subprocess.check_output(['git','log','9d69f2b7..HEAD','--format=%H%x09%an%x09%ae'],cwd=ROOT,text=True).splitlines()
assert authors and all(r.split('\t')[1:]==['spinner-bot','langxibielangle@qq.com'] for r in authors)
old=read(BASE.parent/'cycle-38/审计/收尾核验/system-evidence.json')['old_cycle_seals']
assert proof['old_cycle_seals'][:-1]==old
assert proof['old_cycle_seals'][-1]['sha256']=='49d9b7cd2661a1c4eb5d5d377753d57f3b48cddca0a0b95c4684163517608aca'
for row in proof['old_cycle_seals']:
    p=BASE.parent/row['cycle']/'审计/证据清单.json'
    assert digest(p)==row['sha256']
    assert all(digest(p.parents[1]/n)==sha for n,sha in read(p).items())
migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
# The failed browser ran before the date-only fixture repair. Verify its actual
# recorded HEAD against that older input set, never against today's corrected test.
failed=read(BROWSER/'first-browser-query-evidence.json')
first=read(REGRESS/'read-query-first-browser_targeted-final-binding.json')['source_git_sha256']
assert history(failed['head'],first)==first
archived=[str(p.relative_to(ROOT)) for directory in [WORK,REGRESS,BROWSER] for p in directory.rglob('*') if p.is_file()]
assert history('fbaac607',archived)=={p:digest(ROOT/p) for p in archived}
red=read(WORK/'query-emotion-red-source.json')
assert red['head'].startswith('5ed88b36')
assert history('71e0771b',red['source_sha256'])==red['source_sha256']
result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'verifier_sha256':digest(Path(__file__)),'current_source_count':436,'archived_evidence_git_anchored':len(archived),
    'old_seals_unchanged':37,'old_entries_unchanged':6454,'local_md_links_count':len(links),'local_md_links':links,
    'html_views':[v['viewport'] for v in review['views']],'html_sha256':review['reportSha256'],'html_links':25,
    'issue_documents':3,'closed_issues':proof['closed_issues'],'general_semantic_issues_still_open':True,
    'required_author_commits':len(authors),'entry_document_sha256':{str(p.relative_to(ROOT)):digest(p) for p in paths[:4]},
    'red_test_actual_head':red['head'],'failed_browser_actual_head':failed['head'],
    'goal_remains_active':True,'next_stage':'C40 trusted local read tool, current source authority and provider support investigation',
    'new_native_or_GPU_calls':0,'general_semantic_or_physical_delivery_approval':False}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('C39 closeout passed:',len(links),'MD links;25HTMLlinks;3scoped closed;37oldseals;436current;1440/390actual')

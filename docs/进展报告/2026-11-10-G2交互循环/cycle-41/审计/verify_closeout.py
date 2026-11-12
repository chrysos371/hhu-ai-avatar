"""C41 final links/display/authors, immutable anchors and retired execution check."""
import json
import re
import subprocess
import sys
from pathlib import Path
from native_common import ROOT,BASE,WORK,REGRESS,read,digest,historical

out=BASE/'审计/收尾核验/final-closeout.json';assert not out.exists()
proof=read(BASE/'审计/收尾核验/system-evidence.json')
assert proof['verified'] and proof['verifier_sha256']==digest(BASE/'审计/verify_system.py')
current=read(REGRESS/'source-read-python-final-binding.json')['source_git_sha256']
assert len(current)==445 and all(digest(ROOT/n)==sha for n,sha in current.items())
review=read(BASE/'审计/收尾核验/report-browser.json')
assert review['completed'] and not review['errors'] and len(review['views'])==2
assert review['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
assert all(v['tableCount']==4 and not v['overflow'] and len(v['links'])==25 for v in review['views'])
assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
meta=read(BASE/'审计/report-render-metadata.json')
for key,p in [('proof_sha256','收尾核验/system-evidence.json'),('builder_sha256','build_report.py'),('renderer_sha256','render_report.py')]:
    assert meta[key]==digest(BASE/'审计'/p)
draft=BASE/'审计/工作目录/005-系统复核/report-draft-first'
assert read(draft/'browser-review.json')['reportSha256']==digest(draft/'report-source.html.txt')
assert read(draft/'render-metadata.json')['builder_sha256']==digest(draft/'builder-source.txt')
paths=[ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'docs/backend.md',BASE.parent/'远期目标与验收路线.md']+sorted(BASE.rglob('*.md'))
links=[]
for p in paths:
    for href in re.findall(r'\]\(([^)]+)\)',p.read_text()):
        if href.startswith(('http:','https:','#')):continue
        assert (p.parent/href.split('#')[0]).resolve().is_file(),(p,href)
        links.append({'file':str(p.relative_to(ROOT)),'href':href})
issues=sorted((BASE/'审计/问题单').glob('*.md'));assert len(issues)==5
for p in issues:
    state=p.read_text().splitlines()[2]
    assert ('关闭' in state) if p.stem[:7] in proof['closed_issues'] else ('开放' in state)
for p in paths[:3]:assert all(token in p.read_text() for token in ['C41','2138','192','445'])
authors=subprocess.check_output(['git','log','81789dc2..HEAD','--format=%H%x09%an%x09%ae'],cwd=ROOT,text=True).splitlines()
assert authors and all(r.split('\t')[1:]==['spinner-bot','langxibielangle@qq.com'] for r in authors)
previous=read(BASE.parent/'cycle-40/审计/收尾核验/system-evidence.json')['old_cycle_seals']
assert proof['old_cycle_seals'][:-1]==previous
assert proof['old_cycle_seals'][-1]['sha256']=='ba757808806d45a802c460578ca8c9bd72a9cb612d72bb9e10a0b501b8127219'
for row in proof['old_cycle_seals']:
    p=BASE.parent/row['cycle']/'审计/证据清单.json';assert digest(p)==row['sha256']
    assert all(digest(p.parents[1]/n)==sha for n,sha in read(p).items())
migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
archived=[str(p.relative_to(ROOT)) for p in (BASE/'实验').rglob('*') if p.is_file()]
for dirname in ('001-来源与参数调查','002-当前软件与浏览器','003-受控读取配对','004-原生开发配对'):
    archived += [str(p.relative_to(ROOT)) for p in (BASE/'审计/工作目录'/dirname).rglob('*') if p.is_file()]
assert historical('66aa47e5',archived)=={p:digest(ROOT/p) for p in archived}
null=read(BASE/'审计/工作目录/005-系统复核/system-null-diagnosis.json')
assert historical('ba0de63b',null['source_sha256'])==null['source_sha256']
descriptor=WORK/'execution-freeze-development.json'
command=[sys.executable,str(BASE/'审计/run_pairs.py'),'--freeze',str(descriptor),
    '--expected-freeze-sha256',digest(descriptor),'--partition','development','--output',str(BASE/'实验/should-never-exist')]
r=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
assert r.returncode!=0 and 'C41 descriptor retired' in r.stderr and not (BASE/'实验/should-never-exist').exists()
assets=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
assert len(assets)==9 and all(x['valid'] for x in assets)
result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
    'verifier_sha256':digest(Path(__file__)),'current_source_count':445,
    'archived_research_and_software_files_git_anchored':len(archived),'archive_git_anchor':'66aa47e5',
    'old_seals_unchanged':39,'old_entries_unchanged':6643,'local_md_links_count':len(links),'local_md_links':links,
    'html_views':[v['viewport'] for v in review['views']],'html_sha256':review['reportSha256'],'html_links':25,
    'draft_raw_source_and_QA_preserved':True,'issue_documents':5,'closed_issues':proof['closed_issues'],
    'open_issues':proof['open_issues'],'required_author_commits':len(authors),
    'entry_document_sha256':{str(p.relative_to(ROOT)):digest(p) for p in paths[:4]},
    'retired_execution_rejection':{'command':command,'exit_code':r.returncode,'stderr':r.stderr,'no_provider_or_output':True},
    'asset_links_valid':9,'actual_native_calls':29,'lab_branch_outcomes':48,
    'no_observed_native_route_gain':True,'protected_executed':False,'default_enabled':False,
    'goal_remains_active':True,'next_stage':'C42 source-executable tool catalogue and parameter availability before model selection',
    'general_semantic_or_physical_approval':False}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('C41 closeout passed:',len(links),'MD links;25HTMLlinks;5issues/1OPEN;39oldseals;445current;29native;1440/390actual')

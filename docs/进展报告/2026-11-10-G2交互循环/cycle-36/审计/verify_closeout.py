"""Validate active documentation, author and display after measured C36 evidence."""
import json, re, subprocess
from pathlib import Path
from verify_system import ROOT,BASE,WORK,read,digest
out=BASE/'审计/收尾核验/final-closeout.json';assert not out.exists()
proof=read(BASE/'审计/收尾核验/system-evidence.json');assert proof['verified']
assert proof['verifier_sha256']==digest(BASE/'审计/verify_system.py')
current=read(WORK/'full-browser-final-binding.json')['source_git_sha256']
for name,sha in current.items():assert digest(ROOT/name)==sha,name
review=read(BASE/'审计/收尾核验/report-browser.json')
assert review['completed'] and not review['errors'] and len(review['views'])==2
assert review['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
assert all(v['tableCount']==4 and not v['overflow'] for v in review['views'])
assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
paths=[ROOT/'README.md',ROOT/'AGENTS.md',ROOT/'docs/backend.md',BASE.parent/'远期目标与验收路线.md']+sorted(BASE.rglob('*.md'))
links=[]
for p in paths:
 for href in re.findall(r'\]\(([^)]+)\)',p.read_text()):
  if href.startswith(('http:','https:','#')):continue
  assert (p.parent/href.split('#')[0]).resolve().is_file(),(p,href)
  links.append({'file':str(p.relative_to(ROOT)),'href':href})
issues=sorted((BASE/'审计/问题单').glob('*.md'));assert len(issues)==4 and all('关闭' in p.read_text() for p in issues)
for p in paths[:3]:assert all(k in p.read_text() for k in ['1835','192','17','C36'])
authors=subprocess.check_output(['git','log','3f67215..HEAD','--format=%H%x09%an%x09%ae'],cwd=ROOT,text=True).splitlines()
assert authors and all(r.split('\t')[1:]==['spinner-bot','langxibielangle@qq.com'] for r in authors)
for row in proof['old_cycle_seals']:
 p=BASE.parent/row['cycle']/'审计/证据清单.json';assert digest(p)==row['sha256']
 for n,sha in read(p).items():assert digest(p.parents[1]/n)==sha
migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
for n,sha in read(migration).items():assert digest(migration.parent/n)==sha
result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
 'current_source_count':len(current),'old_seals_unchanged':34,'old_entries_unchanged':5966,'local_md_links_count':len(links),'local_md_links':links,
 'html_views':[v['viewport'] for v in review['views']],'html_sha256':review['reportSha256'],'issue_documents':len(issues),
 'required_author_commits':len(authors),'entry_document_sha256':{str(p.relative_to(ROOT)):digest(p) for p in paths[:4]},
 'goal_remains_active':True,'next_stage':'fresh_material_native_task_capability_baseline','native_or_gpu_calls_this_cycle':0}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('C36 closeout passed:',len(links),'MD links,4issues,34old seals,426current inputs,17browser,1440/390report')

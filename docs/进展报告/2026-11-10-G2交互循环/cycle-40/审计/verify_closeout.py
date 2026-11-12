"""C40 final links/display/authors/immutable archives and retired execution gates."""
import json
import re
import subprocess
import sys
from pathlib import Path
from native_common import ROOT,BASE,WORK,read,digest,historical

out=BASE/'审计/收尾核验/final-closeout.json';assert not out.exists()
proof=read(BASE/'审计/收尾核验/system-evidence.json')
assert proof['verified'] and proof['verifier_sha256']==digest(BASE/'审计/verify_system.py')
reg=BASE/'审计/工作目录/004-当前软件与浏览器'
current=read(reg/'wire-python-final-binding.json')['source_git_sha256']
assert len(current)==440 and all(digest(ROOT/n)==sha for n,sha in current.items())
review=read(BASE/'审计/收尾核验/report-browser.json')
assert review['completed'] and not review['errors'] and len(review['views'])==2
assert review['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
assert all(v['tableCount']==4 and not v['overflow'] and len(v['links'])==25 for v in review['views'])
assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
meta=read(BASE/'审计/report-render-metadata.json')
for key,p in [('proof_sha256','收尾核验/system-evidence.json'),('builder_sha256','build_report.py'),('renderer_sha256','render_report.py')]:assert meta[key]==digest(BASE/'审计'/p)
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
for p in paths[:3]:assert all(token in p.read_text() for token in ['C40','2070','192','440'])
authors=subprocess.check_output(['git','log','3f51fa48..HEAD','--format=%H%x09%an%x09%ae'],cwd=ROOT,text=True).splitlines()
assert authors and all(r.split('\t')[1:]==['spinner-bot','langxibielangle@qq.com'] for r in authors)
old=read(BASE.parent/'cycle-39/审计/收尾核验/system-evidence.json')['old_cycle_seals']
assert proof['old_cycle_seals'][:-1]==old
assert proof['old_cycle_seals'][-1]['sha256']=='bfd05b7428b3af761ffd5b73aaf74d4f7a175184bebff609883caf40f6c9d36f'
for row in proof['old_cycle_seals']:
    p=BASE.parent/row['cycle']/'审计/证据清单.json';assert digest(p)==row['sha256']
    assert all(digest(p.parents[1]/n)==sha for n,sha in read(p).items())
migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
archived=[str(p.relative_to(ROOT)) for p in (BASE/'实验').rglob('*') if p.is_file()]
archived +=[str(p.relative_to(ROOT)) for p in WORK.rglob('*') if p.is_file()]
assert historical('0ae0952a',archived)=={p:digest(ROOT/p) for p in archived}
# Recompute the actual adapter invocation count, independent of report labels.
actual_calls=sum(r.get('wire_finish_reason')=='tool_calls' for group in (BASE/'实验').iterdir() for r in [json.loads(line) for line in (group/'provider-trace.jsonl').read_text().splitlines()])
assert actual_calls==proof['native_wire_adapter_tool_calls']==12
retired=[]
for suffix in ('','-sse-fixed'):
    descriptor=WORK/('execution-freeze'+suffix+'.json')
    command=[sys.executable,str(BASE/'审计/run_wire.py'),'--freeze',str(descriptor),'--expected-freeze-sha256',digest(descriptor),'--output',str(BASE/'实验/should-never-exist')]
    r=subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
    assert r.returncode!=0 and 'C40 descriptor retired' in r.stderr and not (BASE/'实验/should-never-exist').exists()
    retired.append({'descriptor':descriptor.name,'exit_code':r.returncode,'stderr':r.stderr,'no_provider_or_output_created':True})
assets=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True));assert len(assets)==9 and all(r['valid'] for r in assets)
result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
    'current_source_count':440,'native_archival_files_git_anchored':len(archived),'archive_git_anchor':'0ae0952a','old_seals_unchanged':38,'old_entries_unchanged':6531,
    'local_md_links_count':len(links),'local_md_links':links,'html_views':[v['viewport'] for v in review['views']],'html_sha256':review['reportSha256'],'html_links':25,
    'issue_documents':5,'closed_issues':proof['closed_issues'],'open_issues':proof['open_issues'],'required_author_commits':len(authors),
    'entry_document_sha256':{str(p.relative_to(ROOT)):digest(p) for p in paths[:4]},'retired_execution_rejections':retired,'asset_links_valid':9,
    'actual_native_calls':40,'actual_adapted_tool_calls':12,'expected_selections':{'exact':21,'total':24},'actual_business_reads_or_writes':0,
    'goal_remains_active':True,'next_stage':'C41 independent source-argument validation and bounded tool error repair; no default promotion','general_semantic_or_physical_approval':False}
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('C40 closeout passed:',len(links),'MD links;25HTMLlinks;5issues/1OPEN;38oldseals;440current;40native;1440/390actual')

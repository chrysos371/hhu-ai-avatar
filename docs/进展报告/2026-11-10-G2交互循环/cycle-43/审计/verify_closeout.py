"""Final current-source, report/link, author and immutable-history review."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from native_common import ROOT,BASE,WORK,REGRESS,read,digest,historical


def main():
    output=BASE/'审计/收尾核验/closeout.json';assert not output.exists()
    source=read(REGRESS/'policy-evidence-python-final-binding.json')['source_git_sha256']
    assert len(source)==455 and all(digest(ROOT/n)==sha for n,sha in source.items())
    assert historical(read(REGRESS/'policy-evidence-python-final-binding.json')['head'],source)==source
    frozen=read(WORK/'development-freeze.json')
    assert len(frozen['sha256'])==576 and historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
    assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
    assert read(WORK/'development-freeze-retirement.json')['verification_sha256']==digest(WORK/'development-verification.json')
    system=read(BASE/'审计/收尾核验/system-evidence.json');assert system['verified']
    assert system['verifier_sha256']==digest(BASE/'审计/verify_system.py')
    meta=read(BASE/'审计/report-render-metadata.json')
    assert meta['system_sha256']==digest(BASE/'审计/收尾核验/system-evidence.json')
    assert meta['builder_sha256']==digest(BASE/'审计/build_report.py') and meta['renderer_sha256']==digest(BASE/'审计/render_report.py')
    review=read(BASE/'审计/收尾核验/report-browser.json')
    assert review['completed'] and review['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
    assert [v['viewport']['width'] for v in review['views']]==[1440,390]
    assert meta['tables']==4 and meta['links']==23
    assert all(v['tableCount']==4 and not v['overflow'] and len(v['links'])==23 for v in review['views'])
    assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
    links=[]
    paths=list(BASE.rglob('*.md'))+[ROOT/'AGENTS.md',ROOT/'README.md',ROOT/'docs/backend.md',BASE.parent/'远期目标与验收路线.md']
    for path in paths:
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            target=raw.split('#',1)[0].strip('<>')
            if not target or re.match(r'[a-z]+://',target):continue
            local=(path.parent/unquote(target)).resolve()
            assert local.exists(),(str(path),raw)
            links.append({'source':str(path.relative_to(ROOT)),'target':raw})
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names={str(p.relative_to(ROOT)):module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not found for found in names.values()),names
    seals=[]
    for number in range(3,43):
        cycle=BASE.parent/f'cycle-{number:02}';p=cycle/'审计/证据清单.json'
        assert all(digest(cycle/n)==sha for n,sha in read(p).items())
        seals.append({'cycle':cycle.name,'items':len(read(p)),'sha256':digest(p)})
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
    assert sum(s['items'] for s in seals)+len(read(migration))==7289
    authors=subprocess.check_output(['git','log','9cc33087..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines()
    assert authors and set(authors)=={'spinner-bot <langxibielangle@qq.com>'}
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(__file__),'current_software_inputs':455,'retired_native_inputs':576,
        'local_markdown_links_verified':len(links),'links':links,'HTML_links_per_viewport':23,'HTML_tables':4,
        'viewports':[1440,390],'old_seals_including_migration':41,'old_items':7289,
        'cycle_commits_checked':len(authors),'all_authors_spinner_bot':True,'undefined_globals':names,
        'primary_gate_passed':False,'protected_executed':False,'default_enabled':False,
        'additional_native_calls':0,'HTML_sha256':review['reportSha256']}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C43 closeout:',len(links),'local MD links;23HTML;1440/390;455 current/576 archived;41 old7289;spinner authors')


if __name__=='__main__':main()

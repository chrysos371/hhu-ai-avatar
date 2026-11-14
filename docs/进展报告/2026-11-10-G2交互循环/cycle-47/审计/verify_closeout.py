"""Check C47 report, current source, documentation links and commit authors."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from native_common import ROOT, BASE, WORK, REGRESS, read, digest, historical


def main():
    output = BASE/'审计/收尾核验/closeout.json'; assert not output.exists()
    source = read(REGRESS/'native-history-v2-python-final-binding.json')['source_git_sha256']
    assert len(source) == 479 and all(digest(ROOT/n) == sha for n,sha in source.items())
    system_path = BASE/'审计/收尾核验/system-evidence.json'; system = read(system_path)
    assert system['verified'] and system['source_sha256'] == source
    assert system['verifier_sha256'] == digest(BASE/'审计/verify_system.py')
    assert system['native_calls'] == 196 and system['native_unique_SQL_dumps'] == 192
    assert system['CPU_unique_SQL_dumps'] == 44
    assert not any(m['primary_gate_passed'] for m in system['models'])
    for short in ('4b','14b'):
        frozen = read(WORK/(short+'-freeze-v2.json'))
        assert historical(frozen['source_ref'],frozen['sha256']) == frozen['sha256']
        assert all(digest(ROOT/n) == sha for n,sha in frozen['sha256'].items())
        assert read(WORK/(short+'-freeze-v2-retirement.json'))['retired']
        assert read(WORK/(short+'-retirement-verification.json'))['additional_native_calls'] == 0
    meta = read(BASE/'审计/report-render-metadata.json')
    assert meta['system_sha256'] == digest(system_path)
    assert meta['builder_sha256'] == digest(BASE/'审计/build_report.py')
    assert meta['renderer_sha256'] == digest(BASE/'审计/render_report.py')
    review = read(BASE/'审计/收尾核验/report-browser.json')
    assert review['completed'] and not review['errors']
    assert review['reportSha256'] == digest(BASE/'审计/系统审计与推进报告.html')
    assert [v['viewport']['width'] for v in review['views']] == [1440,390]
    assert meta['tables'] == 4 and meta['links'] == 24
    assert all(v['tableCount'] == 4 and not v['overflow'] and len(v['links']) == 24 for v in review['views'])
    assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
    links = []
    maintained = [ROOT/'AGENTS.md',ROOT/'README.md',ROOT/'docs/backend.md',
        ROOT/'docs/记忆工作台与提醒.md',ROOT/'docs/本机数据布局.md',BASE.parent/'远期目标与验收路线.md']
    archived_plan = BASE/'审计/工作目录/001-实模方案调查/plan-v1.md'
    assert digest(archived_plan) == read(WORK/'4b-freeze-v2.json')['sha256'][str(archived_plan.relative_to(ROOT))]
    for path in sorted(BASE.rglob('*.md'))+maintained:
        reference_base = BASE if path == archived_plan else path.parent
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            target = raw.split('#',1)[0].strip('<>')
            if not target or re.match(r'[a-z]+://',target): continue
            assert (reference_base/unquote(target)).resolve().exists(),(str(path),raw)
            links.append({'source':str(path.relative_to(ROOT)),'target':raw,
                'reference_base':str(reference_base.relative_to(ROOT)),
                'original_location_for_byte_archive':path == archived_plan})
    first = read(BASE/'审计/工作目录/005-归档文档引用语境/first-report-archive.json')
    archive = BASE/'审计/工作目录/005-归档文档引用语境'
    assert all(digest(archive/row['archive_name']) == row['sha256'] for row in first['files'])
    first_review = read(archive/'first-report-browser.json.txt')
    assert first_review['reportSha256'] == digest(archive/'first-report.html.txt')
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not missing for missing in names.values()),names
    old_items = 0
    for number in range(3,47):
        cycle = BASE.parent/f'cycle-{number:02}'; path = cycle/'审计/证据清单.json'; data = read(path)
        assert all(digest(cycle/n) == sha for n,sha in data.items()); old_items += len(data)
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'; data = read(migration)
    assert all(digest(migration.parent/n) == sha for n,sha in data.items()); old_items += len(data)
    assert old_items == 8565
    authors = subprocess.check_output(['git','log','674fddbd..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines()
    assert authors and set(authors) == {'spinner-bot <langxibielangle@qq.com>'}
    result = {'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'current_software_inputs':479,
        'system_sha256':digest(system_path),'native_calls_in_cycle':196,'additional_native_calls':0,
        'native_SQL_dumps':192,'CPU_SQL_dumps':44,'both_semantic_gates_failed':True,
        'local_markdown_links_verified':len(links),'links':links,'HTML_links_per_viewport':24,
        'HTML_tables':4,'viewports':[1440,390],'HTML_sha256':review['reportSha256'],
        'old_seals_including_migration':45,'old_items':old_items,
        'cycle_commits_checked':len(authors),'all_authors_spinner_bot':True,'undefined_globals':names,
        'maintained_docs_sha256':{str(p.relative_to(ROOT)):digest(p) for p in maintained},
        'issues_limited_closed':2,'issues_open':3,'original_archive_reference_context_checked':True,
        'first_report_preserved':True,'general_semantic_or_default_model_approval':False}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C47 closeout:',len(links),'MD links;24 HTML links;1440/390;479 source;45 old seals/8565 items;spinner authors')


if __name__ == '__main__':
    main()

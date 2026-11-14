"""Final C49 source, report/link, authorship and old-seal review, no inference."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from native_common import ROOT,BASE,WORK,REGRESS,read,digest,historical


def main():
    output = BASE/'审计/收尾核验/closeout.json'; assert not output.exists()
    source = read(REGRESS/'minimal-history-v1-python-final-binding.json')['source_git_sha256']
    assert len(source) == 489 and all(digest(ROOT/n) == sha for n,sha in source.items())
    system_path = BASE/'审计/收尾核验/system-evidence.json'; system = read(system_path)
    assert system['verified'] and system['source_sha256'] == source
    assert system['verifier_sha256'] == digest(BASE/'审计/verify_system.py')
    assert system['native_calls'] == 652 and system['native_unique_SQL_dumps'] == 756
    assert system['CPU_unique_SQL_dumps'] == 136 and system['candidate_rejected_for_default_activation']
    assert system['issues_open'] == 3 and system['issues_limited_closed'] == 2
    for model in system['models']:
        assert model['primary_gate_passed'] is False
        for stats in model['arms'].values():
            assert stats['JSON_objects_for_literal_claims'] == 54 and stats['not_JSON_objects_for_literal_claims'] == 0
            assert stats['literal_true_claims']['human_reading_verified'] == stats['literal_true_claims']['human_task_completion_verified'] == 0
    for short in ('4b','14b'):
        frozen = read(WORK/(short+'-freeze-v1.json'))
        assert historical(frozen['source_ref'],frozen['sha256']) == frozen['sha256']
        assert all(digest(ROOT/n) == sha for n,sha in frozen['sha256'].items())
        assert read(WORK/(short+'-freeze-v1-retirement.json'))['retired']
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
    assert all(v['tableCount'] == 4 and not v['overflow'] and len(v['links']) == meta['links'] for v in review['views'])
    assert all(t['lastCellReadable'] for v in review['views'] for t in v['horizontalTables'])
    contract_path = BASE/'审计/工作目录/005-最小来源契约/source-contract.json'; contract = read(contract_path)
    assert digest(contract_path) == system['source_contract_sha256']
    assert contract['verified'] and contract['probe_sha256'] == digest(BASE/'审计/probe_minimal_source_contract.py')
    assert contract['new_native_calls'] == contract['new_SDK_turns'] == contract['new_SQL_dumps'] == 0
    assert contract['sampled_minimal_query_frames_without_unbound_claim_or_query_proves_fields'] == 144
    first = read(BASE/'审计/工作目录/006-汇总计数核验/system-evidence-first.json')
    assert first['native_calls'] == system['native_calls'] == 652
    assert [m['native_calls'] for m in first['models']] == [146,146]
    for before,model in zip(first['models'],system['models']):
        proof = read(WORK/(model['model']+'-verification.json'))
        evaluation = read(BASE/'实验'/(model['model']+'-development-v1')/'evaluation.json')
        assert type(model['native_calls']) is int
        assert model['native_calls'] == proof['native_calls'] == evaluation['actual_native_calls'] == 326
        assert {k:v for k,v in before.items() if k!='native_calls'} == {k:v for k,v in model.items() if k!='native_calls'}
    assert sum(m['native_calls'] for m in system['models']) == system['native_calls']
    fixed = read(BASE/'审计/工作目录/001-材料与来源调查/registered-oracle-fixed.json')
    assert fixed['current_verifier_sha256'] == digest(BASE/'审计/verify_native.py')
    assert fixed['probe_sha256'] == digest(BASE/'审计/probe_registered_order_gate.py')
    maintained = [ROOT/'AGENTS.md',ROOT/'README.md',ROOT/'docs/backend.md',ROOT/'docs/记忆工作台与提醒.md',
        ROOT/'docs/本机数据布局.md',BASE.parent/'远期目标与验收路线.md']
    links = []
    for path in sorted(BASE.rglob('*.md'))+maintained:
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            target = raw.split('#',1)[0].strip('<>')
            if not target or re.match(r'[a-z]+://',target): continue
            assert (path.parent/unquote(target)).resolve().exists(),(str(path),raw)
            links.append({'source':str(path.relative_to(ROOT)),'target':raw})
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not missing for missing in names.values()),names
    old_items = 0
    for number in range(3,49):
        cycle = BASE.parent/f'cycle-{number:02}'; path = cycle/'审计/证据清单.json'; data = read(path)
        assert all(digest(cycle/n) == sha for n,sha in data.items()); old_items += len(data)
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'; data = read(migration)
    assert all(digest(migration.parent/n) == sha for n,sha in data.items()); old_items += len(data)
    assert old_items == 9740
    authors = subprocess.check_output(['git','log','8458f7ae..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines()
    assert authors and set(authors) == {'spinner-bot <langxibielangle@qq.com>'}
    result = {'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'current_software_inputs':489,'system_sha256':digest(system_path),
        'native_calls_in_cycle':652,'additional_native_calls':0,'native_SQL_dumps':756,'CPU_SQL_dumps':136,
        'both_semantic_gates_failed':True,'local_markdown_links_verified':len(links),'links':links,
        'HTML_links_per_viewport':meta['links'],'HTML_tables':4,'viewports':[1440,390],
        'HTML_sha256':review['reportSha256'],'old_seals_including_migration':47,'old_items':old_items,
        'cycle_commits_checked':len(authors),'all_authors_spinner_bot':True,'undefined_globals':names,
        'maintained_docs_sha256':{str(p.relative_to(ROOT)):digest(p) for p in maintained},
        'issues_open':3,'issues_limited_closed':2,'candidate_default_activation_rejected':True,'general_semantic_approval':False}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C49 closeout:',len(links),'MD links;24 HTML;1440/390;489 source;47 old/9740;spinner authors;candidate rejected')


if __name__ == '__main__': main()

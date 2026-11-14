"""Final report/source/link/author checks; no model calls or semantic auto-grading."""
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

from native_common import ROOT,BASE,WORK,read,digest,historical
from source_identity import snapshot


def main():
    output=BASE/'审计/收尾核验/closeout.json';assert not output.exists()
    system_path=BASE/'审计/收尾核验/system-evidence.json';system=read(system_path)
    assert system['verified'] and system['verifier_sha256']==digest(BASE/'审计/verify_system.py')
    assert snapshot()==system['source_sha256'] and len(snapshot())==492
    assert system['native_calls']==436 and system['native_SQL_dumps']==468 and system['CPU_SQL_dumps']==88
    assert system['annotation_rows']==216 and len(system['annotation_provenance_faults_rejected'])==5
    assert all(digest(ROOT/n)==sha for n,sha in system['annotations_sha256'].items())
    assert system['issues_limited_closed']==1 and system['issues_open']==4  # Snapshot predates report issue006.
    assert system['default_activation_authorized'] is False
    assert [m['native_calls'] for m in system['models']]==[218,218]
    assert sum(m['native_calls'] for m in system['models'])==system['native_calls']
    observed={}
    for model in system['models']:
        short=model['model'];frozen=read(WORK/(short+'-freeze-v1.json'))
        assert historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
        assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
        assert read(WORK/(short+'-freeze-v1-retirement.json'))['retired']
        assert read(WORK/(short+'-retirement-verification.json'))['additional_native_calls']==0
        assert model['local_zero_unsupported_send_criterion_met_by_agent_review'] is False
        observed[short]=[model['arms'][a]['observed_flags'].get('unsupported_actual_external_claim',0)
            for a in ('production_snapshot','C48_typed_control','minimal_observation')]
        assert all(a['replies']==36 and a['preserved']==6 for a in model['arms'].values())
    assert observed=={'4b':[5,3,6],'14b':[0,0,6]}
    meta=read(BASE/'审计/report-render-metadata.json');browser=read(BASE/'审计/收尾核验/report-browser.json')
    assert meta['system_sha256']==digest(system_path)
    assert meta['builder_sha256']==digest(BASE/'审计/build_report.py')
    assert meta['renderer_sha256']==digest(BASE/'审计/render_report.py')
    assert meta['tables']==4 and meta['links']==22
    assert browser['completed'] and not browser['errors']
    assert browser['reportSha256']==digest(BASE/'审计/系统审计与推进报告.html')
    assert [v['viewport']['width'] for v in browser['views']]==[1440,390]
    assert all(v['tableCount']==4 and not v['overflow'] and len(v['links'])==22 for v in browser['views'])
    assert all(t['lastCellReadable'] for v in browser['views'] for t in v['horizontalTables'])
    issue006=BASE/'审计/问题单/006-报告目录链接被文件校验拒绝.md'
    assert 'CPU报告流程限定关闭' in issue006.read_text()
    assert (BASE/'审计/工作目录/006-报告链接核验/build-report-first.py.txt').is_file()
    assert len(list((BASE/'审计/问题单').glob('*.md')))==6
    maintained=[ROOT/'AGENTS.md',ROOT/'README.md',ROOT/'docs/backend.md',ROOT/'docs/记忆工作台与提醒.md',
        ROOT/'docs/本机数据布局.md',BASE.parent/'远期目标与验收路线.md']
    links=[]
    for path in sorted(BASE.rglob('*.md'))+maintained:
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            target=raw.split('#',1)[0].strip('<>')
            if not target or re.match(r'[a-z]+://',target):continue
            assert (path.parent/unquote(target)).resolve().exists(),(str(path),raw)
            links.append({'source':str(path.relative_to(ROOT)),'target':raw})
    checker=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec=importlib.util.spec_from_file_location('pure_names',checker);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    names={p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not n for n in names.values()),names
    old_items=0
    for number in range(3,50):
        cycle=BASE.parent/f'cycle-{number:02}';seal=read(cycle/'审计/证据清单.json')
        assert all(digest(cycle/n)==sha for n,sha in seal.items());old_items+=len(seal)
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json';seal=read(migration)
    assert all(digest(migration.parent/n)==sha for n,sha in seal.items());old_items+=len(seal);assert old_items==11143
    authors=subprocess.check_output(['git','log','e2bd8703..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines()
    assert authors and set(authors)=={'spinner-bot <langxibielangle@qq.com>'}
    result={'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'system_sha256':digest(system_path),
        'software_inputs_reused_unchanged':489,'registered_plus_software_inputs':492,'native_calls':436,
        'native_SQL_dumps':468,'CPU_SQL_dumps':88,'agent_review_rows':216,'new_native_calls':0,
        'HTML_tables':4,'HTML_links':22,'viewports':[1440,390],'HTML_sha256':browser['reportSha256'],
        'MD_links_verified':len(links),'links':links,'old_seals_including_migration':48,'old_items':old_items,
        'cycle_commits_checked':len(authors),'all_authors_spinner_bot':True,
        'maintained_docs_sha256':{str(p.relative_to(ROOT)):digest(p) for p in maintained},
        'system_snapshot_issues_limited_closed':1,'post_system_issue006_limited_closed':True,
        'final_issues_limited_closed':2,'final_issues_open':4,'undefined_globals':names,
        'source_span_validation_is_not_independent_semantic_review':True,'default_activation_authorized':False,
        'general_semantic_or_generative_leap_approval':False}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C50 closeout:',len(links),'MD;22HTML/4tables/1440/390;436native;216 agent reviews;48old/11143;2closed/4open;spinner authors')


if __name__=='__main__':main()

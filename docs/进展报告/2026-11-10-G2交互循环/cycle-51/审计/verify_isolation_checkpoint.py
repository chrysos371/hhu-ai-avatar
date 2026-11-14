"""Verify the scoped data-isolation repair and full Python evidence, CPU only."""
import json
from pathlib import Path
import re
import subprocess

from run_python_regression import ROOT,BASE,snapshot,digest


def main():
    work=BASE/'审计/工作目录/001-训练条件与入口';out=work/'isolation-checkpoint.json';assert not out.exists()
    first=read(work/'readiness-first.json');red=read(work/'isolation-red.json');fixed=read(work/'isolation-fixed.json')
    archived=work/'data-before-history-protection.py.txt'
    assert digest(archived)==first['source_sha256']['src/avatar/lab/data.py']==red['screening_code_sha256']
    assert fixed['screening_code_sha256']==digest(ROOT/'src/avatar/lab/data.py')
    assert red['probe_sha256']==fixed['probe_sha256']==digest(BASE/'审计/probe_history_isolation.py')
    assert red['verified'] and red['expected_behavior']=='red' and red['actual_C50_case']['accepted']
    assert fixed['verified'] and fixed['expected_behavior']=='fixed' and not fixed['actual_C50_case']['accepted']
    assert fixed['actual_C50_case']['input']==red['actual_C50_case']['input']
    assert 'eval_overlap' in fixed['actual_C50_case']['reasons']
    assert all(row['protected_hash'] and row['input_occurrences']==row['included_occurrences'] for row in fixed['coverage'])
    assert len(fixed['fixed_all_100_input_occurrence_screening'])==100
    assert all(not row['accepted'] and 'eval_overlap' in row['reasons'] for row in fixed['fixed_all_100_input_occurrence_screening'])
    assert fixed['unrelated_preservation']['accepted'] and not fixed['legacy_protection']['accepted']
    proof_path=BASE/'审计/工作目录/002-当前软件回归/python-first-binding.json';proof=read(proof_path)
    log=proof_path.with_name('python-first.log');assert proof['exit_code']==0 and proof['source_unchanged']
    assert proof['source_git_sha256']==snapshot() and proof['source_inputs']==len(snapshot())==493
    assert proof['driver_sha256']==digest(BASE/'审计/run_python_regression.py') and proof['log_sha256']==digest(log)
    assert '2540 passed, 1 skipped' in log.read_text()
    assert '36 passed, 1 skipped' in (work/'training-targeted-first.log').read_text()
    previous=read(BASE.parent/'cycle-50/审计/收尾核验/system-evidence.json')['source_sha256']
    changes={n for n,sha in snapshot().items() if previous.get(n)!=sha}
    assert changes=={'src/avatar/lab/data.py','tests/test_history_training_isolation.py'}
    old_items=0
    for number in range(3,51):
        cycle=BASE.parent/f'cycle-{number:02}';seal=read(cycle/'审计/证据清单.json')
        assert all(digest(cycle/n)==sha for n,sha in seal.items());old_items+=len(seal)
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json';seal=read(migration)
    assert all(digest(migration.parent/n)==sha for n,sha in seal.items());old_items+=len(seal)
    assert old_items==12072
    aliases=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(aliases)==9 and all(row['valid'] for row in aliases)
    authors=subprocess.check_output(['git','log','08ac8187..HEAD','--format=%an <%ae>'],cwd=ROOT,text=True).splitlines()
    assert authors and set(authors)=={'spinner-bot <langxibielangle@qq.com>'}
    links=[]
    maintained=[ROOT/'AGENTS.md',ROOT/'README.md',ROOT/'experiments/style/README.md']
    for path in sorted(BASE.rglob('*.md'))+maintained:
        for raw in re.findall(r'\[[^\]]*\]\(([^)]+)\)',path.read_text()):
            target=raw.split('#',1)[0].strip('<>')
            if not target or re.match(r'[a-z]+://',target):continue
            assert (path.parent/target).resolve().exists(),(str(path),target)
            links.append({'source':str(path.relative_to(ROOT)),'target':raw})
    result={'verified':True,'scope':'main experimental trainer query/followup input protection only; not all data schemas, semantic leakage, or training readiness',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(__file__),'red_sha256':digest(work/'isolation-red.json'),'fixed_sha256':digest(work/'isolation-fixed.json'),
        'full_regression_binding_sha256':digest(proof_path),'current_source_inputs':493,'Python_passed':2540,'Python_skipped':1,
        'targeted_passed':36,'targeted_skipped':1,'actual_input_occurrences_rejected':100,
        'changed_software_inputs_since_C50':sorted(changes),'old_seals_including_migration':49,'old_items':old_items,
        'asset_aliases_valid':9,'spinner_commits_checked':len(authors),'MD_links_checked':len(links),'links':links,
        'model_constructions':0,'training_steps':0,'new_native_calls':0,'default_model_changed':False,
        'training_prerequisite_issue002_open':True,'cycle51_complete':False,'goal_active':True}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C51 checkpoint:2540/1 Python;36/1 targeted;100 actual inputs rejected;493source;49old/12072;main-input repair only;training still unprepared')


def read(path):
    return json.loads(Path(path).read_text())


if __name__=='__main__':main()

"""Independently recompute raw observations and historical Git bindings, including failures."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
from browser_common import ROOT, BASE, digest, verify
WORK = BASE / '审计/工作目录/001-页面版本屏障'
OUT = BASE / '审计/收尾核验/browser-independent-proof.json'


def read(path):
    return json.loads(path.read_text())


def historical(path, expected):
    assert digest(path) == expected
    value = read(path)
    names = value['sha256']
    raw = subprocess.check_output(['git', 'archive', '--format=tar', value['source_ref'], '--', *sorted(names)], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        actual = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}
    assert actual == names
    for name, sha in names.items():
        if name.startswith(str(WORK.relative_to(ROOT)) + '/'):
            assert digest(ROOT / name) == sha, name  # Frozen evidence archives stay byte-identical.
    for entry in value['browser_bundle'].values():
        assert names[entry['archived_path']] == entry['sha256']
    return value


def module_binding(report, frozen):
    assert report['frozen_inputs'] == frozen
    assert report['actual_native_model_or_gpu'] is False and report['app_os_restart_claim'] is False
    for name, sha in report['runtime_module_sha256'].items():
        assert frozen['sha256'][name] == sha


def product_inputs(frozen):
    return {n: sha for n, sha in frozen['sha256'].items() if n.startswith(('src/', 'scripts/', 'tests/', 'frontend/'))}


def main():
    assert not OUT.exists()
    before = historical(WORK / 'before-inputs/freeze.json', '2da1d3c9143b038e45a548f066b7a381e9dd702b677d74b0faa4498bc372d88d')
    after = historical(WORK / 'after-inputs/freeze.json', '06bfebe78a9f5fa534b2415e46dda28233cf247cb2deb7164ca08fe4e75baa20')
    diagnostic = historical(WORK / 'after-diagnostic-inputs/freeze.json', '6ce6b486c7b746f47ea9e0d066d1e9ae99917ab93742a61d0c3e151fd70d5463')
    fixed_path = WORK / 'after-broadcast-fixed-inputs/freeze.json'
    fixed = verify(fixed_path, 'b7a72d605cce8728affa93cdedabe14912b4b1360396fdf10b2df2be92ffc60e', 'after')
    assert product_inputs(after) == product_inputs(diagnostic) == product_inputs(fixed)
    groups, proof_files = [], {}
    preparations = 0
    for phase, frozen in [('before', before), ('after', after)]:
        for page in ['emotion', 'dashboard']:
            path = BASE / f'实验/{phase}-{page}/evaluation.json'
            report = read(path)
            assert report['completed'] and report['failure'] is None and len(report['cases']) == 3
            module_binding(report, frozen)
            observations = []
            for case in report['cases']:
                assert case['completed'] and case['server_closed'] and case['browser_exit_code'] == 0
                browser = case['browser']
                assert json.loads(case['raw_browser_stdout']) == browser and browser['completed'] and not browser['errors']
                assert case['revision_after'] == 1 and case['source_after']['content'] == '[redacted]'
                prepared = json.loads(case['preparation_raw_response'])['data']
                assert prepared['generation_mode'] != 'llm' and prepared['user_arousal'] < 0
                preparations += 1
                for call in browser['calls']:
                    assert call['status'] == 200
                    json.loads(call['raw_response'])
                after_api = browser['after_api']
                automatic = after_api.get('automatic', after_api.get('emotion'))
                assert automatic['valence'] == automatic['arousal'] == 0
                stale = browser['delayed']['values'] == browser['before']['values']
                assert stale == browser['stale_at_fixed_observation'] == (phase == 'before')
                assert not browser['browser_reloaded_or_navigated_after_forget']
                assert browser['delayed_ms'] >= 1000 and browser['eventual_ms'] <= 22000
                if phase == 'after':
                    assert after_api['context']['revision'] == 1
                    if page == 'emotion':
                        assert all(v.replace(' ', '') == 'P0.00/A0.00' for v in browser['delayed']['values'])
                        assert len(browser['delayed']['values']) == 3
                        assert all(float(v) == 0 for v in browser['delayed']['form'].values())
                    else:
                        assert browser['delayed']['eventRows'] == 0
                observations.append({'repetition': case['repetition'], 'stale_1s': stale,
                    'sample_ms': browser['delayed_ms'], 'eventual_ms': browser['eventual_ms']})
            proof_files[str(path.relative_to(ROOT))] = digest(path)
            groups.append({'phase': phase, 'page': page, 'stale': sum(r['stale_1s'] for r in observations), 'n': 3, 'observations': observations})
    supplements = []
    for path in sorted((BASE / '实验').glob('supplement-*/evaluation.json')):
        report = read(path)
        frozen = {'06bfebe78a9f5fa534b2415e46dda28233cf247cb2deb7164ca08fe4e75baa20': after,
            '6ce6b486c7b746f47ea9e0d066d1e9ae99917ab93742a61d0c3e151fd70d5463': diagnostic,
            'b7a72d605cce8728affa93cdedabe14912b4b1360396fdf10b2df2be92ffc60e': fixed}[report['freeze_sha256']]
        module_binding(report, frozen)
        assert report['all_owned_servers_closed']
        browser = report['browser']
        assert json.loads(report['raw_browser_stdout']) == browser and not browser['errors']
        assert json.loads(report['preparation_raw_response'])['data']['generation_mode'] != 'llm'
        preparations += 1
        if report['completed']:
            assert report['browser_exit_code'] == 0 and browser['completed'] and report['failure'] is None
            id_ = report['case']['id']
            if 'same_revision' in id_ or 'service_instance' in id_:
                assert report['revision_after'] == 0 and report['source_after']['content'] == '我很难过'
            else:
                assert report['revision_after'] == 1 and report['source_after']['content'] == '[redacted]'
            if 'metadata' in id_:
                assert browser['observations']['fault_dom']['values'] == []
                assert browser['observations']['fault_dom']['alerts']
            if 'manual_fields' in id_:
                assert browser['observations']['final_dom']['form'] == {'valence': '0', 'arousal': '-0.1', 'duration': '900', 'reason': 'C35保留手工字段'}
                state = browser['observations']['after_api']
                assert state['effective'] == {'valence': .6, 'arousal': -.1}
            if 'same_revision' in id_:
                assert browser['observations']['ordinary_result']['generation_mode'] != 'llm'
                preparations += 1
            if 'service_instance' in id_:
                assert browser['restart']['before'] != browser['restart']['after']
            if 'broadcast' in id_:
                assert browser['native_cross_window_notice']
                assert any(row.get('body', {}).get('data', {}).get('context', {}).get('revision') == 1
                    for row in browser['network'] if isinstance(row.get('body', {}).get('data'), dict))
        else:
            assert 'broadcast' in report['case']['id'] and report['browser_exit_code'] == 1 and browser['failure']
        supplements.append({'case': report['case']['id'], 'run': path.parent.name,
            'completed': report['completed'], 'failure_retained': report['failure'] is not None})
        proof_files[str(path.relative_to(ROOT))] = digest(path)
    assert len(supplements) == 10 and sum(r['completed'] for r in supplements) == 8
    assert preparations == 23  # 12 matched primary +10 supplement preparations +1 ordinary positive turn.
    regression = []
    for mode in ['python', 'frontend', 'build', 'browser']:
        path = BASE / f'审计/工作目录/002-系统回归/integrated-{mode}-final-binding.json'
        data = read(path)
        assert data['exit_code'] == 0 and data['source_unchanged'] and not data['gpu_inference_claim']
        for name, sha in data['source_git_sha256'].items():
            assert digest(ROOT / name) == sha, name
        log = path.with_name(f'integrated-{mode}-final.log')
        assert digest(log) == data['log_sha256']
        if mode == 'python':
            assert '1835 passed, 1 skipped' in log.read_text()
        if mode == 'frontend':
            assert '192 passed (192)' in log.read_text()
        if mode == 'browser':
            assert data['runtime_matches'] and '15 passed' in log.read_text() and '16 skipped' in log.read_text()
        regression.append({'mode': mode, 'inputs': len(data['source_git_sha256']), 'sha256': digest(path)})
    seals = []
    for path in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(path.parents[1].name[6:]) >= 35:
            continue
        entries = read(path)
        for name, sha in entries.items():
            assert digest(path.parents[1] / name) == sha
        seals.append({'cycle': path.parents[1].name, 'items': len(entries), 'manifest_sha256': digest(path)})
    assert len(seals) == 32 and seals[-1]['manifest_sha256'] == 'ecb7e4b98dfab75a4d3b630c4409f6b5c2f4efb455c120a35a437e8c1eb90f87'
    expected_old = read(BASE.parent / 'cycle-34/审计/收尾核验/system-evidence.json')['old_manifests']
    assert seals[:-1] == expected_old
    migration = ROOT / 'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration) == '717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    for name, sha in read(migration).items():
        assert digest(migration.parent / name) == sha
    result = {'verified': True, 'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'verifier_sha256': digest(Path(__file__)), 'primary_groups': groups, 'supplement_runs_including_failures': supplements,
        'actual_offline_app_results_including_failed_harness': preparations, 'native_or_gpu_calls': 0,
        'regression': regression, 'old_cycle_seals': seals, 'migration_seal_items': len(read(migration)),
        'historical_before_inputs': len(before['sha256']), 'historical_primary_after_inputs': len(after['sha256']),
        'current_and_historical_fixed_inputs': len(fixed['sha256']), 'evidence_sha256': proof_files,
        'interpretation': 'engineering controlled browser privacy boundary only; independent program, not independent human review'}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('Verified: primary before3/3->after0/3 each page; supplement8passed/2retained failures;23offline results;33old seals;0native/GPU')


if __name__ == '__main__':
    main()

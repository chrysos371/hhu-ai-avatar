"""C37 historical-native/current-source audit; no inference or old output mutation.

The retired native verifier is reused with an explicitly historical source adapter.
This is a new archival reconstruction, not a fresh current-native gate or a second
independent implementation of the wire parser. Current regressions are separate.
"""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE / '审计/工作目录/001-默认能力基线'
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_native_groups as native


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def history(ref, names):
    raw = subprocess.check_output(['git', 'archive', '--format=tar', ref, '--', *sorted(names)], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
                for m in archive if m.isfile()}


def verify_historical_freeze(path, expected, model):
    assert path == WORK / 'execution-freeze.json'
    assert digest(path) == expected == native.EXPECTED
    frozen = read(path)
    assert model in frozen['models'] and len(frozen['sha256']) == 328
    assert history(frozen['source_ref'], frozen['sha256']) == frozen['sha256']
    return frozen


def main():
    output = BASE / '审计/收尾核验/system-evidence.json'
    assert not output.exists(), 'Use a new evidence path; never overwrite'
    frozen = verify_historical_freeze(native.FREEZE, native.EXPECTED, 'qwen3-4b-q4_k_m')
    retirement = read(WORK / 'native-phase-retirement.json')
    assert retirement['must_not_use_old_current_check_after_source_changes']
    assert retirement['native_calls'] == 264 and retirement['app_results'] == 144
    changed = [name for name, sha in frozen['sha256'].items() if digest(ROOT / name) != sha]
    assert changed == ['src/avatar/brain/reminders.py', 'tests/test_chinese_reminder_clock.py'], changed
    # Only the retired source identity check changes; every archived wire/trace/
    # response/schema/SSE/storage/runtime/cleanup check remains the same function.
    native.verify_source = verify_historical_freeze
    native_rows, semantic_rows, repeat_rows = [], [], []
    for model, gate_name, expected_bad in [('4b', '4b-three-run-gate.json', 6),
                                        ('32b', '32b-three-run-engineering-proof.json', 2)]:
        gate = read(WORK / gate_name)
        assert gate['verified'] and gate['verifier_sha256'] == digest(BASE / '审计/verify_native_groups.py')
        assert gate['freeze_sha256'] == native.EXPECTED
        key = 'four_b_engineering_sha256' if model == '4b' else 'thirty_two_b_engineering_sha256'
        assert retirement[key] == digest(WORK / gate_name)
        reference_reply = reference_wire = reference_native = None
        for n in (1, 2, 3):
            folder = BASE / '实验' / f'default-{model}-r{n}'
            row = native.verify_group(folder)
            assert row == gate['runs'][n - 1]
            report = read(folder / 'evaluation.json')
            assert history(report['source_ref'], frozen['sha256']) == frozen['sha256']
            assert report['native_finish_counts'] == {'stop': 44} and not report['quality_truncations']
            sample = read(folder / 'sample/native-output.json')
            turns = [(c['id'], i + 1, t) for c in sample['cases'] for i, t in enumerate(c['turns'])]
            review_path = BASE / '审计/工作目录/002-语义审阅' / (folder.name + '-span-review.json')
            review = read(review_path)
            assert review['source_sample_sha256'] == digest(folder / 'sample/native-output.json')
            assert review['source_evaluation_sha256'] == digest(folder / 'evaluation.json')
            assert len(review['rows']) == review['reviewed_turns'] == 24
            assert review['actual_model_generated_turns'] == row['model_generated_turns'] == 20
            for annotation, (case_id, number, turn) in zip(review['rows'], turns, strict=True):
                result = turn['result']
                assert (annotation['case'], annotation['turn'], annotation['input'], annotation['reply']) == (case_id, number, turn['input'], result['reply'])
                assert annotation['generation_mode'] == result['generation_mode']
                assert annotation['actual_reminder_count'] == len(turn['reminders'])
                assert annotation['tool_calls'] == result['tool_calls']
                span = annotation.get('span')
                if span:
                    assert result['reply'][span['start_codepoint']:span['end_codepoint']] == span['text']
            assert review['findings']['unique_clear_unsupported_external_action_turns'] == expected_bad
            replies = [t['result']['reply'] for _, _, t in turns]
            wire = [json.loads(line) for line in (folder / 'wire.jsonl').read_text().splitlines()]
            requests = [r['request_body_sha256'] for r in wire]
            replies_native = [native.parse_wire(r)['reply'] for r in wire]
            if n == 1:
                reference_reply, reference_wire, reference_native = replies, requests, replies_native
            else:
                repeat_rows.append({'model': model, 'reference_repetition': 1, 'compared_repetition': n,
                    'app_reply_bytes_equal': sum(a == b for a, b in zip(reference_reply, replies, strict=True)), 'app_reply_count': 24,
                    'request_wire_sha_equal': sum(a == b for a, b in zip(reference_wire, requests, strict=True)), 'request_count': 44,
                    'native_text_bytes_equal': sum(a == b for a, b in zip(reference_native, replies_native, strict=True)), 'native_call_count': 44})
            native_rows.append(row)
            semantic_rows.append({'group': folder.name, 'review_sha256': digest(review_path),
                'model_generated_turns': 20, 'framework_turns': 4, 'reviewed_turns': 24,
                'findings': review['findings'], 'review_kind': review['scope']})
    assert repeat_rows == read(WORK / 'fixed_order_repeatability.json')['rows']
    closed = read(WORK / 'native-resource-closeout.json')
    assert closed['verified'] and not closed['owned_os_pids_still_present'] and not closed['owned_gpu_pids_still_present']
    assert all(not Path('/proc', str(pid)).exists() for pid in closed['owned_provider_pids'] + closed['owned_sampler_pids'])
    bindings, browser_rows = [], []
    for tag in ('chinese-clock', 'title-boundary'):
        for mode in ('python', 'frontend', 'build', 'browser'):
            name = f'{tag}-{mode}'
            p = WORK / (name + '-final-binding.json')
            d = read(p)
            inputs = d['source_git_sha256']
            assert len(inputs) == 431 and d['source_unchanged'] and d['exit_code'] == 0
            assert history(d['head'], inputs) == inputs
            driver = str((BASE / '审计/run_regression.py').relative_to(ROOT))
            assert history(d['head'], [driver])[driver] == d['driver_sha256']
            assert digest(WORK / (name + '-final.log')) == d['log_sha256']
            if tag == 'title-boundary':
                assert all(digest(ROOT / f) == sha for f, sha in inputs.items())
            if mode == 'browser':
                runtime = read(WORK / (tag + '-browser-final-runtime.json'))
                assert digest(WORK / (tag + '-browser-final-runtime.json')) == d['runtime_sha256']
                assert d['runtime_matches'] and d['optional_e2e_flags_cleared']
                assert len(runtime['module_paths']) == 8 and len(runtime['frontend_sha256']) == 5
                assert runtime['frontend_sha256'] == d['runtime_artifact_sha256']
                assert runtime['state_privacy_protocol_sha256'] == inputs['evals/interaction/cycle-36/maintained-state-privacy-protocol.json']
                assert all(runtime['module_sha256'][k] == inputs[str(Path(v).relative_to(ROOT))] for k, v in runtime['module_paths'].items())
                records = WORK / 'chinese-clock-browser-records' if tag == 'chinese-clock' else BASE / '审计/工作目录/004-标题边界修复/browser-records'
                for which in ('emotion', 'dashboard'):
                    record = read(records / (which + '.json'))
                    assert record['completed'] and record['failure'] is None and not record['errors']
                    assert history(record['head'], inputs) == inputs  # evidence-only commit during browser run is allowed
                    assert record['sourceAfter']['redacted'] and record['sampleMs'] >= 1000
                    before, after = record['beforeApi'], record['afterApi']
                    assert after['context']['revision'] == before['context']['revision'] + 1
                    state = after.get('automatic', after.get('emotion'))
                    assert state['valence'] == state['arousal'] == 0
                    assert [v.replace(' ', '') for v in record['fixedDom']] == (['P0.00/A0.00'] * 3 if which == 'emotion' else ['愉悦度0.00·唤醒度0.00'])
                    assert record['noReloadNavigationOrUiPrivacyNoticeAfterErasure']
                    if which == 'emotion':
                        assert record['form'] == {'valence': '0', 'arousal': '0'}
                    browser_rows.append({'tag': tag, 'page': which, 'sha256': digest(records / (which + '.json')),
                        'sample_ms': record['sampleMs'], 'actual_head': record['head'], 'same_execution_bytes_as_runner': True})
            bindings.append({'name': name, 'sha256': digest(p), 'head': d['head'], 'current_source': tag == 'title-boundary'})
    assert '1911 passed, 1 skipped' in (WORK / 'title-boundary-python-final.log').read_text()
    assert '192 passed (192)' in (WORK / 'title-boundary-frontend-final.log').read_text()
    assert '17 passed' in (WORK / 'title-boundary-browser-final.log').read_text() and '16 skipped' in (WORK / 'title-boundary-browser-final.log').read_text()
    preflight = []
    for suffix, expected in [('', 16), ('-chinese-clock', 24), ('-title-boundary', 24)]:
        p = WORK / ('application-preflight' + suffix) / 'evaluation.json'
        d = read(p)
        assert d['native_calls'] == 0
        actual = sum(len(c['turns']) for c in d['cases'])
        assert actual == expected
        assert bool(d['failure']) == (suffix == '')
        assert d['completed'] == bool(suffix)
        preflight.append({'path': str(p.relative_to(ROOT)), 'sha256': digest(p), 'actual_app_results': actual, 'completed': d['completed']})
    matrix = read(BASE / '审计/工作目录/004-标题边界修复/after-repair-matrix.json')
    assert matrix['before_matches'] == 6 and matrix['after_matches'] == 12 and matrix['actual_native_calls'] == 0
    assert matrix['source_after_sha256'] == digest(ROOT / 'src/avatar/brain/reminders.py')
    seals = []
    for p in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(p.parents[1].name[6:]) >= 37:
            continue
        for name, sha in read(p).items():
            assert digest(p.parents[1] / name) == sha
        seals.append({'cycle': p.parents[1].name, 'items': len(read(p)), 'sha256': digest(p)})
    assert len(seals) == 34 and sum(r['items'] for r in seals) == 5938
    migration = ROOT / 'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration) == '717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    for name, sha in read(migration).items():
        assert digest(migration.parent / name) == sha
    links = json.loads(subprocess.check_output(['python3', '-B', 'scripts/link_project_assets.py', '--check'], cwd=ROOT, text=True))
    assert len(links) == 9 and all(r['valid'] for r in links)
    result = {'verified': True, 'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'verifier_sha256': digest(Path(__file__)), 'native_source_kind': 'retired_historical_git_only_not_current_native_gate',
        'native_reconstruction_reuses': 'verify_native_groups.verify_group with explicit historical Git source adapter; no independent wire parser implementation claim',
        'native_freeze_sha256': native.EXPECTED, 'native_frozen_inputs': 328, 'post_retirement_changed_frozen_inputs': changed,
        'native_groups': native_rows, 'actual_native_calls': 264, 'native_app_results': 144, 'warmup_calls_included': 12,
        'semantic_agent_reviews': semantic_rows, 'semantic_or_model_promotion_approval': False,
        'repeatability': repeat_rows, 'owned_resources_closed': True, 'regression_bindings': bindings,
        'browser_rows': browser_rows, 'current_input_count': 431, 'offline_preflights': preflight,
        'offline_app_results_including_first_failed_phase': 64, 'title_matrix': {'before': 6, 'after': 12, 'controls': 12},
        'old_cycle_seals': seals, 'migration_items_unchanged': 88, 'historical_seals_total': 35,
        'historical_entries_total': 6026, 'data_links': links, 'closed_issues': ['C37-001', 'C37-002', 'C37-005'],
        'open_issues': ['C37-003', 'C37-004', 'C37-006', 'C37-007'], 'new_model_calls_during_this_reconstruction': 0}
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print('C37 historical/current audit passed:328 old/431 current inputs;144app/264native;64offline;35seals/6026items;4semantic issues OPEN')


if __name__ == '__main__':
    main()

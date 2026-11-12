"""C34 systematic source, evidence, failure-cost and owned-resource audit."""
from collections import Counter
import json
from pathlib import Path
import subprocess
from revision_common import ROOT, BASE, RUNTIME, digest, verify_freeze, verify_historical_binding, verify_backend
from verify_native_revision import verify
from verify_shared_affect import parse_events


def read(path):
    return json.loads(path.read_text())


work = BASE / '审计/工作目录'
primary = work / '001-自动情绪版本失效'
regression = work / '002-系统回归'
output = BASE / '审计/收尾核验/system-evidence.json'
assert not output.exists()
old = []
for manifest in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
    if int(manifest.parents[1].name.split('-')[1]) >= 34:
        continue
    entries = read(manifest)
    for name, value in entries.items():
        assert digest(manifest.parents[1] / name) == value, (manifest, name)
    old.append({'cycle': manifest.parents[1].name, 'items': len(entries), 'manifest_sha256': digest(manifest)})
assert len(old) == 31 and old[-1]['items'] == 2015
assert old[-1]['manifest_sha256'] == '5b4d59c03f036dafd99f22f981d8404c646461729a57ee8af87177c998d321de'
freeze = primary / 'native-after-freeze.json'
frozen = verify_freeze(freeze, digest(freeze), phase='after')
verify_historical_binding(frozen)
assert len(frozen['sha256']) == 491
runtime = verify_backend(ROOT / RUNTIME, frozen['sha256'][RUNTIME])
assert len(runtime['files_sha256']) == 54
bindings = {}
archive = read(regression / 'browser-dist-archive.json')
for mode in ('full-python', 'default-browser'):
    binding = read(regression / (mode + '-binding.json'))
    assert binding['exit_code'] == 0 and binding['source_unchanged']
    assert digest(regression / (mode + '.log')) == binding['log_sha256']
    for name, value in binding['source_sha256'].items():
        assert digest(ROOT / name) == value
    committed = {name: value for name, value in binding['source_sha256'].items() if name not in archive}
    verify_historical_binding({'source_ref': binding['head'], 'sha256': committed})
    bindings[mode] = {'head': binding['head'], 'inputs': len(binding['source_sha256']),
        'seconds_with_audit': binding['seconds'], 'binding_sha256': digest(regression / (mode + '-binding.json'))}
assert '1810 passed, 1 skipped' in (regression / 'full-python.log').read_text()
assert '15 passed' in (regression / 'default-browser.log').read_text()
assert '16 skipped' in (regression / 'default-browser.log').read_text()
browser = read(regression / 'browser-runtime.json')
assert len(browser['module_paths']) == 7
assert read(regression / 'default-browser-binding.json')['runtime_matches']
for name, entry in archive.items():
    assert digest(ROOT / name) == digest(ROOT / entry['archived_path']) == entry['sha256']
native = []
for model in ('4b', '32b'):
    before_path = BASE / ('实验/native-before-v2-' + model + '/evaluation.json')
    after_path = BASE / ('实验/native-after-' + model + '/evaluation.json')
    before = verify(before_path, current_source=False)
    after = verify(after_path, current_source=True)
    assert before == read(primary / ('native-before-' + model + '-historical-after-repair.json'))
    assert after == read(primary / ('native-after-' + model + '-independent.json'))
    raw = read(after_path)
    assert Path(raw['before_path']).resolve() == before_path.resolve() and raw['before_sha256'] == digest(before_path)
    for proof in (before, after):
        assert proof['observations']['prepared_nonzero_automatic'] and proof['observations']['prepared_nonzero_user_observation']
    assert not before['observations']['automatic_zero_after_forget'] and not before['observations']['user_observation_zero_after_forget']
    assert after['observations']['automatic_zero_after_forget'] and after['observations']['user_observation_zero_after_forget']
    assert after['observations']['neutral_result_character_pad'] == after['observations']['neutral_result_user_observation'] == [0, 0]
    native.extend((before, after))
counter = Counter()
app_results = 0
owned = []
for path in sorted((BASE / '实验').glob('*/evaluation.json')):
    report = read(path)
    assert report['cleanup_passed'] and report['provider_exit'] == 0 and not report['cleanup_errors']
    trace = [json.loads(line) for line in (path.parent / 'provider-trace.jsonl').read_text().splitlines()]
    assert len(trace) == len(report['requests'])
    counter.update(row.get('kind') or 'warmup' for row in report['requests'])
    pids = [report['provider_pid']] + [worker['pid'] for worker in report['workers']]
    state = subprocess.run(['ps', '-p', ','.join(map(str, pids)), '-o', 'pid='], capture_output=True, text=True)
    assert not state.stdout.strip(), ('owned process still alive', state.stdout)
    assert report['provider_closeout']['runtime_files_verified_after'] == 54
    count = sum(parse_events(turn['raw_sse'])[-1]['event'] == 'result' for turn in report['cases'][0]['turns'])
    app_results += count
    owned.append({'folder': path.parent.name, 'provider_pid': report['provider_pid'], 'worker_pids': pids[1:],
        'no_owned_processes_alive': True, 'native_calls': len(trace), 'actual_result_terminals': count,
        'completed': report['completed'], 'seconds_with_audit': report['seconds']})
assert counter == {'warmup': 10, 'cognitive': 14, 'generation': 14} and app_results == 19 and len(owned) == 5
partial = read(BASE / '实验/native-before-4b/evaluation.json')
assert not partial['completed'] and 'AssertionError' in partial['failure']
verify_historical_binding(partial['frozen_inputs'])
retired = read(primary / 'native-after-retirement.json')
assert retired['actual_total_native_calls'] == sum(counter.values()) == 38
for row in retired['reports']:
    assert digest(ROOT / row['evaluation']) == row['sha256']
http = read(primary / 'controlled-http-independent.json')
assert http['verified'] and http['phases']['before']['forget_retained_old_state'] == 3
assert http['phases']['after']['forget_retained_old_state'] == 0
admission = read(primary / 'after-admission-controls.json')
assert len(admission['cases']) == 4 and all(row['exit_code'] != 0 and row['output_not_created'] for row in admission['cases'])
result = {'verified': True, 'old_manifests': old, 'after_freeze_inputs': len(frozen['sha256']),
    'after_freeze_sha256': digest(freeze), 'runtime_files_current_verified': 54, 'regressions': bindings,
    'actual_runtime_modules': 7, 'archived_browser_bundle_files': len(archive),
    'matched_native_proofs': native, 'all_actual_native_kind_counts': dict(counter),
    'actual_native_calls_including_partial': sum(counter.values()), 'actual_result_terminals_including_partial': app_results,
    'owned_processes': owned, 'http_independent_sha256': digest(primary / 'controlled-http-independent.json'),
    'general_semantics_or_human_quality_approved': False}
output.parent.mkdir(exist_ok=True)
with output.open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('C34 system audit passed:31 old seals,491 frozen inputs,54 runtime files,1810/1 Python,15/16 browser,38 actual native calls,19 results,5 owned providers clean.')

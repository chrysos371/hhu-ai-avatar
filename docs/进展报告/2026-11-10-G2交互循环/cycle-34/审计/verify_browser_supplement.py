"""Recheck saved actual-browser DOM, original HTTP and source redaction evidence."""
import json
from pathlib import Path
from revision_common import ROOT, BASE, digest, verify_historical_binding

work = BASE / '审计/工作目录/003-浏览器情绪缓存补审'
folder = work / 'v2'
report = json.loads((folder / 'browser-cache-observations.json').read_text())
version = json.loads((folder / 'execution-version.json').read_text())
verify_historical_binding({'source_ref': version['source_ref'], 'sha256': version['files_sha256']})
assert digest(folder / 'browser-cache-observations.json') == version['evidence_sha256']
assert report['completed'] and report['actual_browser_and_app_http'] and not report['actual_native_model_or_gpu']
assert len(report['cases']) == 3
rows = []
for case in report['cases']:
    assert case['completed'] and case['browser_exit_code'] == 0 and not case['raw_browser_stderr']
    browser = case['browser']
    assert json.loads(case['raw_browser_stdout']) == browser and browser['completed'] and not browser['errors']
    assert browser['before'] == browser['immediate'] == browser['delayed']
    assert all(value.replace(' ', '').replace('\n', '') == 'P0.00/A0.00' for value in browser['eventual'])
    assert browser['stale_immediate'] and browser['stale_at_fixed_observation']
    assert 1000 <= browser['delayed_ms'] < 2000 and browser['delayed_ms'] < browser['eventual_ms'] < 15000
    assert not browser['browser_reloaded_or_navigated_after_forget']
    calls = browser['calls']
    assert [call['route'] for call in calls] == ['/api/v1/emotion', '/api/forget', '/api/v1/emotion']
    assert all(call['status'] == 200 for call in calls)
    before, after = [json.loads(calls[index]['raw_response'])['data'] for index in (0, 2)]
    assert before == browser['before_api'] and before['automatic']['arousal'] < 0
    assert after == browser['after_api'] and after['automatic'] == after['user_observation'] == {'valence': 0, 'arousal': 0}
    assert case['revision_after'] == 1 and case['source_after']['content'] == '[redacted]'
    assert case['source_after']['role'] == 'user'
    screenshot = folder / f"repetition-{case['repetition']}-after-1s.png"
    assert digest(screenshot) == version['screenshots_sha256'][screenshot.name]
    rows.append({'repetition': case['repetition'], 'stale_after_ms': browser['delayed_ms'],
        'eventual_clear_ms': browser['eventual_ms'], 'source_redacted': True, 'fresh_api_zero': True})
for name, entry in version['actual_frontend_bundle'].items():
    assert digest(ROOT / name) == digest(ROOT / entry['archived_path']) == entry['sha256']
first = json.loads((work / 'browser-cache-observations.json').read_text())
assert not first['completed'] and len(first['cases']) == 1 and not first['cases'][0]['completed']
assert first['cases'][0]['browser_exit_code'] != 0 and 'locator.waitFor' in first['cases'][0]['raw_browser_stderr']
result = {'verified': True, 'evidence_sha256': version['evidence_sha256'], 'rows': rows,
    'reproduced_stale_cases': 3, 'actual_native_calls': 0, 'successful_offline_preparation_results': 3,
    'first_failed_startup_offline_preparation_results': 1, 'historical_sources_verified': True,
    'original_http_dom_sql_and_screenshot_hashes_verified': True}
with (folder / 'independent-proof.json').open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('Verified3 actual browser DOM/API/SQL cache gaps and preserved1 startup failure;0native.')

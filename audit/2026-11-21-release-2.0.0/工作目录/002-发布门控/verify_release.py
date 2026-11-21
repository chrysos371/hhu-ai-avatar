"""Read-only, fail-closed release evidence verifier. Never publishes or tags."""
import argparse
import copy
from hashlib import sha256
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[4]
REQUIRED = {'python', 'native', 'native_freeze', 'native_manifest', 'alignment', 'content', 'cases',
            'frontend', 'build', 'install', 'soak', 'formal', 'browser_batch', 'asr', 'signal',
            'archive', 'report_qa', 'goals', 'issues', 'original_issues', 'deferrals'}
SUITES = {'base', 'playback', 'history-audit', 'external-erase', 'history-restore', 'notification',
          'navigation', 'reminder-privacy', 'receipts', 'reminder-normal-claim-recovery',
          'reminder-response-drop-after-commit-recovery', 'reminder-navigation-before-response-recovery',
          'reminder-ack-response-drop-after-commit-recovery'}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON key')
        result[key] = value
    return result


def read(path):
    return json.loads(path.read_text(), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def zero(value):
    return type(value) is int and value == 0


def check_facts(data, config):
    require(config['version'] == '2.0.0', 'unexpected version')
    require(config['claims'] == dict(human_review_approved=False, physical_device_approved=False,
                                   multiday_approved=False), 'authorized deferrals cannot become human approval')
    p = data['python']
    require(zero(p['actual_returncode']) and p['source_unchanged'] is True, 'full Python gate')
    cases = data['cases']['cases']
    expected_turns = 2*sum(len(case['turns']) for case in cases)
    require(len({case['id'] for case in cases}) == len(cases) and len(cases) >= 68, 'original root coverage')
    n = data['native']
    require(n['engineering_passed'] is True and zero(n['actual_worker_wait_code'])
            and zero(n['actual_provider_wait_code']) and n['provider_pid_and_gpu_retired'] is True
            and n['source_unchanged'] is True, 'actual native source/process gate')
    require(n['completed_trials'] == 2*len(cases) and n['completed_turns'] == expected_turns
            and type(n['actual_generate_calls']) is int and 0 < n['actual_generate_calls'] <= 600
            and n['actual_generate_calls'] == n['actual_client_native_calls'], 'native coverage/call gate')
    require(data['alignment']['passed'] is True
            and len(data['alignment']['rows']) == n['actual_generate_calls'], 'native logical alignment')
    review = data['content']
    require(review['content_approved'] is True and len(review['rows']) == expected_turns
            and review['all_turns_reviewed'] == expected_turns, 'complete source review')
    expected_keys = {(c['id'], arm, index) for c in cases for arm in ('baseline', 'candidate')
                     for index in range(1, len(c['turns'])+1)}
    actual = {(r['case_id'], r['arm'], r['turn']) for r in review['rows']}
    require(actual == expected_keys and len(actual) == len(review['rows']), 'unique complete review rows')
    require(all(not r['issues'] for r in review['rows'] if r['arm'] == 'candidate'), 'candidate critical mismatch')
    require(data['frontend']['passed'] is True and data['frontend']['source_unchanged'] is True
            and len(data['frontend']['steps']) == 4
            and all(zero(s['actual_returncode']) for s in data['frontend']['steps']), 'frontend gate')
    b = data['build']
    require(zero(b['actual_build_tool_returncode']) and b['build_result']['passed'] is True
            and b['build_result']['source_unchanged'] is True and b['build_result']['version'] == '2.0.0', 'build gate')
    i = data['install']
    require(zero(i['actual_smoke_driver_returncode']) and i['result']['passed'] is True
            and i['result']['version'] == '2.0.0'
            and i['result']['build_source'] == b['build_result']['source_ref']
            and len(i['result']['server_runs']) == 2
            and i['result']['legacy_database_migration_preserved_profile'] is True
            and i['result']['rollback_from_backup_with_original_source'] is True
            and all(zero(s['actual_returncode']) for s in i['preparation_actual_steps']), 'independent installation gate')
    s = data['soak']
    require(zero(s['actual_driver_returncode']) and s['summary']['passed'] is True
            and s['completed_events'] == 60 and s['summary']['model_requests'] == 120
            and [p['actual_wait_code'] for p in s['summary']['processes']] == [0, -9, 0]
            and all(p['pid_retired'] is True for p in s['summary']['processes'])
            and s['summary']['p95_seconds'] <= 10 and s['summary']['installed_unchanged'] is True, 'fixed short soak gate')
    require(all(p['rss_range_kib'] <= 65536 and p['fd_range'] <= 4
                and all(r['rss_kib'] < 1048576 and r['fd'] < 128 and r['threads'] <= 32 for r in p['resources'])
                for p in s['summary']['processes']), 'registered resource bounds')
    f = data['formal']
    require(f['passed'] is True and f['source_unchanged'] is True and f['completed_browser_viewports'] == 2
            and zero(f['actual_server_wait_code']) and zero(f['actual_probe_wait_code'])
            and f['server_identity_retired'] is True and f['probe_identity_retired'] is True, 'formal renderer gate')
    stages = data['browser_batch']['stages']
    require(data['browser_batch']['passed'] is True and {s['suite'] for s in stages} == SUITES
            and len(stages) == len(SUITES) and all(zero(s['actual_returncode']) for s in stages), 'complete browser batch')
    browser_proofs = [p for key, p in data.items() if key.startswith('browser_suite_')]
    require(len(browser_proofs) == 13 and {p['suite'] for p in browser_proofs} == SUITES, 'browser proof inventory')
    require(all(p['passed'] is True and zero(p['actual_returncode']) and p['source_unchanged'] is True
                and p['ui_unchanged'] is True and p['stats']['unexpected'] == 0 and p['stats']['flaky'] == 0
                and p['stats']['expected'] > 0 and (p['suite'] == 'base' or p['stats']['skipped'] == 0)
                and p['ui_sha256'] == b['build_result']['ui_sha256'] for p in browser_proofs), 'browser failures/bytes')
    a = data['asr']
    require(a['passed'] is True and zero(a['actual_returncode']) and a['source_unchanged'] is True
            and a['external_unchanged'] is True and a['summary']['samples'] == 40
            and a['summary']['failed_samples'] == 0 and a['summary']['passes_preregistered_gate'] is True, 'ASR gate')
    q = data['signal']
    require(q['passed'] is True and q['source_unchanged'] is True and len(q['steps']) == 4
            and all(zero(p['actual_returncode']) for p in q['steps']), 'signal clock gate')
    a = data['archive']
    require(a['passed'] is True and len(a['old_seals']) == 55 and a['sealed_entries'] == 12737
            and a['original_documents'] == 255 and a['canonical_issue_ids'] == 242
            and a['deleted_files'] == a['modified_original_seals'] == 0, 'archive preservation')
    require(data['report_qa']['passed'] is True and data['report_qa']['viewports'] == [1440, 390]
            and data['report_qa']['links_checked'] > 0, 'report display/link gate')
    goals = data['goals']['goals']
    require({g['id'] for g in goals} == {'G01', 'G02', 'G03', 'G04', 'G05', 'G06', 'G07', 'R01'}, 'goal coverage')
    require(all(g.get('final_release_status') in ('verified_software_scope', 'verified_with_user_deferrals',
                                                'deferred_by_user', 'verified_delivery') for g in goals), 'unverified goal')
    require(all(r['status'].startswith('closed') for r in data['issues']['rows']), 'open corrective issue')
    originals = data['original_issues']['rows']
    require(len(originals) == 242 and all(r.get('final_release_disposition') for r in originals), 'original dispositions incomplete')
    require(all(not r['final_release_disposition'].startswith(('open', 'active', 'pending')) for r in originals), 'open original root')


def verify_files(data, config, files):
    """All hashes are checked independently of fact/self-report fields."""
    checked = {}
    def verify(path, expected):
        path = Path(path).resolve()
        require(path.is_file(), 'missing evidence: '+str(path))
        actual = digest(path)
        require(actual == expected, 'changed bytes: '+str(path))
        checked[str(path)] = actual
    for key, descriptor in config['proofs'].items():
        verify(ROOT/descriptor['path'], descriptor['sha256'])
    for p in data.values():
        if not isinstance(p, dict):
            continue
        sources = p.get('source_sha256')
        if isinstance(sources, dict):
            for name, value in sources.items():
                verify(ROOT/name, value)
        for root_key, hash_key in [('raw', 'raw_sha256'), ('raw_root', 'raw_sha256'),
                                  ('root', 'sha256'), ('preparation', 'preparation_sha256')]:
            if root_key in p and hash_key in p:
                for name, value in p[hash_key].items():
                    verify(Path(p[root_key])/name, value)
        for name, value in p.get('external_sha256', {}).items():
            verify(Path(name), value)
    p = data['python']
    verify(ROOT/config['python_log'], p['log_sha256'])
    require(re.search(r'\b'+str(config['python_passed'])+r' passed, 1 skipped\b', (ROOT/config['python_log']).read_text()), 'pytest count/log')
    source_ref, values = data['native_freeze']['source_ref'], data['native_freeze']['sha256']
    raw = subprocess.check_output(['git', 'archive', '--format=tar', source_ref, '--', *values], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as stream:
        historical = {m.name: sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    require(historical == values, 'native frozen Git bytes')
    for name, value in values.items():
        verify(ROOT/name, value)
    verify(ROOT/config['alignment_driver'], data['alignment']['source_sha256'])
    verify(ROOT/config['proofs']['native_manifest']['path'], data['content']['raw_manifest_sha256'])
    verify(ROOT/config['proofs']['native_freeze']['path'], data['content']['source_freeze_sha256'])
    case_map = {c['id']: c for c in data['cases']['cases']}
    for row in data['content']['rows']:
        path = Path(row['turn_path'])
        verify(path, row['turn_sha256'])
        actual = read(path)
        sources = [dict(id=r['id'], text=r['content']) for r in actual['sql']['memory_messages'] if r['role'] == 'user']
        require(actual['result']['reply'] == row['reply'] == actual['sql_assistant']
                and sources == row['source_user_messages']
                and [r['text'] for r in sources] == case_map[row['case_id']]['turns'][:row['turn']], 'review/source row mismatch')
    build = data['build']['build_result']
    for name, value in build['source_sha256'].items():
        verify(ROOT/name, value)
    for name, value in build['artifacts'].items():
        verify(Path(data['build']['raw'])/name, value)
    for name, value in data['install']['result']['installed_files_sha256'].items():
        installed = Path(data['install']['result']['installed_avatar']).parent.parent/name
        verify(installed, value)
    for seal in data['archive']['old_seals']:
        manifest = ROOT/seal['path']
        verify(manifest, seal['sha256'])
        for name, value in read(manifest).items():
            verify(ROOT/seal['root']/name, value)
    for name, value in data['archive']['original_source_sha256'].items():
        verify(ROOT/name, value)
    for name, value in data['report_qa']['report_sha256'].items():
        verify(ROOT/name, value)
    for name in config['required_documents']:
        path = ROOT/name
        require(path.is_file() and path.stat().st_size > 0, 'missing document: '+name)
        checked[str(path)] = digest(path)
    files.update(checked)


def negative_controls(data, config):
    mutations = [
        ('pytest_failed', lambda d: d['python'].update(actual_returncode=1)),
        ('unknown_provider_wait', lambda d: d['native'].update(actual_provider_wait_code=None)),
        ('native_incomplete', lambda d: d['native'].update(completed_turns=1)),
        ('content_rejected', lambda d: d['content'].update(content_approved=False)),
        ('candidate_issue', lambda d: next(r for r in d['content']['rows'] if r['arm'] == 'candidate').update(issues=[{'category':'injected_control'}])),
        ('missing_review_row', lambda d: d['content']['rows'].pop()),
        ('build_failed', lambda d: d['build']['build_result'].update(passed=False)),
        ('install_failed', lambda d: d['install']['result'].update(passed=False)),
        ('wrong_hard_kill', lambda d: d['soak']['summary']['processes'][1].update(actual_wait_code=0)),
        ('missing_browser', lambda d: d['browser_batch']['stages'].pop()),
        ('asr_failed', lambda d: d['asr'].update(actual_returncode=1)),
        ('archive_changed', lambda d: d['archive'].update(modified_original_seals=1)),
        ('report_failed', lambda d: d['report_qa'].update(passed=False)),
        ('open_issue', lambda d: d['issues']['rows'][0].update(status='open'))]
    rejected = []
    for name, mutation in mutations:
        altered = copy.deepcopy(data)
        mutation(altered)
        try:
            check_facts(altered, config)
        except (ValueError, KeyError, TypeError):
            rejected.append(name)
        else:
            raise ValueError('negative control wrongly accepted: '+name)
    return rejected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(not args.output.exists(), 'fresh immutable output required')
    result = dict(formal_release_allowed=False, verifier_sha256=digest(Path(__file__)), source_ref=
                  subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip())
    try:
        config = read(args.manifest)
        require(REQUIRED <= set(config['proofs']), 'required proof missing')
        data = {name: read(ROOT/item['path']) for name, item in config['proofs'].items()}
        files = {}
        verify_files(data, config, files)
        check_facts(data, config)
        result.update(negative_controls_rejected=negative_controls(data, config), evidence_files_sha256=files,
                      manifest_sha256=digest(args.manifest), formal_release_allowed=True,
                      source_pause_after_publish=True, human_physical_multiday_approved=False,
                      scope='finite registered engineering/nonhuman release with explicit user deferrals; no universal semantic claim')
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result['error'] = repr(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'evidence_files_sha256'}, ensure_ascii=False))
    raise SystemExit(0 if result['formal_release_allowed'] else 1)


if __name__ == '__main__':
    main()

"""Keep the native study, later guard fix and historical artifacts distinct."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = HERE.parents[4]
OUT = HERE / '收尾核验'


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def git_digest(ref, name):
    return sha256(subprocess.check_output(['git', 'show', ref + ':' + name], cwd=ROOT)).hexdigest()


def verify():
    if sys.flags.optimize:
        raise RuntimeError('Run this evidence verifier without Python optimization')
    lab = HERE / '工作目录/001-当前请求范围与草稿忠实性v4'
    guard = HERE / '工作目录/002-冻结描述符执行期身份'
    historical = read(lab / 'full-source-binding.json')
    current = read(guard / 'fixed-source-binding.json')
    changed = {'scripts/evaluate_capability_pair.py', 'scripts/run_native_output_models.py',
               'scripts/lab/run_frozen_capability_job.py'}
    assert len(historical['source_sha256']) == 209 and len(current['source_sha256']) == 210
    assert digest(lab / 'python-full.log') == historical['log_sha256']
    assert '1489 passed, 1 skipped in 100.65s' in (lab / 'python-full.log').read_text()
    differences = set()
    for name, expected in historical['source_sha256'].items():
        assert git_digest('738af79', name) == expected
        if digest(ROOT / name) != expected:
            differences.add(name)
    assert differences == changed
    for name, expected in current['source_sha256'].items():
        assert git_digest('452a810', name) == digest(ROOT / name) == expected
    for folder in ('src/avatar', 'tests'):
        assert all(path.relative_to(ROOT).as_posix() in current['source_sha256']
                   for path in (ROOT / folder).rglob('*.py'))
    assert digest(guard / 'python-full-fixed.log') == current['log_sha256']
    assert '1496 passed, 1 skipped in 102.78s' in (guard / 'python-full-fixed.log').read_text()
    assert digest(guard / 'identity-fixed-first.log') == current['related_log_sha256']
    red = read(guard / 'before-source-binding.json')
    for name, expected in red['source_sha256'].items():
        assert git_digest('8fe9e4e', name) == expected
    assert len(red['observations']) == 4
    assert all(row['controlled_arm_boundaries'] == 24 and row['engineering_passed'] for row in red['observations'])
    fixed = read(guard / 'fixed-observations.json')
    assert all(row['controlled_arm_boundaries'] == 1 and not row['engineering_passed']
               and 'Frozen descriptor identity changed' in row['failure'] for row in fixed['source_identity_rows'][:3])
    assert fixed['source_identity_rows'][3]['controlled_arm_boundaries'] == 24
    handoff = fixed['supervisor_handoff'][0]
    assert handoff['expected_sha_in_command'] == handoff['context_sha'] == handoff['actual_sha']
    raw = read(guard / 'child-entry-negative-raw.json')
    assert raw['owned_temporary_directory_removed']
    assert raw['probe_source_sha256'] == digest(guard / 'probe_child_entries.py')
    assert git_digest('985ee2f', str((guard / 'probe_child_entries.py').relative_to(ROOT))) == raw['probe_source_sha256']
    assert len(raw['observations']) == 2
    assert all(row['returncode'] != 0 and not row['output_created']
               and 'Frozen descriptor identity changed' in row['stderr'] for row in raw['observations'])

    frozen_path = ROOT / 'evals/interaction/cycle-23/candidate-development-freeze-v4.json'
    frozen = read(frozen_path)
    assert digest(frozen_path) == git_digest('faf105f', str(frozen_path.relative_to(ROOT)))
    assert len(frozen['sha256']) == 235 and frozen['provider_backend'] == 'cuda'
    assert frozen['allowed_partition'] == 'development' and not frozen['prospective_execution_authorized']
    freeze_current_differences = set()
    for name, expected in frozen['sha256'].items():
        if name.startswith('data/g2-cycle-02/'):
            copy = lab / 'metadata-inputs' / Path(name).name
            assert digest(copy) == git_digest('2c2d26f', str(copy.relative_to(ROOT))) == expected
        else:
            assert git_digest('2c2d26f', name) == expected
        if digest(ROOT / name) != expected:
            freeze_current_differences.add(name)
    assert freeze_current_differences == changed
    retired = read(frozen_path.with_name('candidate-development-freeze-v4-retirement.json'))
    assert retired['freeze_sha256'] == digest(frozen_path)
    assert retired['status'] == 'completed_development_historical_only'
    prior = []
    for number, count in ((21, 432), (22, 81)):
        directory = BASE.parent / ('cycle-' + str(number))
        manifest_path = directory / '审计/证据清单.json'
        manifest = read(manifest_path)
        assert len(manifest) == count and all(digest(directory / name) == expected for name, expected in manifest.items())
        prior.append({'cycle': number, 'entries': count, 'manifest_sha256': digest(manifest_path), 'mismatches': 0})

    sys.path.insert(0, str(ROOT / 'scripts/lab'))
    import run_frozen_capability_job as jobs
    models = []
    for size, failures_after in (('4b', 1), ('14b', 0)):
        directory = BASE / '实验' / ('paired-cuda-development-' + size)
        lifecycle = read(directory / 'lifecycle.json')
        model = lifecycle['models'][0]
        assert lifecycle['completed'] and lifecycle['failure'] is None
        assert model['sampler_exit'] == model['provider_exit'] == 0 and model['cleanup_passed']
        assert jobs.process(model['provider_pid']) is None
        for name, expected in lifecycle['sourceSha256'].items():
            assert git_digest(lifecycle['head'], name) == expected
        job = jobs.status(BASE / '实验/jobs' / ('cuda-v4-' + size))
        assert job['state'] == 'completed' and job['return_code'] == 0
        assert not job['worker_verified_alive'] and not job['child_verified_alive']
        config = read(BASE / '实验/jobs' / ('cuda-v4-' + size) / 'config.json')
        assert config['controller_sha256'] == frozen['sha256']['scripts/lab/run_frozen_capability_job.py']
        assert '--expected-freeze-sha256' not in config['command']  # Completed before the later identity fix.
        ready = read(directory / model['model_id'] / 'provider-ready.json')
        assert ready['backend'] == 'cuda' and ready['chosen_gpu']['index'] == 2
        assert ready['effective_visible_devices'] == ready['chosen_gpu']['uuid']
        assert ready['provider_source_sha256'] == frozen['sha256']['scripts/serve_local_model_eval.py']
        sample_path = directory / model['model_id'] / 'sample/paired-output.json'
        sample = read(sample_path)
        summary_path = BASE / '实验' / (directory.name + '-summary.json')
        summary = read(summary_path)
        review = read(summary_path.with_name(directory.name + '-span-review.json'))
        assert digest(sample_path) == summary['sample_sha256'] == review['sample_sha256'] == retired['sample_sha256'][size]
        assert digest(summary_path) == review['summary_sha256']
        assert sample['candidateFreezeSha256'] == digest(frozen_path) and sample['sourceSha256'] == frozen['sha256']
        assert sample['execution_complete'] and sample['engineering_passed'] and sample['failure'] is None
        assert len(sample['cases']) == 24 and sum(len(c['turns']) for c in sample['cases']) == 40
        assert sample['generation_modes'] == {'llm': 32, 'rules': 2, 'rules_speaker_control': 4, 'rules_speaker_scope': 2}
        assert all(arm['turns'] == 20 and arm['generation_modes'] ==
                   {'llm': 16, 'rules': 1, 'rules_speaker_control': 2, 'rules_speaker_scope': 1}
                   for arm in summary['arms'].values())
        assert all(p['same_profile'] and p['same_reminder_state'] for p in summary['pairs'])
        assert review['baseline_primary_failure_turns'] == 6 and review['candidate_primary_failure_turns'] == failures_after
        assert not review['independent_human'] and not review['semantic_approved'] and not review['prospective_authorized']
        assert len(review['reviews']) == 20
        for pair, reviewed in zip(summary['pairs'], review['reviews']):
            for arm in ('baseline', 'candidate'):
                assert pair[arm + '_reply'] == reviewed[arm]['reply']
                assert sha256(reviewed[arm]['reply'].encode()).hexdigest() == reviewed[arm]['reply_sha256']
                assert all(f['source_span'] in reviewed[arm]['reply'] for f in reviewed[arm]['findings'])
        older_path = BASE.parent / 'cycle-22/实验' / (directory.name + '-summary.json')
        older = read(older_path)
        assert digest(older_path) == review['previous_v3_summary_sha256']
        assert sum(a['baseline_reply'] == b['baseline_reply'] for a, b in zip(summary['pairs'], older['pairs'])) == 20
        trace = [json.loads(line) for line in (directory / model['model_id'] / 'provider-trace.jsonl').read_text().splitlines()]
        assert len(trace) == 70 and all(row['outcome'] == 'completed' and row['finish_reason'] == 'stop' for row in trace)
        assert sum(bool(row['analysis']) for row in trace) == 36
        native = {row['id']: row for row in trace}
        verified = 0
        nonempty = 0
        for case in sample['cases']:
            assert case['completed'] and case['error'] is None
            for turn in case['turns']:
                result = turn['result']
                assert turn['stored_assistants'][-1] == result['reply'] and not result['tool_calls']
                assert result['trace']['verifier']['available'] is False
                if result['generation_mode'] != 'llm':
                    continue
                row = native[turn['native_provider']['id']]
                assert row == turn['native_provider'] and row['response'] == turn['visible'] == result['reply']
                if case['arm'] != 'candidate_lab_capability_prompt':
                    continue
                data = json.loads(row['messages'][0]['content'].rsplit('可信元数据如下：\n', 1)[1])
                assert data == turn['validated_source_capability'] and data['response_contract_version'] == 4
                assert data['current_user_source']['message_id'] == result['conversation']['user_message_id']
                assert data['current_user_source']['revision'] == result['conversation']['revision']
                records = turn['actual_local_receipts']
                fields = ('id', 'source_message_id', 'action', 'reminder_id', 'recorded_at')
                local = data['local_execution_evidence']
                assert local['items'] == [{key: r[key] for key in fields} for r in records[-20:]]
                assert local['has_more'] is (len(records) > 20)
                verified += 1
                nonempty += bool(records)
        assert verified == 16 and nonempty == 1
        models.append({'model_id': model['model_id'], 'application_replies': 40, 'pairs': 20,
                       'elapsed_seconds': sample['elapsedSeconds'], 'provider_completions_with_two_warmups': 70,
                       'source_sql_validated_turns': verified, 'nonempty_receipt_model_turns': nonempty,
                       'baseline_primary': 6, 'candidate_primary': failures_after,
                       'source_ref_before_later_guard': '738af79', 'gpu': ready['chosen_gpu'],
                       'job_started_utc': job['started_utc'], 'job_ended_utc': job['ended_utc'],
                       'provider_pid_absent': model['provider_pid'], 'owned_processes_stopped': True})
    assert datetime.fromisoformat(models[0]['job_ended_utc']) <= datetime.fromisoformat(models[1]['job_started_utc'])
    result = {'passed': True, 'verifier_optimize_flag': sys.flags.optimize,
              'scope': 'Native study, later identity guard and controlled fixtures are separate; agent semantic review not independent human gold.',
              'historical_model_stage_source_ref': '738af79', 'historical_model_full_python': historical['result'],
              'historical_frozen_inputs': 235, 'historical_freeze_ref': '2c2d26f',
              'current_guard_source_ref': '452a810', 'current_full_python': current['result'],
              'current_source_test_files': 210, 'only_historical_to_current_changed_files': sorted(changed),
              'prior_manifests': prior, 'models': models, 'overall_candidate_rejected': True,
              'prospective_authorized': False, 'semantic_approved': False, 'physical_device_approved': False,
              'generational_leap_approved': False}
    OUT.mkdir(exist_ok=True)
    output = OUT / '阶段来源与系统收尾核验.json'
    value = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
    if output.exists():
        assert output.read_bytes() == value
    else:
        output.write_bytes(value)
    print('Verified:historical235 native inputs,80 replies/32 SQL bindings,current210 sources/full1496;v4 rejected')


if __name__ == '__main__':
    verify()

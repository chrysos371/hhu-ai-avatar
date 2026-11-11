"""Cross-check fixed entry guards and both completed source-frozen GPU cohorts."""
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
    first = HERE / '工作目录/001-实验入口执行契约'
    before = read(first / 'before-source-binding.json')
    fixed = read(first / 'fixed-source-binding.json')
    for name, expected in before['source_sha256'].items():
        assert git_digest('1ca82d4', name) == expected
    for name, expected in fixed['source_sha256'].items():
        assert git_digest('4fcaf20', name) == expected
    assert digest(first / 'entry-contract-fixed.log') == fixed['fixed_test_log_sha256']
    observations = read(first / 'fixed-observations.json')['observations']
    assert len(observations) == 20
    assert all(row['controlled_boundary_calls'] == 1 for row in before['observations'])
    assert all(row['controlled_boundary_calls'] == 0 and not row['output_created']
               and row['error_type'] == 'ValueError' for row in observations[:14])
    assert all(row['controlled_boundary_calls'] == 1 for row in observations[14:])

    work = HERE / '工作目录/002-一般能力与本地回执候选v3'
    full = read(work / 'full-source-binding.json')
    assert digest(work / 'python-full.log') == full['log_sha256']
    assert '1481 passed, 1 skipped in 101.02s' in (work / 'python-full.log').read_text()
    for name, expected in full['source_sha256'].items():
        assert git_digest('9d9229f', name) == digest(ROOT / name) == expected, name
    for folder in ('src/avatar', 'tests'):
        assert all(path.relative_to(ROOT).as_posix() in full['source_sha256']
                   for path in (ROOT / folder).rglob('*.py'))
    erroneous = read(work / 'first-test-binding.json')
    assert digest(work / 'test-receipt-first.py.txt') == erroneous['source_sha256']['tests/test_receipt_capability_prompt_lab.py']

    freeze_path = ROOT / 'evals/interaction/cycle-22/candidate-development-freeze-v3.json'
    freeze = read(freeze_path)
    assert len(freeze['sha256']) == 230
    assert freeze['provider_backend'] == 'cuda' and freeze['allowed_partition'] == 'development'
    assert not freeze['prospective_execution_authorized'] and not freeze['production_activation_approved']
    for name, expected in freeze['sha256'].items():
        if name.startswith('data/g2-cycle-02/'):
            historical = work / 'metadata-inputs' / Path(name).name
            assert digest(historical) == expected
            assert git_digest('96eb2d0', str(historical.relative_to(ROOT))) == expected
        else:
            assert git_digest('96eb2d0', name) == expected, name
        assert digest(ROOT / name) == expected, name
    retired = read(freeze_path.with_name('candidate-development-freeze-v3-retirement.json'))
    assert retired['freeze_sha256'] == digest(freeze_path)
    assert retired['status'] == 'completed_development_historical_only'
    old = BASE.parent / 'cycle-21'
    old_manifest = read(old / '审计/证据清单.json')
    assert len(old_manifest) == 432
    assert all(digest(old / name) == expected for name, expected in old_manifest.items())

    sys.path.insert(0, str(ROOT / 'scripts/lab'))
    import run_frozen_capability_job as jobs
    models = []
    for size, primary_after in (('4b', 1), ('14b', 0)):
        directory = BASE / '实验' / ('paired-cuda-development-' + size)
        lifecycle = read(directory / 'lifecycle.json')
        model = lifecycle['models'][0]
        assert lifecycle['completed'] and lifecycle['failure'] is None
        assert model['sampler_exit'] == model['provider_exit'] == 0 and model['cleanup_passed']
        assert jobs.process(model['provider_pid']) is None
        for name, expected in lifecycle['sourceSha256'].items():
            assert git_digest(lifecycle['head'], name) == expected
        job = jobs.status(BASE / '实验/jobs' / ('cuda-v3-' + size))
        assert job['state'] == 'completed' and job['return_code'] == 0
        assert not job['worker_verified_alive'] and not job['child_verified_alive']
        config = read(BASE / '实验/jobs' / ('cuda-v3-' + size) / 'config.json')
        assert config['controller_sha256'] == freeze['sha256']['scripts/lab/run_frozen_capability_job.py']
        ready = read(directory / model['model_id'] / 'provider-ready.json')
        assert ready['backend'] == 'cuda' and ready['chosen_gpu']['index'] == 0
        assert ready['provider_source_sha256'] == freeze['sha256']['scripts/serve_local_model_eval.py']
        assert ready['effective_visible_devices'] == ready['chosen_gpu']['uuid']
        sample_path = directory / model['model_id'] / 'sample/paired-output.json'
        sample = read(sample_path)
        summary_path = BASE / '实验' / (directory.name + '-summary.json')
        summary = read(summary_path)
        review = read(summary_path.with_name(directory.name + '-span-review.json'))
        assert digest(sample_path) == summary['sample_sha256'] == review['sample_sha256'] == retired['sample_sha256'][size]
        assert digest(summary_path) == review['summary_sha256']
        assert sample['candidateFreezeSha256'] == digest(freeze_path)
        assert sample['sourceSha256'] == freeze['sha256']
        assert sample['execution_complete'] and sample['engineering_passed'] and sample['failure'] is None
        assert len(sample['cases']) == 24 and sum(len(c['turns']) for c in sample['cases']) == 40
        assert all(p['same_profile'] and p['same_reminder_state'] for p in summary['pairs'])
        assert review['baseline_primary_failure_turns'] == 6 and review['candidate_primary_failure_turns'] == primary_after
        assert not review['independent_human'] and not review['prospective_authorized'] and not review['semantic_approved']
        assert len(review['reviews']) == 20
        for pair, reviewed in zip(summary['pairs'], review['reviews']):
            for arm in ('baseline', 'candidate'):
                assert pair[arm + '_reply'] == reviewed[arm]['reply']
                assert sha256(reviewed[arm]['reply'].encode()).hexdigest() == reviewed[arm]['reply_sha256']
                for finding in reviewed[arm]['findings']:
                    assert finding['source_span'] in reviewed[arm]['reply']
        trace = [json.loads(line) for line in (directory / model['model_id'] / 'provider-trace.jsonl').read_text().splitlines()]
        assert len(trace) == 70 and all(t['outcome'] == 'completed' and t['finish_reason'] == 'stop' for t in trace)
        native = {row['id']: row for row in trace}
        verified = 0
        with_receipts = 0
        for case in sample['cases']:
            assert case['completed'] and case['error'] is None
            for turn in case['turns']:
                result = turn['result']
                assert turn['stored_assistants'][-1] == result['reply']
                assert not result['tool_calls'] and result['trace']['verifier']['available'] is False
                if result['generation_mode'] != 'llm':
                    continue
                row = native[turn['native_provider']['id']]
                assert row == turn['native_provider']
                assert turn['visible'] == row['response'] == result['reply']
                if case['arm'] != 'candidate_lab_capability_prompt':
                    continue
                data = json.loads(row['messages'][0]['content'].rsplit('可信元数据如下：\n', 1)[1])
                assert data == turn['validated_source_capability']
                assert data['response_contract_version'] == 3
                assert data['current_user_source']['message_id'] == result['conversation']['user_message_id']
                assert data['current_user_source']['revision'] == result['conversation']['revision']
                local = data['local_execution_evidence']
                sql = turn['actual_local_receipts']
                fields = ('id', 'source_message_id', 'action', 'reminder_id', 'recorded_at')
                assert local['items'] == [{key: record[key] for key in fields} for record in sql[-20:]]
                assert local['has_more'] is (len(sql) > 20)
                verified += 1
                with_receipts += bool(sql)
        assert verified == 16 and with_receipts == 1
        models.append({'model_id': model['model_id'], 'sample_sha256': digest(sample_path),
                       'elapsed_seconds': sample['elapsedSeconds'], 'application_replies': 40, 'pairs': 20,
                       'provider_completions_including_two_warmups': 70, 'source_sql_validated_turns': verified,
                       'nonempty_local_receipt_model_turns': with_receipts, 'baseline_primary': 6,
                       'candidate_primary': primary_after, 'provider_pid_absent': model['provider_pid'],
                       'job_completed_and_processes_stopped': True})
    result = {'passed': True, 'scope': 'Engineering and raw-native/source/SQL evidence validation; agent semantic review separate.',
              'fixed_entry_negative_cases': 14, 'fixed_entry_positive_cases': 6,
              'full_python_result': full['result'], 'current_source_files_bound_to_full_ref': len(full['source_sha256']),
              'full_source_ref': '9d9229f', 'historical_freeze_ref': '96eb2d0', 'historical_frozen_inputs': 230,
              'previous_cycle432_artifacts_unchanged': True, 'previous_manifest_sha256': digest(old / '审计/证据清单.json'),
              'models': models, 'overall_candidate_rejected': True, 'prospective_authorized': False,
              'general_semantic_approved': False, 'physical_device_approved': False, 'generational_leap_approved': False}
    OUT.mkdir(exist_ok=True)
    output = OUT / '全轮来源与收尾核验.json'
    encoded = (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode()
    if output.exists():
        assert output.read_bytes() == encoded
    else:
        output.write_bytes(encoded)
    print('Verified:207 source/test files,230 frozen inputs,2 models/80 replies,32 source-SQL bindings; candidate rejected')


if __name__ == '__main__':
    verify()

"""Read-only audit of completed C21 inputs; write only new delivery evidence.

Historical canonical documents may evolve. Only the two explicitly named
inputs of the action stage may use their original Git bytes as evidence.
Frozen phase artifacts must still match the live archive exactly.
"""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = HERE.parents[4]
OUT = HERE / '交付核验'
STAGES = {
    '隐私阶段证据清单.json': 23,
    '独立修复证据清单.json': 40,
    '本地动作修复证据清单.json': 25,
    '动作回执阶段证据清单.json': 58,
    '认知事实阶段证据清单.json': 26,
    '导航音频阶段证据清单.json': 39,
    '集成阶段证据清单.json': 62,
}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def git_bytes(ref, name):
    return subprocess.check_output(['git', 'show', f'{ref}:{name}'], cwd=ROOT)


def write_once(path, value):
    """Re-execution verifies sealed bytes rather than silently rewriting them."""
    if path.exists():
        assert path.read_bytes() == value, path
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)


def verify():
    historical = {'docs/backend.md', 'docs/本地动作回执.md'}
    stages = []
    unique = {}
    for name, count in STAGES.items():
        manifest = read(HERE / name)
        assert len(manifest) == count
        old_docs = []
        for relative, expected in manifest.items():
            path = (BASE / relative).resolve()
            assert path.is_relative_to(ROOT)
            project_name = path.relative_to(ROOT).as_posix()
            if digest(path) != expected:
                assert name == '动作回执阶段证据清单.json'
                assert project_name in historical
                value = git_bytes('b090960', project_name)
                assert sha256(value).hexdigest() == expected
                copy = OUT / '历史规范文档/b090960' / project_name
                write_once(copy, value)
                old_docs.append({'path': project_name, 'git_ref': 'b090960',
                                 'sha256': expected, 'copy': str(copy.relative_to(BASE))})
            unique[(project_name, expected)] = True
        stages.append({'manifest': name, 'entries': count,
                       'sha256': digest(HERE / name),
                       'frozen_artifact_mismatches': 0, 'historical_canonical_docs': old_docs})

    # Source identity, not a claim that full regressions were rerun after merge.
    core = read(HERE / '工作目录/011-集成与系统复核/integration-regression-binding.json')
    front = read(HERE / '工作目录/012-导航音频释放时序/frontend-fixed-binding.json')
    bindings = {}
    for record, prefixes, ref in ((core, ('src/avatar/', 'tests/'), '81b8dda'),
                                   (front, ('frontend/',), '96c73ca')):
        for name, expected in record['source_sha256'].items():
            if name.startswith(prefixes):
                assert digest(ROOT / name) == expected, name
                assert sha256(git_bytes(ref, name)).hexdigest() == expected
                bindings[name] = {'sha256': expected, 'git_ref': ref}
    for folder in ('src/avatar', 'tests'):
        for path in (ROOT / folder).rglob('*.py'):
            assert path.relative_to(ROOT).as_posix() in bindings, path
    runtime = read(OUT / 'browser-main-runtime.json')
    assert runtime == read(OUT / 'actions-main-runtime.json')
    assert runtime['project_root'] == str(ROOT)
    for module, path in runtime['module_paths'].items():
        local = Path(path)
        assert local.is_relative_to(ROOT / 'src')
        assert digest(local) == runtime['module_sha256'][module]
    assert runtime['frontend_sha256'] == front['bundle_sha256']
    for name, expected in runtime['frontend_sha256'].items():
        assert digest(ROOT / name) == expected
    assert '15 passed (36.1s)' in (OUT / 'browser-default-main.log').read_text()
    assert '13 skipped' in (OUT / 'browser-default-main.log').read_text()
    assert '1 passed (4.9s)' in (OUT / 'actions-main.log').read_text()
    assert read(OUT / 'actions-main/receipt-browser.json')['completed']

    freeze_path = ROOT / 'evals/interaction/cycle-21/candidate-development-freeze-v2-cpu.json'
    freeze = read(freeze_path)
    assert len(freeze['sha256']) == 254
    for name, expected in freeze['sha256'].items():
        # The retired descriptor is historical; current product is intentionally newer.
        assert sha256(git_bytes('3eeebfc', name)).hexdigest() == expected, name
    retired = read(freeze_path.with_name('candidate-development-freeze-v2-cpu-retirement.json'))
    assert retired['freeze_sha256'] == digest(freeze_path)
    assert retired['status'] == 'completed_development_historical_only'
    assert not retired['production_activation_approved']
    models = []
    for suffix, baseline, candidate in (('4b', 6, 4), ('14b-attempt02', 5, 2)):
        directory = BASE / '实验' / ('paired-cpu-development-' + suffix)
        lifecycle = read(directory / 'lifecycle.json')
        assert lifecycle['completed'] and lifecycle['failure'] is None
        model = lifecycle['models'][0]
        assert model['sampler_exit'] == model['provider_exit'] == 0 and model['cleanup_passed']
        provider = read(directory / model['model_id'] / 'provider-ready.json')
        assert provider['backend'] == 'cpu_explicit' and provider['effective_visible_devices'] == '-1'
        assert not provider['process_gpu_mib_after_load']
        assert provider['configuration']['n_threads'] == provider['configuration']['n_threads_batch'] == 4
        assert provider['configuration']['n_gpu_layers'] == 0 and not provider['configuration']['offload_kqv']
        sample_path = directory / model['model_id'] / 'sample/paired-output.json'
        sample = read(sample_path)
        summary_path = BASE / '实验' / (directory.name + '-summary.json')
        summary = read(summary_path)
        review = read(summary_path.with_name(directory.name + '-span-review.json'))
        assert sample['execution_complete'] and sample['engineering_passed'] and sample['failure'] is None
        assert digest(sample_path) == summary['sample_sha256'] == review['sample_sha256']
        assert digest(summary_path) == review['summary_sha256']
        assert summary['candidate_freeze_sha256'] == digest(freeze_path)
        assert review['baseline_primary_failure_turns'] == baseline
        assert review['candidate_primary_failure_turns'] == candidate
        assert not review['independent_human'] and not review['model_self_score']
        assert not review['prospective_authorized'] and not review['production_activation_approved']
        assert len(summary['pairs']) == 20
        assert all(p['same_profile'] and p['same_reminder_state'] for p in summary['pairs'])
        trace = [json.loads(line) for line in (directory / model['model_id'] / 'provider-trace.jsonl').read_text().splitlines()]
        assert len(trace) == summary['provider_calls'] == 70
        assert all(t['outcome'] == 'completed' and t['finish_reason'] == 'stop' for t in trace)
        models.append({'model_id': model['model_id'], 'application_replies': 40, 'pairs': 20,
                       'provider_calls_including_two_warmups': 70,
                       'elapsed_seconds': sample['elapsedSeconds'], 'sample_sha256': digest(sample_path),
                       'baseline_explicit_failure_turns': baseline, 'candidate_explicit_failure_turns': candidate,
                       'baseline_contextual_pending_separately': review.get('baseline_contextual_pending_turns_separately', 0),
                       'decision': 'reject_candidate', 'provider_exit': 0, 'cleanup_passed': True})
    result = {'passed': True, 'scope': 'Completed C21 delivery; historical native study and current engineering source are separate.',
              'stages': stages, 'unique_stage_path_sha_pairs': len(unique),
              'current_source_bindings': bindings, 'main_runtime_project_root': runtime['project_root'],
              'main_bundle_matches_integrated_bundle': True, 'cpu_freeze_historical_inputs': 254,
              'cpu_freeze_git_ref': '3eeebfc', 'cpu_freeze_retired': True, 'models': models,
              'general_semantic_approved': False, 'physical_device_approved': False,
              'generational_leap_approved': False}
    write_once(OUT / '全轮证据复核.json', (json.dumps(result, ensure_ascii=False, indent=2) + '\n').encode())
    print(json.dumps({'passed': True, 'stages': len(stages), 'unique_stage_path_sha_pairs': len(unique),
                      'source_bindings': len(bindings), 'models': len(models)}, ensure_ascii=False))


if __name__ == '__main__':
    verify()

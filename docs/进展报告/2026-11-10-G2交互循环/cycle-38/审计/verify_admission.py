"""Zero-native C38 admission from current Git/tests, controlled wire and CLI negatives."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from native_common import ROOT, BASE, PROTOCOL, REGISTRY, WORK, RUNTIME, ADMISSION, digest, read
from native_wire_relay import parse_wire
from avatar.paths import project_data_root


def history(ref, names):
    raw = subprocess.check_output(['git', 'archive', '--format=tar', ref, '--', *sorted(names)], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


def main():
    assert not ADMISSION.exists()
    directory = ADMISSION.parent
    binding_path = directory/'admission-python-final-binding.json'
    binding = read(binding_path)
    assert binding['exit_code'] == 0 and binding['source_unchanged']
    assert len(binding['source_git_sha256']) == 434
    assert history(binding['head'], binding['source_git_sha256']) == binding['source_git_sha256']
    assert all(digest(ROOT/n) == sha for n, sha in binding['source_git_sha256'].items())
    assert digest(directory/'admission-python-final.log') == binding['log_sha256']
    assert '1958 passed, 1 skipped' in (directory/'admission-python-final.log').read_text()
    controlled_path = directory/'controlled-sampler-preflight-scope-label/evaluation.json'
    controlled = read(controlled_path)
    assert controlled['completed'] and controlled['failure'] is None and controlled['native_or_gpu_calls'] == 0
    assert controlled['actual_app_results'] == 44 and controlled['controlled_http_requests'] == 97 and controlled['provider_closed']
    assert all(a['completed'] and a['server_closed'] and not a['failure'] for a in controlled['arms'])
    assert all(digest(ROOT/n) == sha for n, sha in controlled['source_sha256'].items())
    assert history(controlled['execution_head'], controlled['source_sha256']) == controlled['source_sha256']
    wire = [json.loads(line) for line in (controlled_path.parent/'wire.jsonl').read_text().splitlines()]
    assert len(wire) == len(controlled['fixture_requests']) == 97
    for row, fixture in zip(wire, controlled['fixture_requests'], strict=True):
        assert row['actual_native'] is False
        assert row['request'] == json.loads(fixture['raw_request'])
        assert hashlib.sha256(row['raw_request_json'].encode()).hexdigest() == row['request_body_sha256']
        assert hashlib.sha256(row['raw_http_body'].encode()).hexdigest() == row['response_body_sha256']
        assert parse_wire(row)['finish_reason'] == 'stop'
    assigned = []
    fixed = 0
    for arm in controlled['arms']:
        dump = controlled_path.parent/(arm['id']+'-'+arm['arm']+'.sql')
        assert digest(dump) == arm['sql_dump_sha256']
        for turn in arm['turns']:
            assigned.extend(turn['native_ordinals'])
            result = turn['result']
            assert turn['final_display_reply'] == result['reply'] == turn['stored_assistants'][-1]['content']
            if result['generation_mode'] in ('llm', 'reviewed_response'):
                assert turn['visible'] == result['reply']
            review = result.get('response_review')
            if review and review['fixed_renderer_used']:
                fixed += 1
                assert review['source_message_ids'] and not result['tool_calls']
    assert sorted(assigned) == list(range(1, 98)) and fixed == 8
    runtime = read(RUNTIME)
    assert len(runtime['files_sha256']) == 54 and runtime['model_inference_calls'] == 0
    assert all(digest(Path(n)) == sha for n, sha in runtime['files_sha256'].items())
    protocol = read(PROTOCOL)
    base = {'version': 1, 'scope': 'isolated_typed_capability_paired_development',
        'candidate': 'lab_typed_capability_gate_v1', 'execution_authorized': True,
        'allowed_partition': 'development', 'protected_execution_authorized': False, 'provider_backend': 'cuda',
        'models': ['qwen3-4b-q4_k_m'], 'protocol': str(PROTOCOL.relative_to(ROOT)),
        'models_registry': str(REGISTRY.relative_to(ROOT)), 'registry_sha256': digest(REGISTRY),
        'case_ids': [c['id'] for c in protocol['development_cases']],
        'turn_count_per_arm': 22, 'repetitions': 3}
    negatives = []
    with tempfile.TemporaryDirectory(prefix='c38-entry-negative-', dir=project_data_root(ROOT)/'tmp') as folder:
        folder = Path(folder)
        for name, mutate in [('parent_sha', {}), ('wrong_candidate', {'candidate': 'old_v4'}),
                             ('protected', {'allowed_partition': 'protected', 'protected_execution_authorized': True}),
                             ('cpu_substitution', {'provider_backend': 'cpu_explicit'})]:
            descriptor = folder/(name+'.json')
            descriptor.write_text(json.dumps({**base, **mutate}))
            expected = '0'*64 if name == 'parent_sha' else digest(descriptor)
            command = [sys.executable, str(BASE/'审计/run_pairs.py'), '--model', 'qwen3-4b-q4_k_m',
                '--repetition', '1', '--freeze', str(descriptor), '--expected-freeze-sha256', expected]
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            assert result.returncode != 0
            reason = 'descriptor bytes changed' if name == 'parent_sha' else 'execution contract differs'
            assert reason in result.stderr
            assert not (BASE/'实验/paired-4b-r1').exists()
            negatives.append({'control': name, 'argv': command, 'exit_code': result.returncode,
                'stdout': result.stdout, 'stderr': result.stderr, 'rejected_before_output_or_provider': True})
    seals = []
    for p in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(p.parents[1].name[6:]) >= 38:
            continue
        assert all(digest(p.parents[1]/n) == sha for n, sha in read(p).items())
        seals.append({'cycle': p.parents[1].name, 'items': len(read(p)), 'sha256': digest(p)})
    assert len(seals) == 35 and sum(r['items'] for r in seals) == 6124
    assert seals[-1]['sha256'] == 'f76e5bb390b80aff83a5ef4f43ea5a017acb14cc427e36a87542eff50d0c3416'
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration) == '717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    assert all(digest(migration.parent/n) == sha for n, sha in read(migration).items())
    result = {'verified': True, 'scope': 'controlled_software_engineering_admission_only_NOT_native_semantic_gate',
        'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'verifier_sha256': digest(Path(__file__)), 'full_python_binding_sha256': digest(binding_path),
        'full_python_result': '1958 passed/1 skipped', 'current_selected_inputs': 434,
        'scripted_preflight_sha256': digest(controlled_path), 'controlled_app_results': 44,
        'controlled_HTTP_calls': 97, 'scripted_fixed_responses': 8, 'new_native_calls': 0,
        'owned_controlled_resources_closed': True, 'native_runtime_files': 54,
        'descriptor_negatives': negatives, 'historical_cycle_seals': seals,
        'old_seals_total_including_migration': 36, 'old_entries_including_migration': 6212,
        'semantic_or_production_approval': False, 'protected_execution_authorized': False}
    ADMISSION.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print('C38 engineering admission:1958/1;434inputs;44controlled app/97HTTP;4real CLI negatives;54runtime;36seals;0native')


if __name__ == '__main__':
    main()

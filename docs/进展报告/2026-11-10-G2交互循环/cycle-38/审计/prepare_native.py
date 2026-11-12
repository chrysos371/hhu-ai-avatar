"""Record installed identity before clean committed C38 development freeze."""
import argparse
import json
import subprocess
from native_common import ROOT, PROTOCOL, REGISTRY, WORK, RUNTIME, digest, read, capture_runtime, required_inputs, verify_source


def main(action):
    WORK.mkdir(parents=True, exist_ok=True)
    if action == 'runtime':
        assert not RUNTIME.exists()
        RUNTIME.write_text(json.dumps(capture_runtime(), ensure_ascii=False, indent=2)+'\n')
        print('Captured54 runtime files;0model calls;commit before freezing')
        return
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip(), 'Commit before freezing'
    protocol = read(PROTOCOL)
    cases = protocol['development_cases']
    frozen = {'version': 1, 'scope': 'isolated_typed_capability_paired_development',
        'candidate': 'lab_typed_capability_gate_v1', 'execution_authorized': True,
        'allowed_partition': 'development', 'protected_execution_authorized': False, 'provider_backend': 'cuda',
        'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'protocol': str(PROTOCOL.relative_to(ROOT)), 'models_registry': str(REGISTRY.relative_to(ROOT)),
        'registry_sha256': digest(REGISTRY), 'models': ['qwen3-4b-q4_k_m'],
        'case_ids': [c['id'] for c in cases], 'turn_count_per_arm': sum(len(c['turns']) for c in cases),
        'repetitions': protocol['sampling']['repetitions'], 'sha256': {n: digest(ROOT/n) for n in sorted(required_inputs())}}
    path = WORK/'execution-freeze.json'
    assert not path.exists()
    path.write_text(json.dumps(frozen, ensure_ascii=False, indent=2)+'\n')
    verify_source(path, digest(path))
    print('C38 frozen', len(frozen['sha256']), 'inputs;SHA', digest(path))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('runtime', 'freeze'))
    main(parser.parse_args().action)

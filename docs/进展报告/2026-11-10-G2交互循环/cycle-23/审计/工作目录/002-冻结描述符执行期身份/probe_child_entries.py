"""Archive raw OS-child rejection evidence without loading a model."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from evaluate_capability_pair import required_sources


def probe():
    observations = []
    with tempfile.TemporaryDirectory(prefix='freeze-child-proof-', dir=ROOT.parent / 'runtime/tmp') as name:
        folder = Path(name)
        descriptor = {'candidate': 'lab_source_capability_v4', 'provider_backend': 'cuda',
                      'execution_authorized': True, 'allowed_partition': 'development',
                      'prospective_execution_authorized': False, 'scope': 'Before parent handoff',
                      'sha256': {p: sha256((ROOT / p).read_bytes()).hexdigest()
                                 for p in sorted(required_sources('lab_source_capability_v4'))}}
        freeze = folder / 'freeze.json'
        freeze.write_text(json.dumps(descriptor))
        expected = sha256(freeze.read_bytes()).hexdigest()
        descriptor['scope'] = 'Changed between parent and child'
        freeze.write_text(json.dumps(descriptor))
        current = sha256(freeze.read_bytes()).hexdigest()
        assert expected != current
        for entry in ('runner', 'sampler'):
            output = folder / (entry + '-must-not-exist')
            command = [sys.executable, str(ROOT / 'scripts' / ('run_native_output_models.py' if entry == 'runner'
                                                              else 'evaluate_capability_pair.py')),
                       '--candidate-freeze', str(freeze), '--expected-freeze-sha256', expected,
                       '--protocol', str(ROOT / 'evals/interaction/cycle-23/capability-output-protocol.json'),
                       '--pair-protocol', str(ROOT / 'evals/interaction/cycle-23/paired-capability-protocol.json'),
                       '--partition', 'development', '--output', str(output)]
            if entry == 'runner':
                command += ['--provider-python', sys.executable, '--stage', 'capability_pair',
                            '--candidate', 'source_capability_v4', '--backend', 'cuda', '--model-key', 'qwen3-4b-q4_k_m']
            else:
                command += ['--provider', str(folder / 'nonexistent-provider.json'),
                            '--trace', str(folder / 'unused-trace'), '--candidate', 'lab_source_capability_v4']
            result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            assert result.returncode != 0 and 'Frozen descriptor identity changed' in result.stderr
            assert not output.exists()
            observations.append({'entry': entry, 'argv': command, 'returncode': result.returncode,
                                 'stdout': result.stdout, 'stderr': result.stderr,
                                 'expected_sha256': expected, 'actual_sha256': current,
                                 'output_created': output.exists()})
    evidence = {'scope': 'Two actual OS children reject stale parent SHA before output/provider metadata/model load. No model, GPU allocation, HTTP or SQL operation.',
                'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'probe_source_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
                'owned_temporary_directory_removed': not folder.exists(), 'observations': observations}
    with (HERE / 'child-entry-negative-raw.json').open('x') as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print('Archived two real child exits; no output/model; owned directory removed')


if __name__ == '__main__':
    probe()

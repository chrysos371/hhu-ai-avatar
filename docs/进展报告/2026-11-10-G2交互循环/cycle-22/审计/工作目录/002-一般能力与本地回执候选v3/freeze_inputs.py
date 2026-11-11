"""Create a fresh CUDA development-only freeze after full source-bound tests."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[6]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'scripts'))
from evaluate_capability_pair import required_sources, verify_freeze, validate_execution_contract


def freeze():
    binding = json.loads((WORK / 'full-source-binding.json').read_text())
    for name, expected in binding['source_sha256'].items():
        assert sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
    assert binding['result'] == '1481 passed, 1 skipped in 101.02s'
    selected = 'lab_source_capability_v3'
    names = required_sources(selected) | {
        str(path.relative_to(ROOT)) for path in (ROOT / 'tests').rglob('*.py')}
    names |= {'scripts/lab/run_frozen_capability_job.py', 'scripts/summarize_capability_pair.py',
              'evals/interaction/cycle-21/cpu-capability-output-protocol.json',
              'data/g2-cycle-02/gguf-metadata.json', 'data/g2-cycle-02/qwen14b-gguf-metadata.json'}
    for name in ('计划.md', 'related-fixed.log', 'python-full.log', 'full-source-binding.json',
                 'freeze_inputs.py', 'metadata-inputs/gguf-metadata.json', 'metadata-inputs/qwen14b-gguf-metadata.json'):
        names.add(str((WORK / name).relative_to(ROOT)))
    for name in ('gguf-metadata.json', 'qwen14b-gguf-metadata.json'):
        assert (ROOT / 'data/g2-cycle-02' / name).read_bytes() == (WORK / 'metadata-inputs' / name).read_bytes()
    descriptor = {
        'candidate': selected, 'source_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'default_runtime_git_ref': '9d9229f', 'full_python_regression': binding['result'],
        'provider_backend': 'cuda', 'execution_authorized': True, 'allowed_partition': 'development',
        'prospective_execution_authorized': False, 'production_activation_approved': False,
        'semantic_approved': False, 'scope': 'Fresh current-product known12/20 baseline-v3 pairs; bounded SQL metadata, no output rewrite, one owned CUDA provider; no historical CPU/GPU equivalence or independent human gold.',
        'sha256': {name: sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(names)},
    }
    protocol = json.loads((ROOT / 'evals/interaction/cycle-22/capability-output-protocol.json').read_text())
    validate_execution_contract(descriptor, protocol, 'cuda')
    output = ROOT / 'evals/interaction/cycle-22/candidate-development-freeze-v3.json'
    with output.open('x') as stream:
        json.dump(descriptor, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    assert verify_freeze(output, 'development', selected) == descriptor
    print(len(names), 'frozen inputs;', sha256(output.read_bytes()).hexdigest())


if __name__ == '__main__':
    freeze()

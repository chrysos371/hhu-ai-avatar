"""Actual subprocess rejection controls; never create an output, DB or GPU provider."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE / '审计/工作目录/001-自动情绪版本失效'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


freeze = WORK / 'native-after-freeze.json'
before = BASE / '实验/native-before-v2-4b/evaluation.json'
base = [sys.executable, str(BASE / '审计/run_native_revision.py'), '--phase', 'after',
    '--model', 'qwen3-4b-q4_k_m', '--freeze', str(freeze), '--expected-freeze-sha256', sha(freeze),
    '--provider-python', str(ROOT.parent / 'envs/hhu-ai-avatar-llm/bin/python')]
cases = [
    ('missing_before', [], 'After requires pinned same-model completed before evidence'),
    ('wrong_before_sha', ['--before', str(before), '--before-sha256', '0' * 64],
     'After requires pinned same-model completed before evidence'),
    ('wrong_phase', ['--phase', 'before'], 'Emotion revision phase mismatch'),
    ('before_as_after_prior', ['--model', 'qwen3-32b-q4_k_m', '--prior-4b', str(before),
     '--prior-4b-sha256', sha(before)], 'AssertionError'),
]
report = {'scope': 'actual_subprocess_after_admission_negative_controls',
    'actual_native_model_or_gpu': False, 'script_sha256': sha(Path(__file__)),
    'freeze_sha256': sha(freeze), 'cases': []}
for name, extra, expected in cases:
    output = ROOT.parent / 'runtime/tmp' / ('c34-after-reject-' + name)
    assert not output.exists()
    command = base + ['--output', str(output)] + extra
    completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, timeout=20)
    assert completed.returncode != 0 and expected in completed.stdout and not output.exists()
    report['cases'].append({'name': name, 'argv': command, 'exit_code': completed.returncode,
        'stdout': completed.stdout, 'expected_rejection': expected, 'output_not_created': True})
target = WORK / 'after-admission-controls.json'
with target.open('x') as stream:
    json.dump(report, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('4 real subprocess after-admission negative controls passed; no output/DB/provider created.')

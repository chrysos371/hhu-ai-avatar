"""Production promotion must retain the measured finite classifier exactly."""
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from avatar.brain.reminder_query_targets import derive_read_target
from avatar.lab.source_read_dispatch import derive_read_target as laboratory_target

PROTOCOL = json.loads((Path(__file__).resolve().parents[1] /
    'evals/interaction/cycle-44/source-read-dispatch-trial-protocol.json').read_text())
CASES = PROTOCOL['development_cases'] + PROTOCOL['protected_cases']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_previously_seen_registered_material_has_identical_target_and_evidence(case):
    assert asdict(derive_read_target(case['text'])) == asdict(laboratory_target(case['text']))


@pytest.mark.parametrize('text', [
    '“提醒编号1现在是什么状态？”', '`提醒编号1状态？`',
    '~~~\n提醒编号1状态？', '提醒编号1和提醒编号2状态？',
    '提醒编号１状态？', '提醒编号9223372036854775808状态？',
    '提醒编号1现在取消了吗？', '现在取消提醒编号1',
    '请不要查询提醒编号1', '请写一句提醒编号1的状态',
])
def test_quotes_code_parameter_bounds_and_write_frames_remain_equivalent(text):
    assert asdict(derive_read_target(text)) == asdict(laboratory_target(text))


@pytest.mark.parametrize('text', ['', 'x' * 2001, None, True])
def test_mode_text_is_bounded(text):
    with pytest.raises(ValueError):
        derive_read_target(text)

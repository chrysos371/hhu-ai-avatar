import importlib.util
import json
from pathlib import Path

import pytest

from avatar.config import config

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('mixed_writer_audit', ROOT/'scripts/lab/audit_mixed_writer_authority.py')
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)
CASES = json.loads((ROOT/'evals/interaction/cycle-14/mixed-writer-protocol.json').read_text())['cases']


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_mixed_writer_privacy_preserves_authority_provenance(tmp_path, monkeypatch, case):
    monkeypatch.setattr(config.llm, 'api_key', '')
    monkeypatch.setattr(config.embedding, 'model', '')
    row = AUDIT.evaluate_case(tmp_path/'owned.db', case)
    assert row['failure'] is None
    assert row['passed'], row['checks']

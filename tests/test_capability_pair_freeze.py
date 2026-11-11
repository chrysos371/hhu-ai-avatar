from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
spec = importlib.util.spec_from_file_location('capability_pair_audit', ROOT/'scripts/evaluate_capability_pair.py')
audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)


def freeze(tmp_path, **changes):
    data = {'candidate': audit.CANDIDATE, 'execution_authorized': True,
        'allowed_partition': 'development', 'prospective_execution_authorized': False,
        'sha256': {name: sha256((ROOT/name).read_bytes()).hexdigest() for name in audit.required_sources()}}
    data.update(changes)
    path = tmp_path/'freeze.json'; path.write_text(json.dumps(data))
    return path, data


def test_development_freeze_cannot_authorize_prospective(tmp_path):
    path, data = freeze(tmp_path)
    assert audit.verify_freeze(path, 'development') == data
    with pytest.raises(ValueError): audit.verify_freeze(path, 'prospective')


@pytest.mark.parametrize('changes,partition', [
    ({'execution_authorized': False}, 'development'),
    ({'candidate': 'other-candidate'}, 'development'),
    ({'allowed_partition': 'prospective'}, 'prospective'),
    ({'allowed_partition': 'unknown'}, 'unknown'),
    ({'sha256': {}}, 'development'),
])
def test_missing_authority_or_complete_source_freeze_rejected(tmp_path, changes, partition):
    path, _ = freeze(tmp_path, **changes)
    with pytest.raises(ValueError): audit.verify_freeze(path, partition)


def test_source_mismatch_cannot_pass_as_frozen(tmp_path):
    path, data = freeze(tmp_path)
    data['sha256']['src/avatar/lab/capability_prompt.py'] = '0'*64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): audit.verify_freeze(path, 'development')


def test_frozen_path_cannot_escape_repository(tmp_path):
    path, data = freeze(tmp_path)
    data['sha256']['../outside'] = '0'*64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): audit.verify_freeze(path, 'development')


def test_separately_authorized_prospective_is_still_partition_specific(tmp_path):
    path, data = freeze(tmp_path, allowed_partition='prospective', prospective_execution_authorized=True)
    assert audit.verify_freeze(path, 'prospective') == data
    with pytest.raises(ValueError): audit.verify_freeze(path, 'development')


def test_v2_freeze_requires_explicit_candidate_and_its_own_protocols(tmp_path):
    candidate = 'lab_source_capability_v2'
    path, data = freeze(tmp_path, candidate=candidate,
        sha256={name: sha256((ROOT/name).read_bytes()).hexdigest() for name in audit.required_sources(candidate)})
    with pytest.raises(ValueError): audit.verify_freeze(path, 'development')
    assert audit.verify_freeze(path, 'development', candidate) == data
    with pytest.raises(ValueError): audit.verify_freeze(path, 'prospective', candidate)
    del data['sha256']['evals/interaction/cycle-21/source-capability-candidate-v2.json']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError): audit.verify_freeze(path, 'development', candidate)


def test_unknown_candidate_cannot_generate_a_complete_source_list():
    with pytest.raises(ValueError): audit.required_sources('unknown')


@pytest.mark.parametrize('bad_field', [None, 'current_user_source', 'runtime_attribution',
    'current_turn_execution_receipts', 'declared_model_tool_names', 'registry_readiness_verified'])
def test_transmitted_source_metadata_must_match_completed_turn(bad_field):
    result = {'conversation': {'user_message_id': 7, 'revision': 2},
              'speaker_attribution': {'scope': 'fictional_character', 'turn_tools_allowed': False}}
    data = {**audit.capability_evidence(), 'capability_evidence_version': 2,
        'current_user_source': {'message_id': 7, 'revision': 2, 'verified': True},
        'runtime_attribution': {**result['speaker_attribution'], 'origin': 'web_source_store'},
        'registry_readiness_verified': False, 'historical_execution_verified': False}
    if bad_field: data[bad_field] = 'corrupt'
    native = {'messages': [{'content': 'trusted contract\n可信元数据如下：\n'+json.dumps(data)}]}
    if bad_field:
        with pytest.raises(AssertionError): audit.validate_source_metadata(native, result)
    else:
        assert audit.validate_source_metadata(native, result) == data

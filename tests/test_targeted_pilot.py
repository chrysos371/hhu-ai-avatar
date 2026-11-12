"""Provenance and leakage gates for targeted pilot exports."""
import copy
import json
from pathlib import Path
import pytest
from avatar.lab import targeted
from avatar.lab.common import canonical, sha
from avatar.lab.training import load_data


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    monkeypatch.setattr(targeted, 'evaluation_texts', lambda: ([], {}))
    root = Path(__file__).resolve().parents[1]
    value = json.loads((root/'training/companion/targeted-14b-001/candidates.json').read_text())
    source = tmp_path/'candidates.json'
    source.write_text(canonical(value))
    output = targeted.export(source, tmp_path/'export')
    return output, value


def test_targeted_loader_preserves_ai_only_scope(prepared):
    output, _ = prepared
    train, dev, manifest = load_data(output/'sft.jsonl')
    assert (len(train), len(dev)) == (24, 12)
    assert manifest['approval_scope'] == targeted.SCOPE
    assert manifest['not_full_human_checklist_approval'] is True
    assert not manifest['human_reviewed'] and not manifest['quality_approved']


@pytest.mark.parametrize('field,value', [('human_reviewed', True), ('quality_approved', True),
                                         ('approval_scope', 'human-preference-plus-ai-final-checks')])
def test_targeted_does_not_inherit_or_fake_human_approval(prepared, field, value):
    output, _ = prepared
    p = output/'manifest.json'
    m = json.loads(p.read_text()); m[field] = value; p.write_text(canonical(m))
    with pytest.raises(ValueError, match='provenance'):
        load_data(output/'sft.jsonl')


def test_rehashed_edited_target_still_fails_content_provenance(prepared):
    output, _ = prepared
    p = output/'sft.jsonl'
    rows = [json.loads(x) for x in p.read_text().splitlines()]
    rows[0]['messages'][-1]['content'] = '错误修改后的答案'
    p.write_text(''.join(canonical(r)+'\n' for r in rows))
    m = json.loads((output/'manifest.json').read_text());m['sft_sha256']=sha(p)
    (output/'manifest.json').write_text(canonical(m))
    with pytest.raises(ValueError, match='provenance'):
        load_data(p)


def test_updated_protection_refuses_stale_export(prepared, monkeypatch):
    output, _ = prepared
    monkeypatch.setattr(targeted, 'evaluation_texts', lambda: ([], {'new': 'hash'}))
    with pytest.raises(ValueError, match='Protection'):
        load_data(output/'sft.jsonl')


def test_review_cannot_be_replaced_even_with_updated_manifest_hash(prepared):
    output, _ = prepared
    p=output/'review.json';r=json.loads(p.read_text());r['rows'][0]['checks']=['替换审核']
    p.write_text(canonical(r));m=json.loads((output/'manifest.json').read_text());m['review_sha256']=sha(p)
    (output/'manifest.json').write_text(canonical(m))
    with pytest.raises(ValueError, match='review'):
        load_data(output/'sft.jsonl')


def test_protected_input_and_scenario_group_overlap_rejected(prepared):
    _, v = prepared
    with pytest.raises(ValueError, match='evaluation overlap'):
        targeted.validate_rows(v['train'], v['dev'], [v['train'][0]['messages'][1]['content']])
    dev=copy.deepcopy(v['dev']);dev[0]['group']=v['train'][0]['group']
    with pytest.raises(ValueError, match='group leakage'):
        targeted.validate_rows(v['train'], dev, [])


def test_arithmetic_and_json_targets_have_independent_oracles(prepared):
    _, v=prepared
    rows={r['id']:r['messages'][-1]['content'] for r in v['train']+v['dev']}
    prefix='t14-001-delivery-'
    assert rows[prefix+'01'] == f'{47//6}/{47%6}'
    assert rows[prefix+'02'] == str(18*2+4)
    assert rows[prefix+'03'] == str(9*12-17)
    assert json.loads(rows[prefix+'04']) == ['葡萄','苹果','梨']
    assert rows[prefix+'05'] == str(2*60+35-15-20)
    assert rows[prefix+'06'] == ','.join(map(str, sorted({4,7,4,9,7})))


def test_targeted_preflight_refuses_partial_overlength_dataset(prepared, tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from avatar.lab import training
    output, _ = prepared
    fake = SimpleNamespace(from_pretrained=lambda *a, **kw: object())
    monkeypatch.setitem(sys.modules, 'transformers', SimpleNamespace(AutoTokenizer=fake))
    calls = []
    def encode(tokenizer, row, length):
        calls.append(row['id'])
        if len(calls) == 1:
            raise ValueError('overlength')
        return {'id': row['id'], 'input_ids': [1], 'labels': [1]}
    monkeypatch.setattr(training, 'encode_record', encode)
    config=tmp_path/'config.json';config.write_text('{"max_length":1024}')
    result=tmp_path/'preflight'
    with pytest.raises(ValueError, match='silent sample dropping'):
        training.preflight(output/'sft.jsonl', tmp_path, result, config)
    assert json.loads((result/'rejected.json').read_text())[0]['split'] == 'train'
    assert not (result/'preflight.json').exists()


@pytest.mark.parametrize('used', [1, 550, 1100])
def test_training_idle_gate_rejects_even_small_other_jobs(monkeypatch, used):
    from avatar.lab import training
    monkeypatch.setattr(training, 'gpu_inventory', lambda: {0: {'used_mib': used}})
    with pytest.raises(ValueError, match='entirely idle'):
        training.require_idle_gpus([0])


def test_training_idle_gate_accepts_empty_card(monkeypatch):
    from avatar.lab import training
    monkeypatch.setattr(training, 'gpu_inventory', lambda: {0: {'used_mib': 0}})
    training.require_idle_gpus([0])

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('training_review', ROOT / 'scripts/prepare_companion_training.py')
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)


def setup_batch(tmp_path):
    source = review.load_batch(ROOT / 'training/companion/batch-001.candidates.json')
    source['samples'] = source['samples'][:2]
    source['count'] = 2
    path = tmp_path / 'batch.json'
    path.write_text(json.dumps(source, ensure_ascii=False), encoding='utf-8')
    evaluations = tmp_path / 'evals'
    evaluations.mkdir()
    review.prepare(path, evaluations, tmp_path / 'review')
    return path, evaluations, tmp_path / 'review/review.csv'


def smoke_fixture(tmp_path):
    path, evaluations, ledger = setup_batch(tmp_path)
    samples = review.load_batch(path)['samples']
    votes = {'reviewer_type': 'human', 'rounds': [{'votes': [
        dict(id=s['id'], selected='A', A='chosen', B='rejected', sample_sha256=review.digest(s))
        for s in samples]}]}
    checks = dict(reviewer_type='ai', purpose='local-sft-smoke',
                  authorization_source='user-chat-explicit-training-request',
                  eval_corpus_sha256=review.audit(review.load_batch(path), evaluations)['eval_corpus_sha256'],
                  samples=[dict(id=s['id'], sample_sha256=review.digest(s), decision='include',
                                checks={k: True for k in review.REVIEW_CHECKS}, note='Test fixture only')
                           for s in samples])
    vp, cp = tmp_path / 'votes.json', tmp_path / 'checks.json'
    vp.write_text(json.dumps(votes))
    cp.write_text(json.dumps(checks))
    return path, evaluations, ledger, vp, cp


def test_smoke_export_separates_ai_checks_from_human_approval(tmp_path):
    path, evaluations, ledger, vp, cp = smoke_fixture(tmp_path)
    manifest = review.export_smoke(path, vp, cp, evaluations, tmp_path / 'smoke')
    assert manifest['samples'] == 2 and manifest['not_full_human_checklist_approval']
    assert not (tmp_path / 'smoke/dpo.jsonl').exists()
    assert all(row['decision'] == 'pending' for row in read_rows(ledger))
    with pytest.raises(ValueError, match='No human-approved'):
        review.export(path, ledger, evaluations, tmp_path / 'formal')


def test_smoke_excludes_semantic_overlap_without_modifying_candidate(tmp_path):
    path, evaluations, _, vp, cp = smoke_fixture(tmp_path)
    checks = json.loads(cp.read_text())
    checks['samples'][0].update(decision='exclude', note='Semantic overlap with protected evaluation')
    checks['samples'][0]['checks']['eval_overlap'] = False
    cp.write_text(json.dumps(checks))
    manifest = review.export_smoke(path, vp, cp, evaluations, tmp_path / 'smoke')
    assert manifest['samples'] == 1 and len(manifest['excluded']) == 1
    assert len(review.load_batch(path)['samples']) == 2
    assert manifest['excluded'][0]['id'] not in manifest['sample_ids']


@pytest.mark.parametrize('change', ['stale', 'missing-check', 'wrong-preference', 'wrong-scope'])
def test_smoke_gate_rejects_incomplete_or_stale_evidence(tmp_path, change):
    path, evaluations, _, vp, cp = smoke_fixture(tmp_path)
    checks = json.loads(cp.read_text())
    if change == 'stale':
        checks['samples'][0]['sample_sha256'] = 'outdated'
    elif change == 'missing-check':
        checks['samples'][0]['checks']['roles'] = False
    elif change == 'wrong-scope':
        checks['purpose'] = 'formal-training'
    else:
        votes = json.loads(vp.read_text())
        votes['rounds'][0]['votes'][0]['selected'] = 'B'
        vp.write_text(json.dumps(votes))
    cp.write_text(json.dumps(checks))
    with pytest.raises(ValueError):
        review.export_smoke(path, vp, cp, evaluations, tmp_path / 'smoke')
    assert not (tmp_path / 'smoke').exists()


def read_rows(path):
    with path.open(encoding='utf-8-sig', newline='') as file:
        return list(csv.DictReader(file))


def save_rows(path, rows):
    with path.open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=review.FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def approve_fixture(row):
    row.update(decision='approve', reviewer_type='human', reviewer='unit-test-fixture',
               comment='Simulated approval only; not actual human review.')
    row.update({'checked_' + key: 'yes' for key in review.REVIEW_CHECKS})


def test_pending_batch_never_creates_training_exports(tmp_path):
    path, evaluations, ledger = setup_batch(tmp_path)
    with pytest.raises(ValueError, match='No human-approved'):
        review.export(path, ledger, evaluations, tmp_path / 'export')
    assert not (tmp_path / 'export').exists()


@pytest.mark.parametrize('field,value', [('reviewer_type', 'ai'), ('reviewer', ''),
                                       ('checked_roles', ''), ('comment', '')])
def test_approval_requires_identity_checklist_and_comment(tmp_path, field, value):
    path, evaluations, ledger = setup_batch(tmp_path)
    rows = read_rows(ledger)
    approve_fixture(rows[0])
    rows[0][field] = value
    save_rows(ledger, rows)
    with pytest.raises(ValueError, match='Explicit human'):
        review.export(path, ledger, evaluations, tmp_path / 'export')


def test_export_only_approved_with_identical_prompt_and_no_rationale_leak(tmp_path):
    path, evaluations, ledger = setup_batch(tmp_path)
    rows = read_rows(ledger)
    approve_fixture(rows[0])
    save_rows(ledger, rows)
    manifest = review.export(path, ledger, evaluations, tmp_path / 'export')
    sample = review.load_batch(path)['samples'][0]
    assert manifest['approved_ids'] == [sample['id']]
    sft = json.loads((tmp_path / 'export/sft.jsonl').read_text())
    dpo = json.loads((tmp_path / 'export/dpo.jsonl').read_text())
    assert sft['messages'][:-1] == dpo['prompt'] == sample['messages']
    assert sft['messages'][-1] == dpo['chosen'][0] == {'role': 'assistant', 'content': sample['chosen']}
    assert dpo['rejected'][0]['content'] == sample['rejected']
    assert 'preference_rationale' not in sft and 'constraints' not in dpo


def test_editing_candidate_invalidates_previous_approval(tmp_path):
    path, evaluations, ledger = setup_batch(tmp_path)
    rows = read_rows(ledger)
    approve_fixture(rows[0])
    save_rows(ledger, rows)
    batch = json.loads(path.read_text())
    batch['samples'][0]['chosen'] += ' 修改后的内容。'
    path.write_text(json.dumps(batch), encoding='utf-8')
    with pytest.raises(ValueError, match='Stale review hash'):
        review.export(path, ledger, evaluations, tmp_path / 'export')


def test_exact_eval_collision_blocks_export_and_manifest_counts_are_ignored(tmp_path):
    path, evaluations, ledger = setup_batch(tmp_path)
    sample = review.load_batch(path)['samples'][0]
    (evaluations / 'suite.json').write_text(json.dumps({'cases': [
        {'id': 'held-out-fixture', 'turns': [sample['messages'][1]['content']]}]}), encoding='utf-8')
    (evaluations / 'manifest.json').write_text('{"cases": 100}', encoding='utf-8')
    assert any(e['reason'] == 'exact_eval_overlap' for e in review.audit(review.load_batch(path), evaluations)['errors'])
    with pytest.raises(ValueError, match='overlap errors'):
        review.export(path, ledger, evaluations, tmp_path / 'export')


def test_duplicate_ledger_and_overwriting_review_are_rejected(tmp_path):
    path, evaluations, ledger = setup_batch(tmp_path)
    rows = read_rows(ledger)
    save_rows(ledger, rows + [rows[0]])
    with pytest.raises(ValueError, match='exactly once'):
        review.export(path, ledger, evaluations, tmp_path / 'export')
    with pytest.raises(ValueError, match='never overwritten'):
        review.prepare(path, evaluations, ledger.parent)


def test_changed_protected_eval_set_invalidates_overlap_approval(tmp_path):
    path, evaluations, ledger = setup_batch(tmp_path)
    rows = read_rows(ledger)
    approve_fixture(rows[0])
    save_rows(ledger, rows)
    (evaluations / 'new.json').write_text(json.dumps({'cases': [
        {'id': 'new-protected-case', 'turns': ['这是一条新增而不同的保留场景用户消息。']}]}), encoding='utf-8')
    with pytest.raises(ValueError, match='corpus changed'):
        review.export(path, ledger, evaluations, tmp_path / 'export')


def test_real_batch_counts_and_literal_evidence():
    batch = review.load_batch(ROOT / 'training/companion/batch-001.candidates.json')
    assert len(batch['samples']) == 24
    assert all(sum(s['category'] == cat for s in batch['samples']) == 8
               for cat in ('context', 'role', 'task'))
    assert not batch['training_ready']
    assert all(s['human_review']['status'] == 'pending' for s in batch['samples'])

"""Prepare review batches; export human approvals or explicitly scoped smoke trials."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
REVIEW_CHECKS = ['context', 'roles', 'delivery', 'grounding', 'safety', 'eval_overlap']
FIELDS = ['id', 'sample_sha256', 'eval_corpus_sha256', 'decision', 'reviewer_type', 'reviewer',
          *['checked_' + key for key in REVIEW_CHECKS], 'comment']


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def normalized(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text).casefold()
                   if c.isalnum())


def shingles(text):
    text = normalized(text)
    return {text[i:i + 4] for i in range(max(0, len(text) - 3))}


def load_batch(path):
    batch = json.loads(Path(path).read_text(encoding='utf-8'))
    samples = batch['samples']
    if batch['schema_version'] != '1.0' or batch['count'] != len(samples) or not samples:
        raise ValueError('Invalid batch version/count')
    seen = set()
    for sample in samples:
        if sample['id'] in seen:
            raise ValueError('Duplicate sample ID')
        seen.add(sample['id'])
        if sample['category'] not in {'context', 'role', 'task'} or not sample['scene_family']:
            raise ValueError('Invalid category/family')
        messages = sample['messages']
        if len(messages) < 2 or messages[0]['role'] != 'system' or messages[-1]['role'] != 'user':
            raise ValueError('Prompt must start with system and end with user')
        for index, message in enumerate(messages):
            expected = 'system' if index == 0 else 'user' if index % 2 else 'assistant'
            if message['role'] != expected or not isinstance(message['content'], str) or not message['content'].strip():
                raise ValueError('Invalid message sequence/content')
        for key in ('chosen', 'rejected', 'preference_rationale'):
            if not isinstance(sample[key], str) or not sample[key].strip():
                raise ValueError('Empty response/rationale')
        if normalized(sample['chosen']) == normalized(sample['rejected']):
            raise ValueError('Chosen and rejected must differ')
        if not sample['constraints'] or not sample['error_tags'] or not sample['grounding']:
            raise ValueError('Missing review criteria or source evidence')
        for evidence in sample['grounding']:
            index = evidence['message_index']
            if (type(index) is not int or not 0 <= index < len(messages)
                    or messages[index]['role'] != 'user' or not evidence['evidence']
                    or evidence['evidence'] not in messages[index]['content']):
                raise ValueError('Grounding must point to literal user source')
    return batch


def audit(batch, eval_root):
    corpus = []
    protected_files = {}
    for path in sorted(Path(eval_root).glob('*.json')):
        suite = json.loads(path.read_text(encoding='utf-8'))
        cases = suite.get('cases', [])
        if not isinstance(cases, list):
            continue  # Manifests may contain a numeric case count, not a suite.
        if cases:
            protected_files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for case in cases:
            for turn in case.get('turns', []):
                if isinstance(turn, str) and len(normalized(turn)) >= 8:
                    corpus.append((str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                                   case['id'], turn, shingles(turn)))
    errors, warnings, prompts, answers = [], [], {}, {}
    for sample in batch['samples']:
        prompt = digest(sample['messages'])
        chosen = normalized(sample['chosen'])
        for value, seen, label in [(prompt, prompts, 'duplicate_prompt'), (chosen, answers, 'duplicate_chosen')]:
            if value in seen:
                errors.append(dict(id=sample['id'], reason=label, other=seen[value]))
            seen[value] = sample['id']
        for message in sample['messages']:
            if message['role'] != 'user' or len(normalized(message['content'])) < 8:
                continue
            text = message['content']
            grams = shingles(text)
            best = None
            for file, case_id, source, source_grams in corpus:
                if normalized(text) == normalized(source):
                    errors.append(dict(id=sample['id'], reason='exact_eval_overlap', file=file, case_id=case_id))
                union = grams | source_grams
                similarity = len(grams & source_grams) / len(union) if union else 0
                if similarity >= 0.25 and (best is None or similarity > best['similarity']):
                    best = dict(id=sample['id'], reason='lexical_near_overlap', file=file,
                                case_id=case_id, similarity=round(similarity, 4), candidate=text, evaluation=source)
            if best:
                warnings.append(best)
    return dict(batch_id=batch['batch_id'], samples=len(batch['samples']), errors=errors,
                warnings=warnings, evaluation_turns_scanned=len(corpus),
                protected_files=protected_files, eval_corpus_sha256=digest(protected_files),
                similarity_check=dict(normalization='NFKC + casefold + alphanumeric', ngram=4,
                                      warning_jaccard=0.25, minimum_normalized_turn_length=8),
                limitation='Character shingle similarity is not semantic/family isolation; human review required.')


def empty_output(path):
    path = Path(path)
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise ValueError('Output must be a new or empty directory; review work is never overwritten')
    path.mkdir(parents=True, exist_ok=True)
    return path


def prepare(batch_path, eval_root, output):
    batch = load_batch(batch_path)
    report = audit(batch, eval_root)
    output = empty_output(output)
    (output / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'review.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        for sample in batch['samples']:
            writer.writerow(dict(id=sample['id'], sample_sha256=digest(sample),
                                 eval_corpus_sha256=report['eval_corpus_sha256'], decision='pending'))
    lines = ['# 小批量训练候选人工审核', '',
             '全部样例为AI合成候选，尚未经过人工审核。chosen/rejected标签可以被人工推翻。', '',
             '请在review.csv填写decision、reviewer_type=human、审核者、六项检查及理由。'
             'approve需各项为yes或na（na理由写入comment）；revise需先修改候选并生成新审核目录。', '',
             '重点检查：语境归属、说话人/接收人、产物是否完成、信息证据、边界、与评测的语义/家族重叠。'
             '词面去重不能证明没有评测泄漏；本批次尚不划分验证集。', '']
    for sample in batch['samples']:
        lines += [f"## {sample['id']}（{sample['category']}）", '', f"场景家族：{sample['scene_family']}", '']
        for message in sample['messages']:
            lines += [f"{message['role']}：{message['content']}", '']
        lines += ['### 候选好回复', '', sample['chosen'], '', '### 候选坏回复', '', sample['rejected'], '',
                  '### AI偏好理由（待人工核验）', '', sample['preference_rationale'], '',
                  '检查约束：' + '；'.join(sample['constraints']), '',
                  '审核状态：pending。不能将本材料中的AI理由当作人工审核结论。', '']
    (output / 'review.md').write_text('\n'.join(lines), encoding='utf-8')
    return report


def export(batch_path, review_path, eval_root, output):
    batch = load_batch(batch_path)
    report = audit(batch, eval_root)
    if report['errors']:
        raise ValueError('Batch has duplicate/overlap errors; export blocked')
    with Path(review_path).open(encoding='utf-8-sig', newline='') as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames or not set(FIELDS) <= set(reader.fieldnames):
            raise ValueError('Missing review columns')
        rows = list(reader)
    ids = [row['id'] for row in rows]
    if len(set(ids)) != len(ids) or set(ids) != {s['id'] for s in batch['samples']}:
        raise ValueError('Review must contain each sample ID exactly once')
    reviews = {row['id']: row for row in rows}
    approved = []
    for sample in batch['samples']:
        row = reviews[sample['id']]
        if row['sample_sha256'] != digest(sample):
            raise ValueError('Stale review hash: ' + sample['id'])
        if row['eval_corpus_sha256'] != report['eval_corpus_sha256']:
            raise ValueError('Evaluation corpus changed; overlap review must be repeated')
        if row['decision'] not in {'pending', 'approve', 'reject', 'revise'}:
            raise ValueError('Unknown review decision')
        if row['decision'] != 'approve':
            continue
        if (row['reviewer_type'] != 'human' or not row['reviewer'].strip() or not row['comment'].strip()
                or any(row['checked_' + key] not in {'yes', 'na'} for key in REVIEW_CHECKS)):
            raise ValueError('Explicit human identity, checklist and reasoning required: ' + sample['id'])
        approved.append(sample)
    if not approved:
        raise ValueError('No human-approved samples; no training files written')
    output = empty_output(output)
    sft, dpo = [], []
    for sample in approved:
        answer = dict(role='assistant', content=sample['chosen'])
        sft.append(dict(id=sample['id'], messages=sample['messages'] + [answer]))
        dpo.append(dict(id=sample['id'], prompt=sample['messages'], chosen=[answer],
                        rejected=[dict(role='assistant', content=sample['rejected'])]))
    for name, records in [('sft.jsonl', sft), ('dpo.jsonl', dpo)]:
        (output / name).write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
    manifest = dict(batch_id=batch['batch_id'], approved_ids=[s['id'] for s in approved],
                    candidate_sha256=hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
                    review_sha256=hashlib.sha256(Path(review_path).read_bytes()).hexdigest(),
                    eval_corpus_sha256=report['eval_corpus_sha256'],
                    samples=len(approved), split='pilot-training-only-no-validation-split',
                    note='Reviewer identity is declared in a local CSV, not authenticated. Verify actual human review.')
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def export_smoke(batch_path, votes_path, checks_path, eval_root, output):
    """Distinct, explicitly scoped gate: human preferences + attributed AI final checks."""
    batch = load_batch(batch_path)
    report = audit(batch, eval_root)
    if report['errors'] or report['warnings']:
        raise ValueError('Resolve lexical overlap warnings/errors before smoke export')
    ledger = json.loads(Path(votes_path).read_text(encoding='utf-8'))
    if ledger.get('reviewer_type') != 'human':
        raise ValueError('Human preference votes required')
    votes = [vote for round in ledger['rounds'] for vote in round['votes']]
    if len(votes) != len({v['id'] for v in votes}) or {v['id'] for v in votes} != {s['id'] for s in batch['samples']}:
        raise ValueError('Exactly one preference vote per sample required')
    checks = json.loads(Path(checks_path).read_text(encoding='utf-8'))
    if (checks.get('reviewer_type') != 'ai' or checks.get('purpose') != 'local-sft-smoke'
            or checks.get('authorization_source') != 'user-chat-explicit-training-request'
            or checks.get('eval_corpus_sha256') != report['eval_corpus_sha256']):
        raise ValueError('Attributed final checks and explicit smoke-training scope required')
    records = checks['samples']
    if len(records) != len({r['id'] for r in records}) or {r['id'] for r in records} != {s['id'] for s in batch['samples']}:
        raise ValueError('Final checks must cover each sample once')
    for name, expected in checks.get('extra_protected_files', {}).items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('Extra protected evaluation file changed')
    included, excluded = [], []
    for sample in batch['samples']:
        vote = next(v for v in votes if v['id'] == sample['id'])
        checked = next(r for r in records if r['id'] == sample['id'])
        if (vote['sample_sha256'] != digest(sample) or checked['sample_sha256'] != digest(sample)
                or vote.get(vote['selected']) != 'chosen'
                or not checked.get('note')):
            raise ValueError('Missing/stale preference or final check: ' + sample['id'])
        if checked.get('decision') == 'exclude':
            excluded.append(dict(id=sample['id'], reason=checked['note']))
        elif (checked.get('decision') == 'include'
              and all(checked.get('checks', {}).get(key) is True for key in REVIEW_CHECKS)):
            included.append(sample)
        else:
            raise ValueError('Missing inclusion decision or complete final check: ' + sample['id'])
    if not included:
        raise ValueError('No eligible smoke samples')
    output = empty_output(output)
    records = [dict(id=s['id'], messages=s['messages'] + [dict(role='assistant', content=s['chosen'])])
               for s in included]
    data = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records)
    (output / 'sft.jsonl').write_text(data, encoding='utf-8')
    (output / 'audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = dict(purpose='local-sft-smoke', approval_scope='human-preference-plus-ai-final-checks',
                    not_full_human_checklist_approval=True, samples=len(records),
                    sample_ids=[s['id'] for s in included], excluded=excluded,
                    candidate_sha256=hashlib.sha256(Path(batch_path).read_bytes()).hexdigest(),
                    votes_sha256=hashlib.sha256(Path(votes_path).read_bytes()).hexdigest(),
                    final_checks_sha256=hashlib.sha256(Path(checks_path).read_bytes()).hexdigest(),
                    eval_corpus_sha256=report['eval_corpus_sha256'],
                    sft_sha256=hashlib.sha256(data.encode()).hexdigest(),
                    note='Pipeline-only trial, not performance validation; no validation set or DPO export.')
    (output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'export', 'export-smoke'])
    parser.add_argument('--batch', type=Path, default=ROOT / 'training/companion/batch-001.candidates.json')
    parser.add_argument('--eval-root', type=Path, default=ROOT / 'evals/companion')
    parser.add_argument('--review', type=Path)
    parser.add_argument('--votes', type=Path)
    parser.add_argument('--final-checks', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == 'prepare':
            result = prepare(args.batch, args.eval_root, args.output_dir)
        elif args.command == 'export-smoke':
            if args.votes is None or args.final_checks is None:
                parser.error('--votes and --final-checks required for export-smoke')
            result = export_smoke(args.batch, args.votes, args.final_checks, args.eval_root, args.output_dir)
        else:
            if args.review is None:
                parser.error('--review required for export')
            result = export(args.batch, args.review, args.eval_root, args.output_dir)
    except (ValueError, KeyError) as exc:
        parser.exit(1, str(exc) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(bool(result.get('errors')))


if __name__ == '__main__':
    raise SystemExit(main())

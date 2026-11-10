"""Paired local BF16 base/LoRA developer evaluation with blinded dialogue review."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
import time

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = '你是小海，一个温柔又有点好奇心的AI伙伴。请自然、简短地回应用户。'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_suite(path):
    suite = json.loads(Path(path).read_text())
    cases = suite['cases']
    if len(cases) != 20 or len({c['id'] for c in cases}) != 20:
        raise ValueError('Expected 20 distinct cases')
    for case in cases:
        if len(case['turns']) != 3 or not all(isinstance(t, str) and t.strip() for t in case['turns']):
            raise ValueError('Three nonempty user turns required')
        if not case['checks'] or not case['scene_family']:
            raise ValueError('Missing review criteria')
    return suite


def dialogue(case, generate):
    history = [dict(role='system', content=SYSTEM)]
    turns = []
    for text in case['turns']:
        history.append(dict(role='user', content=text))
        result = generate([dict(m) for m in history])
        if not result['reply'].strip():
            raise ValueError('Empty generation')
        turns.append(dict(user=text, **result))
        history.append(dict(role='assistant', content=result['reply']))
    return dict(id=case['id'], category=case['category'], turns=turns)


def write_review(suite, results, output, seed=20261109):
    rng = random.Random(seed)
    order = list(suite['cases'])
    rng.shuffle(order)
    sides = ['base'] * 10 + ['lora'] * 10
    rng.shuffle(sides)
    key, lines = {}, ['# 匿名完整对话审阅', '',
        '每个编号包含同一场景的A/B两组完整对话；两组各自延续自身历史。',
        '请先独立评价两组是否满足约束，再填A/B/tie/both_bad和具体轮次证据。',
        'review.csv中的人工评分保持空白；不要用回复长度或措辞偏好代替任务与安全检查。', '']
    with (output / 'review.csv').open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['blind_id', 'winner', 'A_quality', 'B_quality', 'safety_regression', 'reviewer_type', 'reviewer', 'evidence'])
        for index, (case, a_side) in enumerate(zip(order, sides), 1):
            blind = f'pair-{index:02d}'
            key[blind] = dict(case_id=case['id'], A=a_side, B='lora' if a_side == 'base' else 'base')
            writer.writerow([blind] + [''] * 7)
            lines += [f'## {blind}', '', '检查：' + '；'.join(case['checks']), '']
            for label in ['A', 'B']:
                lines += [f'### {label}', '']
                for i, turn in enumerate(results[key[blind][label]][case['id']]['turns'], 1):
                    lines += [f'用户{i}：{turn["user"]}', '', f'助手{i}：{turn["reply"]}', '']
                    if turn['truncated']:
                        lines += ['[本轮达到生成上限，不能视作正常完整回复]', '']
    (output / 'blind-review.md').write_text('\n'.join(lines))
    (output / 'unblinding-key.json').write_text(json.dumps(key, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', type=Path, default=ROOT / 'evals/companion/lora-dev-20.json')
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--adapter', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    suite = load_suite(args.suite)
    lock = json.loads(args.suite.with_suffix('.manifest.json').read_text())
    if sha(args.suite) != lock['suite_sha256']:
        raise ValueError('Suite changed after freezing')
    for name, expected in lock['protected_sources'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('Training/evaluation source changed: ' + name)
    proof = json.loads((ROOT / 'training/companion/batch-001-smoke/run-evidence.json').read_text())
    if sha(args.adapter / 'adapter_model.safetensors') != proof['adapter_sha256']:
        raise ValueError('Adapter differs from first smoke trial')
    model_proof = json.loads((args.model / 'verified-revision.json').read_text())
    base_manifest = json.loads((ROOT / 'training/companion/base-model.json').read_text())
    if model_proof['revision'] != base_manifest['revision'] or model_proof['verified_weight_sha256'] != base_manifest['sha256']:
        raise ValueError('Original model verification mismatch')
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Output must be new/empty')
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel
    if not torch.cuda.is_available():
        raise RuntimeError('CUDA required')
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    base = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16,
                  attn_implementation='sdpa', local_files_only=True).to('cuda')
    model = PeftModel.from_pretrained(base, args.adapter, is_trainable=False).eval()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = dict(suite_sha256=sha(args.suite), adapter_sha256=proof['adapter_sha256'],
        model_provenance=model_proof, system_prompt=SYSTEM, do_sample=False, max_new_tokens=256,
        enable_thinking=False, dtype='bfloat16', attention='sdpa', seed=42,
        backend='model-only; Avatar guards disabled equally in both arms',
        histories='separate self-generated history per arm and per case',
        purpose='developer comparison; not an unseen independent benchmark',
        gpu=torch.cuda.get_device_name(), torch_version=torch.__version__)
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    def generate(messages):
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                         enable_thinking=False, return_tensors='pt').to('cuda')
        if ids.shape[1] + 256 > 4096:
            raise ValueError('Context limit; no silent truncation')
        start = time.monotonic()
        with torch.inference_mode():
            out = model.generate(ids, attention_mask=torch.ones_like(ids), max_new_tokens=256,
                                 do_sample=False, pad_token_id=tokenizer.eos_token_id)
        new = out[0, ids.shape[1]:].tolist()
        return dict(reply=tokenizer.decode(new, skip_special_tokens=True),
            generated_tokens=len(new), truncated=bool(new and new[-1] != tokenizer.eos_token_id),
            seconds=round(time.monotonic() - start, 4))
    results = dict(base={}, lora={})
    for index, case in enumerate(suite['cases']):
        for arm in (['base', 'lora'] if index % 2 == 0 else ['lora', 'base']):
            if arm == 'base':
                with model.disable_adapter():
                    item = dialogue(case, generate)
            else:
                item = dialogue(case, generate)
            results[arm][case['id']] = item
            (args.output / 'raw-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(json.dumps(dict(case=case['id'], arm=arm,
                  truncated=sum(t['truncated'] for t in item['turns']))), flush=True)
    write_review(suite, results, args.output)
    summary = {arm: dict(cases=len(rows), turns=sum(len(c['turns']) for c in rows.values()),
                        truncated=sum(t['truncated'] for c in rows.values() for t in c['turns']))
               for arm, rows in results.items()}
    (args.output / 'execution-summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

"""Same original weights: raw base, base+Avatar, LoRA+Avatar. Isolated local state."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import logging
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from evaluate_companion_lora import load_suite, sha, SYSTEM, dialogue
from evaluate_companion import FallbackTrace

ARMS = ['raw_base', 'base_avatar', 'lora_avatar']


def load_raw_reference(path, suite, model_proof, suite_hash):
    manifest = json.loads((path.parent / 'manifest.json').read_text())
    if (manifest['suite_sha256'] != suite_hash
            or manifest['model'] != model_proof or manifest['raw_system'] != SYSTEM
            or manifest['reply_max_new_tokens'] != 256 or manifest['do_sample'] is not False
            or manifest['enable_thinking'] is not False or manifest['dtype'] != 'bfloat16'
            or manifest['attention'] != 'sdpa'):
        raise ValueError('Raw reference conditions differ')
    rows = json.loads(path.read_text())['raw_base']
    if set(rows) != {c['id'] for c in suite['cases']}:
        raise ValueError('Raw reference case mismatch')
    for case in suite['cases']:
        turns = rows[case['id']]['turns']
        if ([t['user'] for t in turns] != case['turns']
                or any(t['truncated'] or not t['reply'].strip() for t in turns)):
            raise ValueError('Incomplete or different raw reference')
    return rows


class LocalTrace:
    available = True

    def __init__(self, generate):
        self.generate = generate
        self.calls = []

    def chat(self, messages, temperature=0, max_tokens=512):
        return self._call(messages, 'reply', temperature, 256)

    def chat_analysis(self, messages, temperature=0):
        return self._call(messages, 'analysis', temperature, 512)

    def _call(self, messages, kind, temperature, limit):
        record = dict(kind=kind, messages=[dict(m) for m in messages],
                      requested_temperature=temperature, actual_do_sample=False, token_limit=limit)
        self.calls.append(record)
        try:
            record.update(self.generate(messages, limit))
            return record['reply']
        except Exception as exc:
            record['error'] = type(exc).__name__
            raise


def backend_dialogue(case, llm, directory):
    from avatar.main import Avatar
    from avatar.brain.memory import MemoryStore
    from avatar.brain.emotion import EmotionEngine
    memory = MemoryStore(str(directory / 'memory.db'), embedder=None)
    avatar = Avatar(memory=memory, llm=llm, session_id=case['id'])
    clock = [0.0]
    avatar.emotion = EmotionEngine(clock=lambda: clock[0])
    turns = []
    try:
        for index, text in enumerate(case['turns']):
            clock[0] = 10.0 * (index + 1)
            before = len(llm.calls)
            trace = FallbackTrace()
            logger = logging.getLogger('avatar.main')
            logger.addHandler(trace)
            try:
                result = avatar.respond(text, use_tts=False, use_web=False)
            finally:
                logger.removeHandler(trace)
            calls = llm.calls[before:]
            turns.append(dict(user=text, reply=result['reply'], result=result,
                calls=calls, fallback_events=trace.events, memories=avatar.list_memories(include_history=True),
                truncated=any(c.get('truncated', False) for c in calls),
                guarded=result['boundary']['guarded'],
                analysis_fallback='认知分析失败，回退规则分析' in trace.events,
                reply_fallback='模型回复失败，使用规则回复' in trace.events))
    finally:
        memory.close()
    return dict(id=case['id'], category=case['category'], turns=turns)


def write_blind(suite, results, output):
    rng = random.Random(20261110)
    cases = list(suite['cases']); rng.shuffle(cases)
    key = {}; lines = ['# 三组匿名完整对话', '',
        '每题X/Y/Z分别为三组，位置每题轮换。先逐组评pass/partial/fail，再比较X/Y、Y/Z、X/Z。',
        '只看当前文件；其他结果文件含身份。人工评分表保持空白。', '']
    with (output / 'review.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['blind_id', 'X_quality', 'Y_quality', 'Z_quality', 'ranking', 'reviewer_type', 'reviewer', 'evidence'])
        for i, case in enumerate(cases):
            order = ARMS[i % 3:] + ARMS[:i % 3]
            if i % 2: order = list(reversed(order))
            label = f'triad-{i+1:02d}'; key[label] = dict(case_id=case['id'], **dict(zip('XYZ', order)))
            writer.writerow([label] + [''] * 7)
            lines += [f'## {label}', '', '检查：' + '；'.join(case['checks']), '']
            for side, arm in zip('XYZ', order):
                lines += [f'### {side}', '']
                for n, t in enumerate(results[arm][case['id']]['turns'], 1):
                    lines += [f'用户{n}：{t["user"]}', '', f'助手{n}：{t["reply"]}', '']
                    if t['truncated']: lines += ['[本轮模型调用达到上限，详见原始记录]', '']
    (output / 'blind-review.md').write_text('\n'.join(lines))
    (output / 'unblinding-key.json').write_text(json.dumps(key, ensure_ascii=False, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--adapter', type=Path, required=True)
    p.add_argument('--suite', type=Path, default=ROOT / 'evals/companion/lora-dev-20.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--analysis-decoding', choices=['schema', 'prompt'], default='schema')
    p.add_argument('--raw-reference', type=Path, help='Reuse a frozen matching raw arm, with hashes recorded')
    args = p.parse_args()
    suite = load_suite(args.suite)
    lock = json.loads(args.suite.with_suffix('.manifest.json').read_text())
    if sha(args.suite) != lock['suite_sha256'] or any(sha(ROOT / n) != h for n, h in lock['protected_sources'].items()):
        raise ValueError('Frozen suite/training source mismatch')
    proof = json.loads((ROOT / 'training/companion/batch-001-smoke/run-evidence.json').read_text())
    if sha(args.adapter / 'adapter_model.safetensors') != proof['adapter_sha256']:
        raise ValueError('Adapter mismatch')
    verified = json.loads((args.model / 'verified-revision.json').read_text())
    expected = json.loads((ROOT / 'training/companion/base-model.json').read_text())
    if verified['revision'] != expected['revision'] or verified['verified_weight_sha256'] != expected['sha256']:
        raise ValueError('Base provenance mismatch')
    if args.output.exists() and any(args.output.iterdir()): raise ValueError('Output must be new/empty')
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel
    from avatar.config import config
    config.avatar_name = '小海'; config.avatar_persona = '一个温柔又有点好奇心的AI伙伴'
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    base = AutoModelForCausalLM.from_pretrained(args.model, local_files_only=True,
            dtype=torch.bfloat16, attn_implementation='sdpa').to('cuda')
    model = PeftModel.from_pretrained(base, args.adapter, is_trainable=False).eval()
    if args.analysis_decoding == 'schema':
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn, build_token_enforcer_tokenizer_data
        from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT
        tokenizer_data = build_token_enforcer_tokenizer_data(tokenizer, vocab_size=model.config.vocab_size)
    args.output.mkdir(parents=True, exist_ok=True)
    source_files = list((ROOT / 'src/avatar').rglob('*.py')) + [Path(__file__).resolve(), ROOT / 'scripts/evaluate_companion_lora.py', ROOT / 'scripts/evaluate_companion.py']
    manifest = dict(arms=ARMS, suite_sha256=sha(args.suite), adapter_sha256=proof['adapter_sha256'],
        adapter_config_sha256=sha(args.adapter / 'adapter_config.json'), model=verified,
        backend_source_hashes={str(f.relative_to(ROOT)): sha(f) for f in source_files},
        raw_system=SYSTEM, backend_persona=config.avatar_persona, reply_max_new_tokens=256,
        analysis_max_new_tokens=512, do_sample=False, seed=42, enable_thinking=False,
        dtype='bfloat16', attention='sdpa', emotion_clock='10 seconds per user turn',
        state='fresh SQLite per arm and case; no embeddings, web or TTS; no production DB',
        analysis_protocol=args.analysis_decoding,
        schema_decoder_version=importlib.metadata.version('lm-format-enforcer') if args.analysis_decoding == 'schema' else None,
        adapter_scope='LoRA applied to both analysis and reply in lora_avatar',
        limitation='Exposed developer suite; AI review not human approval; backend rules not model learning')
    if args.raw_reference:
        manifest['raw_reference'] = dict(path=str(args.raw_reference), sha256=sha(args.raw_reference),
            manifest_sha256=sha(args.raw_reference.parent / 'manifest.json'))
    (args.output / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    def generate(messages, limit):
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
                    enable_thinking=False, return_tensors='pt').to('cuda')
        if ids.shape[1] + limit > 4096: raise ValueError('Context limit exceeded')
        start = time.monotonic()
        options = {}
        if limit == 512 and args.analysis_decoding == 'schema':
            parser = JsonSchemaParser(ANALYSIS_RESPONSE_FORMAT['json_schema']['schema'])
            options['prefix_allowed_tokens_fn'] = build_transformers_prefix_allowed_tokens_fn(tokenizer_data, parser)
        with torch.inference_mode():
            out = model.generate(ids, attention_mask=torch.ones_like(ids), do_sample=False,
                        max_new_tokens=limit, pad_token_id=tokenizer.eos_token_id, **options)
        new = out[0, ids.shape[1]:].tolist()
        reply = tokenizer.decode(new, skip_special_tokens=True)
        if not reply.strip(): raise ValueError('Empty output')
        return dict(reply=reply, generated_tokens=len(new), input_tokens=ids.shape[1],
                    truncated=new[-1] != tokenizer.eos_token_id, seconds=round(time.monotonic()-start, 4))
    results = {a: {} for a in ARMS}
    if args.raw_reference:
        results['raw_base'] = load_raw_reference(args.raw_reference, suite, verified, sha(args.suite))
    for index, case in enumerate(suite['cases']):
        order = ARMS[index % 3:] + ARMS[:index % 3]
        for arm in order:
            if arm == 'raw_base' and args.raw_reference: continue
            def run():
                if arm == 'raw_base': return dialogue(case, lambda m: generate(m, 256))
                directory = args.output / 'state' / arm / case['id']; directory.mkdir(parents=True)
                return backend_dialogue(case, LocalTrace(generate), directory)
            if arm == 'lora_avatar': item = run()
            else:
                with model.disable_adapter(): item = run()
            results[arm][case['id']] = item
            (args.output / 'raw-results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
            print(json.dumps(dict(case=case['id'], arm=arm,
                       truncated=sum(t['truncated'] for t in item['turns']))), flush=True)
    summary = {}
    for arm, rows in results.items():
        turns = [t for c in rows.values() for t in c['turns']]
        summary[arm] = dict(cases=len(rows), turns=len(turns),
            truncated=sum(t['truncated'] for t in turns), guarded=sum(t.get('guarded',False) for t in turns),
            analysis_fallbacks=sum(t.get('analysis_fallback',False) for t in turns),
            reply_fallbacks=sum(t.get('reply_fallback',False) for t in turns),
            model_calls=sum(len(t.get('calls',[])) for t in turns) if arm != 'raw_base' else len(turns))
    (args.output / 'execution-summary.json').write_text(json.dumps(summary, indent=2))
    write_blind(suite, results, args.output)
    print(json.dumps(summary), flush=True)


if __name__ == '__main__':
    main()

"""Paired pre-change/current backend evaluation on one pinned local base.

Run in separate processes with --source to prevent mixed Python module state.
No adapters, external API, production memory, embedding, web, or TTS.
"""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar.paths import project_data_root


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--include-old', action='store_true')
    p.add_argument('--suite', type=Path, default=ROOT / 'evals/companion/reliability-dev-30.json')
    p.add_argument('--extra-suite', type=Path, action='append', default=[])
    p.add_argument('--enable-task-contracts', action='store_true')
    p.add_argument('--enable-delivery-check', action='store_true')
    p.add_argument('--enable-grounding', action='store_true')
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('Output must not exist')
    source = args.source.resolve()
    avatar_options = {}
    for key, value in [('task_contract_enabled', args.enable_task_contracts),
                       ('delivery_check_enabled', args.enable_delivery_check),
                       ('grounding_prompt_enabled', args.enable_grounding)]:
        if value:
            avatar_options[key] = True
    sys.path.insert(0, str(source))
    from avatar.main import Avatar
    from avatar.config import config
    assert Path(sys.modules['avatar.main'].__file__).resolve().is_relative_to(source)
    from evaluate_companion_three_arms import LocalTrace, backend_dialogue
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.integrations.transformers import build_transformers_prefix_allowed_tokens_fn, build_token_enforcer_tokenizer_data
    from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT
    config.avatar_name = '小海'
    config.avatar_persona = '一个温柔又有点好奇心的AI伙伴'
    dev_path = args.suite.resolve()
    paths = [dev_path] + [p.resolve() for p in args.extra_suite]
    cases = [dict(c, category=c.get('family', c.get('category', 'task')))
             for path in paths for c in json.loads(path.read_text())['cases']]
    if args.include_old:
        old = ROOT / 'evals/companion/lora-dev-20.json'
        paths.append(old)
        cases += json.loads(old.read_text())['cases']
    if len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Duplicate case IDs across suites')
    model_path = project_data_root(ROOT) / 'models/Qwen3-4B'
    proof = json.loads((model_path / 'verified-revision.json').read_text())
    expected = json.loads((ROOT / 'training/companion/base-model.json').read_text())
    assert proof['revision'] == expected['revision'] and proof['verified_weight_sha256'] == expected['sha256']
    args.output.mkdir(parents=True)
    manifest = dict(source=str(source), source_sha256={str(f.relative_to(source)): sha(f) for f in source.rglob('*.py')},
        evaluator_sha256=sha(Path(__file__)), helper_sha256=sha(ROOT/'scripts/evaluate_companion_three_arms.py'),
        avatar_options=avatar_options, evaluator_default_options='see source snapshot constructor',
        suites={str(f.relative_to(ROOT)): sha(f) for f in paths}, model=proof,
        dtype='bfloat16', attention='sdpa', do_sample=False, enable_thinking=False,
        reply_tokens=256, analysis_tokens=512, seed=42,
        structured_decoder=importlib.metadata.version('lm-format-enforcer'),
        scope='development only; author knows scenarios; human semantic review pending',
        isolation='new SQLite per case; 10s clock per turn; no web/embedding/TTS; base only')
    (args.output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    torch.manual_seed(42)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(model_path, local_files_only=True,
        dtype=torch.bfloat16, attn_implementation='sdpa').to('cuda').eval()
    tokenizer_data = build_token_enforcer_tokenizer_data(tokenizer, vocab_size=model.config.vocab_size)

    def generate(messages, limit):
        ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True,
            enable_thinking=False, return_tensors='pt').to('cuda')
        if ids.shape[1] + limit > 4096:
            raise ValueError('Context exceeds evaluation limit')
        options = {}
        if limit == 512:
            options['prefix_allowed_tokens_fn'] = build_transformers_prefix_allowed_tokens_fn(
                tokenizer_data, JsonSchemaParser(ANALYSIS_RESPONSE_FORMAT['json_schema']['schema']))
        start = time.monotonic()
        with torch.inference_mode():
            out = model.generate(ids, attention_mask=torch.ones_like(ids), do_sample=False,
                max_new_tokens=limit, pad_token_id=tokenizer.eos_token_id, **options)
        new = out[0, ids.shape[1]:].tolist()
        reply = tokenizer.decode(new, skip_special_tokens=True)
        if not reply.strip():
            raise ValueError('Empty model response')
        return dict(reply=reply, generated_tokens=len(new), input_tokens=ids.shape[1],
            truncated=new[-1] != tokenizer.eos_token_id, seconds=round(time.monotonic()-start, 4))

    results = {}
    for c in cases:
        directory = args.output/'state'/c['id']
        directory.mkdir(parents=True)
        results[c['id']] = backend_dialogue(c, LocalTrace(generate), directory, avatar_options=avatar_options)
        (args.output/'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print(json.dumps({'case': c['id'], 'turns': len(results[c['id']]['turns'])}), flush=True)
    turns = [t for c in results.values() for t in c['turns']]
    calls = [x for t in turns for x in t['calls']]
    route_mismatches = []
    for c in cases:
        if 'routes' in c:
            actual = [t['result']['boundary']['route'] for t in results[c['id']]['turns']]
            if actual != c['routes']:
                route_mismatches.append(dict(id=c['id'], expected=c['routes'], actual=actual))
    summary = dict(cases=len(cases), turns=len(turns), model_calls=len(calls),
        call_errors=sum('error' in x for x in calls),
        analysis_fallbacks=sum(t['analysis_fallback'] for t in turns),
        reply_fallbacks=sum(t['reply_fallback'] for t in turns),
        analysis_truncations=sum(x.get('truncated', False) for x in calls if x['kind']=='analysis'),
        reply_call_truncations=sum(x.get('truncated', False) for x in calls if x['kind']=='reply'),
        guarded=sum(t['guarded'] for t in turns), route_mismatches=route_mismatches,
        repair_attempts=sum(t['result'].get('delivery_check',{}).get('repair_attempted',False) for t in turns),
        remaining_delivery_issues=sum(bool(t['result'].get('delivery_check',{}).get('remaining_issues',[])) for t in turns),
        model_seconds=round(sum(x.get('seconds',0) for x in calls),2),
        semantic_review='pending; route checks do not certify response quality')
    (args.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps(summary, ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()

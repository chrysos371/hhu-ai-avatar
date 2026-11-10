"""Local, final-answer-only Qwen3 LoRA pipeline check (no quality claims)."""
import argparse
import hashlib
import importlib.metadata
import json
import random
import time
from pathlib import Path


def encode_record(tokenizer, row, max_length):
    messages = row['messages']
    if messages[-1]['role'] != 'assistant' or messages[-2]['role'] != 'user':
        raise ValueError('Expected final assistant target after user')
    prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=True,
                                          add_generation_prompt=True, enable_thinking=False)
    answer = tokenizer.encode(messages[-1]['content'], add_special_tokens=False)
    ids = prefix + answer + [tokenizer.eos_token_id]
    if not answer or len(ids) > max_length:
        raise ValueError('Empty target or overlength sample: ' + row['id'])
    return {'input_ids': ids, 'labels': [-100] * len(prefix) + answer + [tokenizer.eos_token_id]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    import torch
    import transformers
    import peft
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import LoraConfig, get_peft_model, PeftModel
    cfg = json.loads(args.config.read_text())
    random.seed(cfg['seed'])
    torch.manual_seed(cfg['seed'])
    if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
        raise RuntimeError('BF16 CUDA GPU required')
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    rows = [json.loads(line) for line in args.data.read_text().splitlines() if line.strip()]
    manifest = json.loads(args.data.with_name('manifest.json').read_text())
    if hashlib.sha256(args.data.read_bytes()).hexdigest() != manifest['sft_sha256']:
        raise ValueError('SFT manifest hash mismatch')
    if manifest['purpose'] != 'local-sft-smoke' or manifest['samples'] != len(rows):
        raise ValueError('Wrong export purpose/count')
    provenance = json.loads((args.model / 'verified-revision.json').read_text())
    if provenance['revision'] != cfg['revision'] or provenance['model_id'] != cfg['model_id']:
        raise ValueError('Base model revision mismatch')
    examples = [encode_record(tokenizer, row, cfg['max_length']) for row in rows]
    def load_base():
        return AutoModelForCausalLM.from_pretrained(
            args.model, local_files_only=True, torch_dtype=torch.bfloat16,
            attn_implementation='sdpa', low_cpu_mem_usage=True).to('cuda')
    def probe(model):
        model.eval()
        prompt = tokenizer.apply_chat_template(rows[0]['messages'][:-1], tokenize=True,
                    add_generation_prompt=True, enable_thinking=False, return_tensors='pt').to('cuda')
        with torch.no_grad():
            logits = model(prompt).logits[0, -1].float().cpu()
            result = model.generate(prompt, attention_mask=torch.ones_like(prompt),
                     max_new_tokens=64, do_sample=False, pad_token_id=tokenizer.eos_token_id)
        return logits, tokenizer.decode(result[0, prompt.shape[1]:], skip_special_tokens=True)
    if args.verify_only:
        model = PeftModel.from_pretrained(load_base(), args.output / 'adapter', is_trainable=False)
        logits, text = probe(model)
        saved = torch.load(args.output / 'probe.pt', map_location='cpu', weights_only=True)
        delta = (logits - saved).abs().max().item()
        expected = json.loads((args.output / 'result.json').read_text())['probe_text']
        if not torch.allclose(logits, saved, atol=1e-4, rtol=1e-4) or text != expected or not text.strip():
            raise RuntimeError('Fresh-process adapter reload mismatch')
        result = dict(passed=True, max_logit_difference=delta, generation_identical=text == expected,
                      process='fresh-python-process', probe_text=text)
        (args.output / 'reload-verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False), flush=True)
        return
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError('Output directory must be new/empty')
    args.output.mkdir(parents=True, exist_ok=True)
    model = get_peft_model(load_base(), LoraConfig(r=cfg['lora_r'], lora_alpha=cfg['lora_alpha'],
              lora_dropout=cfg['lora_dropout'], target_modules=cfg['target_modules'],
              task_type='CAUSAL_LM', bias='none'))
    model.config.use_cache = False
    params = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.AdamW(params, lr=cfg['learning_rate'], weight_decay=0.0)
    order = list(range(len(examples)))
    random.shuffle(order)
    if cfg['max_steps'] > (len(order) + cfg['gradient_accumulation_steps'] - 1) // cfg['gradient_accumulation_steps']:
        raise ValueError('Smoke config must not repeat training samples')
    log = []
    model.train()
    train_started = time.monotonic()
    for step in range(cfg['max_steps']):
        optimizer.zero_grad(set_to_none=True)
        loss_sum = 0.0
        micro_count = min(cfg['gradient_accumulation_steps'], len(order) - step * cfg['gradient_accumulation_steps'])
        for micro in range(micro_count):
            item = examples[order[step * cfg['gradient_accumulation_steps'] + micro]]
            batch = {k: torch.tensor([v], device='cuda') for k, v in item.items()}
            loss = model(**batch).loss
            if not torch.isfinite(loss):
                raise RuntimeError('Non-finite training loss')
            loss_sum += loss.item() / micro_count
            (loss / micro_count).backward()
        norm = torch.nn.utils.clip_grad_norm_(params, 1.0, error_if_nonfinite=True)
        optimizer.step()
        entry = dict(step=step + 1, loss=loss_sum, gradient_norm=norm.item(), samples=micro_count)
        log.append(entry)
        print(json.dumps(entry), flush=True)
    training_seconds = time.monotonic() - train_started
    changed = any(p.detach().abs().max().item() > 0 for n, p in model.named_parameters() if 'lora_B' in n)
    if not changed:
        raise RuntimeError('Adapter weights did not update')
    model.save_pretrained(args.output / 'adapter', safe_serialization=True)
    tokenizer.save_pretrained(args.output / 'adapter')
    model.config.use_cache = True
    logits, text = probe(model)
    torch.save(logits, args.output / 'probe.pt')
    result = dict(config=cfg, model_provenance=provenance, batch_size=1, optimizer='AdamW, weight_decay=0',
                  dtype='bfloat16', attention='sdpa', supervision='final-assistant-only-non-thinking',
                  samples=len(rows), sequence_lengths=[len(e['input_ids']) for e in examples],
                  supervised_tokens=[sum(x != -100 for x in e['labels']) for e in examples],
                  trainable_parameters=sum(p.numel() for p in params), adapter_updated=changed,
                  training_seconds=training_seconds,
                  steps=log, probe_text=text, data_sha256=manifest['sft_sha256'],
                  gpu=torch.cuda.get_device_name(), peak_gpu_bytes=torch.cuda.max_memory_allocated(),
                  versions={name: importlib.metadata.version(name) for name in
                            ['torch', 'transformers', 'peft', 'accelerate', 'huggingface_hub', 'tokenizers', 'safetensors']},
                  limitation='Training pipeline check only; no held-out quality evaluation.')
    (args.output / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'completed_steps': len(log), 'adapter_updated': changed}), flush=True)


if __name__ == '__main__':
    main()

"""Real CPU tokenizer, exact original prompt-token matching, changed supervision."""
import os
from pathlib import Path
import json
import sys
os.environ.update(CUDA_VISIBLE_DEVICES="",HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1")
from avatar.lab.training import preflight
from avatar.lab.common import sha,write_json
import avatar.lab.training as training
BASE=Path(__file__).resolve().parents[1]
ASSETS=Path("/data/Users/zrh/data/hhu-ai-avatar")


def read(p):return json.loads(Path(p).read_text())

def main():
    assert sys.prefix==str(ASSETS/"envs/hhu-ai-avatar-train")
    out=ASSETS/"artifacts/c54/target-tokenization-v1"
    config=BASE.parent/"cycle-51/审计/工作目录/005-真实分词预检/training-config-v1.json"
    dataset=ASSETS/"artifacts/c54/target-expression-v1/sft.jsonl"
    result=preflight(dataset,ASSETS/"models/Qwen3-4B",out,config)
    assert result["samples"]==176 and result["dev_samples"]==44 and not result["rejected"]
    old=read(ASSETS/"artifacts/c51/tokenizer-preflight-v1/tokens.json")
    new=read(out/"tokens.json");matched=0;counts={}
    for split in ["train","dev"]:
        original={r["id"]:r for r in old[split]};tokens=0;min_length=2048;max_length=0
        for row in new[split]:
            prior=original[row["id"].replace("c54-expression-","c51-",1)]
            first=next(i for i,v in enumerate(row["labels"]) if v!=-100)
            previous=next(i for i,v in enumerate(prior["labels"]) if v!=-100)
            assert first==previous and row["input_ids"][:first]==prior["input_ids"][:previous]
            assert row["labels"][:first]==[-100]*first and row["labels"][first:]==row["input_ids"][first:]
            matched+=1;tokens+=len(row["labels"])-first;min_length=min(min_length,len(row["labels"]));max_length=max(max_length,len(row["labels"]))
        counts[split]={"supervised_tokens_including_EOS":tokens,"min_sequence_tokens":min_length,"max_sequence_tokens":max_length}
    import torch
    assert not torch.cuda.is_initialized()
    write_json(BASE/"审计/工作目录/003-真实分词/target-tokenization-v1.json",{"verified":True,
        "scope":"current real CPU tokenizer and exact prompt tokens; target replacement also changes token budget, not isolated scalar diversity",
        "verifier_sha256":sha(Path(__file__)),"training_module_sha256":sha(training.__file__),
        "actual_train":176,"actual_dev":44,"actual_prompt_token_pairs_identical":matched,"split_counts":counts,
        "tokens_sha256":sha(out/"tokens.json"),"preflight_sha256":sha(out/"preflight.json"),"external_output":str(out),
        "original_supervised_train_tokens":3936,"original_supervised_dev_tokens":984,
        "new_LLM_generations":0,"new_training_steps":0,"CUDA_initialized":False,"GPU_allocations":0})
    print("C54 actualCPU220prompttokens exact;new supervision",counts,";0LLM/GPU")


if __name__=="__main__":main()

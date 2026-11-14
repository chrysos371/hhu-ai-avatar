"""One CPU-only current preflight; no model construction or training."""
import os
from pathlib import Path
import sys
os.environ.update(CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
from avatar.lab.training import preflight
from avatar.lab.common import sha, write_json
import avatar.lab.training as training

BASE = Path(__file__).resolve().parents[1]
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")


def main():
    assert sys.prefix == str(ASSETS/"envs/hhu-ai-avatar-train")
    output = ASSETS/"artifacts/c53/current-tokenization-v1"
    config=BASE.parent/"cycle-51/审计/工作目录/005-真实分词预检/training-config-v1.json"
    result=preflight(ASSETS/"artifacts/c51/correction-data-v1/sft.jsonl", ASSETS/"models/Qwen3-4B", output, config)
    assert result["samples"]==176 and result["dev_samples"]==44 and not result["rejected"]
    prior=ASSETS/"artifacts/c51/tokenizer-preflight-v1/tokens.json"
    assert result["tokens_sha256"]==sha(prior)=="2c3c37d4b866e2f9b272f1b69287323cc5df8e60a228dea5d8b5b22232e9d28b"
    import torch
    assert not torch.cuda.is_initialized()
    write_json(BASE/"审计/工作目录/005-修后真实分词/current-tokenization-v1.json",{
        "verified":True,"scope":"CPU tokenizer and current loader compatibility; not model inference or training",
        "current_training_module_sha256":sha(training.__file__),"verifier_sha256":sha(Path(__file__)),
        "actual_samples":176,"actual_dev_samples":44,"supervised_train_tokens_including_EOS":result["supervised_tokens"],
        "tokens_sha256":result["tokens_sha256"],"same_as_original_C51_tokens":True,
        "external_output":str(output),"preflight_sha256":sha(output/"preflight.json"),
        "CUDA_initialized":False,"new_model_generations":0,"training_steps":0})
    print("current actual CPU tokenization176/44;3936supervised;identical original220sequences;0LLM/GPU/training")


if __name__=="__main__": main()

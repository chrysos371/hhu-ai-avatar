"""CPU fault controls for capture validation; no backend/model construction."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess

from capture_transformers import validate_call


def main():
    work = Path(__file__).parent / "工作目录/001-调用采证"
    output = work / "validation-cpu-v1.json"
    assert not output.exists()
    template = {"input_ids": [[1, 2, 3]], "independent_token_ids": [1, 2, 3],
        "attention_mask": [[1, 1, 1]], "kind": "reply", "has_adapter": False,
        "adapter_requested": False, "lora_layers": [], "model_training": False,
        "embedding_dtype": "torch.bfloat16", "embedding_device": "cuda:0",
        "do_sample": False, "max_new_tokens": 512, "registered_limit": 512,
        "context_tokens": 8192, "analysis_grammar_present": False}
    positives = []
    for kind in ("analysis", "reply"):
        for has_adapter in (False, True):
            row = copy.deepcopy(template)
            row.update(kind=kind, has_adapter=has_adapter,
                adapter_requested=has_adapter and kind == "reply",
                analysis_grammar_present=kind == "analysis")
            row["lora_layers"] = ([{"name": "fixture.q_proj", "disabled": kind == "analysis",
                "training": False}] if has_adapter else [])
            validate_call(row)
            positives.append(row)
    faults = {
        "different_actual_tokens": {"input_ids": [[1, 2, 4]]},
        "boolean_token_ID": {"input_ids": [[True, 2, 3]]},
        "different_attention_mask": {"attention_mask": [[1, 0, 1]]},
        "boolean_attention_mask": {"attention_mask": [[True, 1, 1]]},
        "two_sequences": {"input_ids": [[1, 2, 3], [1, 2, 3]]},
        "analysis_adapter": {"kind": "analysis", "adapter_requested": True,
            "has_adapter": True, "analysis_grammar_present": True},
        "unexpected_LoRA_layers": {"lora_layers": [{"name": "q", "disabled": True, "training": False}]},
        "model_training": {"model_training": True},
        "wrong_dtype": {"embedding_dtype": "torch.float32"},
        "CPU_offload": {"embedding_device": "cpu"},
        "sampled_decode": {"do_sample": True},
        "changed_budget": {"max_new_tokens": 511},
        "boolean_budget": {"max_new_tokens": True},
        "context_overflow": {"context_tokens": 514},
        "reply_grammar": {"analysis_grammar_present": True},
        "missing_adapter": {"adapter_requested": True},
        "false_numeric_adapter_flag": {"adapter_requested": 0},
    }
    rejected = []
    for name, changes in faults.items():
        row = copy.deepcopy(template)
        row.update(changes)
        try:
            validate_call(row)
        except ValueError as error:
            rejected.append({"fault": name, "rejection": str(error)})
        else:
            raise AssertionError("capture validation accepted: " + name)
    for name, change in (("analysis_layer_still_enabled", {"disabled": False}),
                         ("analysis_layer_training", {"training": True})):
        row = copy.deepcopy(positives[1])
        row["lora_layers"][0].update(change)
        try:
            validate_call(row)
        except ValueError as error:
            rejected.append({"fault": name, "rejection": str(error)})
        else:
            raise AssertionError("capture validation accepted: " + name)
    files = [Path(__file__), Path(__file__).with_name("capture_transformers.py")]
    proof = {"passed": True, "scope": "CPU fabricated observations passed to actual validator; not real model hook execution",
        "valid_fixture_roles": len(positives), "faults_rejected": rejected,
        "source_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "actual_model_hook_verified": False, "model_constructions": 0, "training_steps": 0,
        "GPU_allocations": 0, "semantic_quality_approved": False}
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print("C52 capture validator CPU fixtures:4 valid roles,19 faults rejected;0 model/training")


if __name__ == "__main__":
    main()

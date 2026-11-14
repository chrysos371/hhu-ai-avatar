"""Independently inspect a finished stage and retire its process before the next."""
import argparse
import math
import os
from pathlib import Path
import subprocess

from execution_common import (ROOT, BASE, RUN, LOCK, DATA, TOKENIZATION, STAGES,
    read, sha, write_new, require, verify_freeze, training_binding_files, verify_training_binding)


def retired(marker):
    proc = Path(f'/proc/{marker["pid"]}')
    require(not proc.exists() or (proc / "stat").read_text().split()[21] != marker["start_ticks"],
        "stage process has not exited")
    rows = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory",
        "--format=csv,noheader,nounits"], text=True)
    require(not any(line.split(",")[0].strip() == str(marker["pid"]) for line in rows.splitlines()),
        "stage PID still owns GPU memory")
    return {"original_process_present": False, "own_compute_rows_after_exit": []}


def manifest_check(proof):
    path = Path(proof["artifact_manifest"])
    require(sha(path) == proof["artifact_manifest_sha256"], "prior artifact manifest changed")
    files = read(path)
    require(all(sha(path.parent / name) == value for name, value in files.items()), "prior raw artifacts changed")


def verify_evaluation(stage, folder):
    from transformers import AutoTokenizer
    from avatar.lab.runner import local_model, STYLE_HINT
    from capture_transformers import validate_call
    from replay_common import CASES, case_for_replay, inspect_observations
    entry = next(e for e in read(LOCK)["models"] if e["name"] == "4b")
    tokenizer = AutoTokenizer.from_pretrained(local_model(entry), local_files_only=True, trust_remote_code=False)
    evaluation = read(folder / "evaluation.json")
    require(evaluation["completed"] is True and evaluation["actual_trials"] == 66
        and evaluation["actual_queries"] == evaluation["actual_ordinary_turns"] == 66,
        "evaluation stage is incomplete")
    require(evaluation["actual_generation_calls"] == evaluation["actual_generate_entries"] == 134,
        "actual phase generation count differs")
    generated = {}
    for ordinal in range(1, 135):
        start = read(folder / f"actual-generate/{ordinal:04}-entry.json")
        result = read(folder / f"actual-generate/{ordinal:04}-result.json")
        require(result["ordinal"] == ordinal and result["completed"] is True and result["fixture"] is False,
            "actual generation not completed")
        require(all(start[key] == result[key] for key in start), "entry/result observation changed")
        validate_call(result)
        require(result["has_adapter"] is (stage == "after"), "actual adapter presence differs")
        require(result["adapter_requested"] is (stage == "after" and result["kind"] == "reply"),
            "actual adapter scope differs")
        actual = result["input_ids"][0]
        expected = tokenizer.apply_chat_template(result["messages"], tokenize=True,
            add_generation_prompt=True, enable_thinking=False)
        require(actual == expected, "independent actual token reconstruction differs")
        output = result["actual_output_ids"][0]
        require(output[:len(actual)] == actual, "actual output prefix differs")
        tokens = output[len(actual):]
        require(0 < len(tokens) <= 512 and result["backend_result"]["new_tokens"] == len(tokens),
            "actual output token count differs")
        require(tokenizer.decode(tokens, skip_special_tokens=True) == result["backend_result"]["reply"],
            "actual output decode differs")
        generated[ordinal] = result
    require(len(list((folder / "actual-generate").glob("*-entry.json"))) == 134
        and len(list((folder / "actual-generate").glob("*-result.json"))) == 134, "unregistered extra generates")
    cases = {c["id"]: case_for_replay(c) for c in read(CASES)["cases"]}
    SQL = 0
    paired = {}
    ordinals = []
    for repetition in range(1, 4):
        group = read(folder / f"repetition-{repetition}/group.json")
        require(group["completed"] is True and len(group["trials"]) == 22, "repetition incomplete")
        require([t["case"] for t in group["trials"]] == list(cases), "case order differs")
        for trial in group["trials"]:
            case = cases[trial["case"]]
            out = folder / f'repetition-{repetition}/{case["id"]}'
            require(str(out.relative_to(folder)) == trial["folder"] and sha(out / "receipt.json") == trial["receipt_sha256"],
                "actual trial receipt changed")
            receipt = read(out / "receipt.json")
            SQL += inspect_observations(out, receipt, case, "production_snapshot")
            observations = receipt["actual_model_interface_calls"]
            require([o["role"] for o in observations] == ["cognition", "generation"]
                and all(o["error"] is None for o in observations), "actual interface failure")
            calls = [generated[n] for n in trial["call_ordinals"]]
            require([c["kind"] for c in calls] == ["analysis", "reply"], "actual call roles differ")
            for index, (observation, call) in enumerate(zip(observations, calls)):
                import copy
                messages = copy.deepcopy(observation["messages"])
                if index == 1:
                    messages[0]["content"] += "\n" + STYLE_HINT
                require(messages == call["messages"] and observation["raw_reply"] == call["backend_result"]["reply"],
                    "application and actual model observations differ")
            paired[f'{repetition}/{case["id"]}'] = calls
            ordinals.extend(trial["call_ordinals"])
    require(SQL == 132 and ordinals == list(range(3, 135)), "formal SQL/call mapping differs")
    result = {"actual_generation_calls": 134, "formal_generations": 132, "warmups": 2,
        "actual_trials": 66, "SQL_dumps_reconstructed": SQL, "actual_adapter_scope_verified": True}
    if stage == "after":
        before = read(RUN / "ledger/before-verified.json")
        manifest_check(before)
        messages = tokens = analyses = 0
        for key, calls in paired.items():
            repetition, case = key.split("/", 1)
            group = read(RUN / f"before/repetition-{repetition}/group.json")
            trial = next(t for t in group["trials"] if t["case"] == case)
            previous = [read(RUN / f"before/actual-generate/{n:04}-result.json") for n in trial["call_ordinals"]]
            messages += all(a["messages"] == b["messages"] for a, b in zip(previous, calls))
            tokens += all(a["input_ids"] == b["input_ids"] for a, b in zip(previous, calls))
            analyses += previous[0]["actual_output_ids"] == calls[0]["actual_output_ids"]
        result.update(paired_messages_identical=messages, paired_actual_tokens_identical=tokens,
            paired_analysis_output_ids_identical=analyses, matched_trial_pairs=66,
            causal_input_matching_passed=messages == tokens == analyses == 66)
    return result


def verify_training(stage, folder):
    import torch
    from safetensors.torch import load_file
    manifest = read(RUN / "adapter/manifest.json")
    require(manifest["status"] == "completed" and manifest["steps"] == 44
        and manifest["samples"] == 176 and manifest["dev_samples"] == 44
        and not manifest["rejected"], "training completion counts differ")
    require(manifest["dataset_sha256"] == sha(DATA)
        and manifest["config"] == read(TOKENIZATION / "training-config-v1.json"), "training input differs")
    require(manifest["adapter_sha256"] == sha(RUN / "adapter/adapter/adapter_model.safetensors")
        and manifest["adapter_config_sha256"] == sha(RUN / "adapter/adapter/adapter_config.json"), "adapter bytes changed")
    steps = read(RUN / "adapter/steps.json")
    require(len(steps) == 44 and [s["step"] for s in steps] == list(range(1, 45))
        and all(s["samples"] == 4 and math.isfinite(s["loss"]) and math.isfinite(s["gradient_norm"]) for s in steps),
        "actual optimizer log differs")
    tensors = load_file(RUN / "adapter/adapter/adapter_model.safetensors", device="cpu")
    require(tensors and all("lora_" in key and torch.isfinite(value).all().item() for key, value in tensors.items())
        and any(value.abs().max().item() > 0 for key, value in tensors.items() if "lora_B" in key), "saved LoRA update invalid")
    probe = read(folder / "actual-probe.json")
    require(probe["completed"] is True and len(probe["direct_forwards"]) == len(probe["generations"]) == 1,
        "actual existing probe count differs")
    require(probe["expect_trainable"] is (stage == "train")
        and bool(probe["actual_trainable_parameters"]) is (stage == "train"), "actual probe trainability differs")
    if stage == "train":
        require(sum(p["parameters"] for p in probe["actual_trainable_parameters"]) == manifest["trainable_parameters"]
            and all(".lora_" in p["name"] and any(target in p["name"] for target in (".q_proj.", ".v_proj."))
                for p in probe["actual_trainable_parameters"]), "actual trainable parameter scope differs")
    require(probe["logits_file_sha256"] == sha(folder / "actual-probe.pt"), "probe logits changed")
    result = {"optimizer_steps": 44, "train_samples": 176, "dev_samples": 44,
        "additional_probe_generations": 1, "additional_probe_direct_forwards": 1,
        "saved_adapter_tensors": len(tensors), "dev_loss_is_not_quality": True}
    result.update({key: sha(path) for key, path in training_binding_files().items()})
    actual = torch.load(folder / "actual-probe.pt", map_location="cpu", weights_only=True)
    saved = torch.load(RUN / "adapter/probe.pt", map_location="cpu", weights_only=True)
    require(torch.allclose(saved, actual, atol=1e-4, rtol=1e-4), "independent saved logits differ")
    if stage == "train":
        require(torch.equal(saved, actual), "captured training probe logits differ from trainer save")
    else:
        verify_training_binding()
        reload = read(RUN / "adapter/reload-verification.json")
        train = read(RUN / "train/actual-probe.json")
        require(reload["passed"] is True and reload["generation_identical"] is True
            and probe["text"] == train["text"] == manifest["probe_text"], "fresh-process probe text differs")
        difference = float((saved - actual).abs().max())
        require(difference == reload["max_logit_difference"], "recorded logit difference differs")
        result.update(fresh_process_reload_passed=True, independent_max_logit_difference=difference)
    return result


def run(args):
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    verify_freeze(args.freeze, args.expected_freeze_sha256)
    folder = RUN / args.stage
    marker = read(folder / "process-result.json")
    require(marker["completed"] is True and marker["freeze_sha256"] == args.expected_freeze_sha256,
        "stage did not complete; preserve failed output")
    cleanup = retired(marker)
    allocation = read(folder / "gpu-allocation.json")
    require(allocation["pid"] == marker["pid"] and allocation["selected"]["uuid"] == marker["selected_gpu"]["uuid"],
        "actual GPU allocation differs")
    proof_path = RUN / "ledger" / (args.stage + "-verified.json")
    require(not proof_path.exists(), "stage already independently retired")
    result = verify_evaluation(args.stage, folder) if args.stage in ("before", "after") else verify_training(args.stage, folder)
    artifact = folder / "artifact-manifest.json"
    write_new(artifact, {str(p.relative_to(folder)): sha(p) for p in folder.rglob("*") if p.is_file()})
    result.update(execution_verified=True, process_retired=True, cleanup=cleanup,
        stage=args.stage, freeze_sha256=args.expected_freeze_sha256, process_result_sha256=sha(folder / "process-result.json"),
        artifact_manifest=str(artifact), artifact_manifest_sha256=sha(artifact), verifier_sha256=sha(Path(__file__)),
        semantic_quality_approved=False, default_activation_authorized=False)
    write_new(proof_path, result)
    print("C52", args.stage, "independently verified and process retired;quality remains unapproved")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--expected-freeze-sha256", required=True)
    parser.add_argument("--stage", choices=STAGES, required=True)
    run(parser.parse_args())

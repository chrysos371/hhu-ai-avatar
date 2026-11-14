"""One fresh process for one frozen C52 stage; no stage or model retries."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from execution_common import (ROOT, BASE, ASSETS, RUN, DATA, LOCK, TOKENIZATION,
    STAGES, WORK, verify_freeze, protocol_check, preparation_check, read, sha, write_new, require,
    historical, verify_training_binding)


def gpu_cards():
    raw = subprocess.check_output(["nvidia-smi", "--query-gpu=index,uuid,memory.free,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits"], text=True)
    return [{"index": int(v[0]), "uuid": v[1].strip(), "free_mib": int(v[2]),
        "used_mib": int(v[3]), "utilization": int(v[4])}
        for line in raw.splitlines() if (v := line.split(","))]


def choose_gpu(requested):
    cards = gpu_cards()
    candidates = [c for c in cards if c["free_mib"] >= 36000 and c["used_mib"] <= 1024
        and c["utilization"] <= 10 and (requested is None or c["index"] == requested)]
    require(bool(candidates), "no currently idle GPU with 36,000MiB free; no CPU fallback")
    return max(candidates, key=lambda c: (c["free_mib"], -c["index"])), cards


def process_allocation(selected):
    raw = subprocess.check_output(["nvidia-smi", "--query-compute-apps=pid,gpu_uuid,used_memory",
        "--format=csv,noheader,nounits"], text=True)
    own = [line for line in raw.splitlines() if line.split(",")[0].strip() == str(os.getpid())]
    require(own and all(line.split(",")[1].strip() == selected["uuid"] for line in own),
        "actual model process GPU UUID differs")
    return {"pid": os.getpid(), "selected": selected, "own_compute_rows": own}


def environment_check(frozen):
    require(sys.prefix == str(ASSETS / "envs/hhu-ai-avatar-train"), "use the verified training interpreter")
    proof = preparation_check(frozen["c51_seal_sha256"])
    actual = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
        if Path(d.locate_file("")).resolve().is_relative_to(Path(sys.prefix).resolve())}
    require(actual == proof["installed"]["local_versions"], "installed training packages changed")
    return actual


def previous_stage_check(stage, freeze_sha):
    position = STAGES.index(stage)
    for previous in STAGES[:position]:
        path = RUN / "ledger" / (previous + "-verified.json")
        require(path.is_file(), "previous stage has not independently verified and retired: " + previous)
        proof = read(path)
        require(proof["execution_verified"] is True and proof["process_retired"] is True
            and proof["freeze_sha256"] == freeze_sha, "previous execution proof differs")
        committed = WORK / (previous + "-verified.json")
        require(committed.is_file() and sha(committed) == sha(path), "commit previous stage proof before continuing")
        name = str(committed.relative_to(ROOT))
        require(historical("HEAD", [name]) == {name: sha(committed)}, "previous stage proof is not committed")
    if stage in ("reload", "after"):
        verify_training_binding()
    require(not any((RUN / "ledger" / (later + "-start.json")).exists()
        for later in STAGES[position:]), "stage already attempted or later stage started; no retries")


def evaluate(stage, protocol, selected, folder):
    from unittest.mock import patch
    from avatar.lab.runner import TransformersBackend, ReplyScopedModel, gpu_lease, local_model
    from capture_transformers import CapturedBackend
    from replay_common import CASES, case_for_replay, sample_trial, inspect_observations
    cases = read(CASES)["cases"]
    settings = {key: protocol["evaluation"][key] for key in
        ("reply_tokens", "analysis_tokens", "context_tokens", "do_sample", "enable_thinking")}
    settings.update(seed=42, dtype="bfloat16", attention="sdpa")
    entry = next(e for e in read(LOCK)["models"] if e["name"] == "4b")
    adapter = RUN / "adapter/adapter" if stage == "after" else None
    report = {"stage": stage, "completed": False, "groups": [], "actual_trials": 0,
        "actual_queries": 0, "actual_ordinary_turns": 0, "source_check_failures": [],
        "semantic_review_pending": True, "quality_approved": False}
    from avatar.lab.common import write_json
    backend = None
    try:
        with gpu_lease([selected["index"]], 1):
            path = local_model(entry)
            backend = TransformersBackend(path, settings, adapter=adapter, gpu_count=1)
            write_new(folder / "gpu-allocation.json", process_allocation(selected))
            capture = CapturedBackend(backend, folder / "actual-generate")
            engine = ReplyScopedModel(capture, arm="style_lora" if adapter else "style_prompt")
            warm = [{"role": "system", "content": "这是一条独立预热。遵守当前输出协议。"},
                {"role": "user", "content": "只回复准备完成。"}]
            capture.context = {"phase": "warmup"}
            engine.chat_analysis(warm)
            engine.chat(warm)
            require(len(capture.calls) == 2, "warmup count differs")
            report["warmup_calls"] = 2
            for repetition in range(1, 4):
                trials = []
                with patch("time.time", return_value=protocol["evaluation"]["controlled_query_clock_epoch"]):
                    for original in cases:
                        case = case_for_replay(original)
                        out = folder / f"repetition-{repetition}" / case["id"]
                        start = len(capture.calls)
                        def context(value):
                            capture.context = {"stage": stage, **value}
                        receipt = sample_trial(engine, case, "production_snapshot", repetition, out,
                            on_context=context, native_counter=lambda: len(capture.calls))
                        calls = capture.calls[start:]
                        require([c["kind"] for c in calls] == ["analysis", "reply"]
                            and all(c["completed"] for c in calls), "actual model call failed; stop without retry")
                        require(all(c["error"] is None for c in receipt["actual_model_interface_calls"])
                            and receipt["model_modes_valid"], "Avatar fallback cannot hide transport failure")
                        source_error = None
                        try:
                            require(inspect_observations(out, receipt, case, "production_snapshot") == 2,
                                "SQL reconstruction count differs")
                        except (AssertionError, ValueError) as error:
                            source_error = type(error).__name__ + ": " + str(error)[:300]
                            report["source_check_failures"].append({"case": case["id"],
                                "repetition": repetition, "error": source_error})
                        trials.append({"case": case["id"], "family": case["family"],
                            "folder": str(out.relative_to(folder)), "receipt_sha256": sha(out / "receipt.json"),
                            "call_ordinals": [c["ordinal"] for c in calls], "source_error": source_error,
                            "business_unchanged": receipt["business_unchanged_by_query_and_ordinary"],
                            "no_new_user_facts": receipt["no_new_user_facts"]})
                        report["actual_trials"] += 1
                        report["actual_queries"] += receipt["actual_query_turns"]
                        report["actual_ordinary_turns"] += 1
                        write_json(folder / "evaluation.json", report)
                group = {"completed": True, "repetition": repetition, "trials": trials}
                write_new(folder / f"repetition-{repetition}/group.json", group)
                report["groups"].append(group)
                write_json(folder / "evaluation.json", report)
                print(stage, "repetition", repetition, "closed;actual generates", len(capture.calls), flush=True)
            require(len(capture.calls) == 134 and report["actual_trials"] == 66
                and report["actual_queries"] == report["actual_ordinary_turns"] == 66,
                "registered phase counts differ")
            local_model(entry)
            report.update(completed=True, actual_generation_calls=len(capture.calls),
                actual_generate_entries=sum(c["actual_generate_entries"] for c in capture.calls),
                strict_source_checks_passed=not report["source_check_failures"])
    finally:
        write_json(folder / "evaluation.json", report)


def training_stage(stage, selected, folder):
    import avatar.lab.training as training
    from capture_probe import observed_probe
    original = training._probe
    def probe(model, tokenizer, row, torch):
        write_new(folder / "gpu-allocation.json", process_allocation(selected))
        return observed_probe(original, model, tokenizer, row, torch, folder / "actual-probe.json")
    training._probe = probe
    try:
        if stage == "train":
            result = training.train(DATA, LOCK, "4b", TOKENIZATION / "training-config-v1.json",
                RUN / "adapter", gpus=[selected["index"]])
            require(result["steps"] == 44 and result["samples"] == 176
                and result["dev_samples"] == 44 and not result["rejected"], "actual training counts differ")
        else:
            result = training.verify_reload(DATA, LOCK, "4b", RUN / "adapter", gpus=[selected["index"]])
            require(result["passed"] is True, "independent adapter reload failed")
        write_new(folder / "stage-result.json", result)
    finally:
        training._probe = original


def run(args):
    frozen = verify_freeze(args.freeze, args.expected_freeze_sha256)
    versions = environment_check(frozen)
    previous_stage_check(args.stage, args.expected_freeze_sha256)
    protocol = protocol_check()
    selected, cards = choose_gpu(args.gpu)
    # Set before importing Avatar/config; both phases use the original synthetic-data persona.
    os.environ.update(AVATAR_NAME="小海", AVATAR_PERSONA="一个温柔又有点好奇心的AI伙伴",
        EMBEDDING_MODEL="", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1",
        TOKENIZERS_PARALLELISM="false", PYTHONDONTWRITEBYTECODE="1")
    folder = RUN / args.stage
    require(not folder.exists(), "stage output already exists")
    marker = {"stage": args.stage, "pid": os.getpid(), "start_ticks": Path(f"/proc/{os.getpid()}/stat").read_text().split()[21],
        "freeze_sha256": args.expected_freeze_sha256, "started_UTC": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "selected_gpu": selected, "inventory_at_start": cards, "package_versions": versions,
        "completed": False, "process_retirement_pending": True, "quality_approved": False}
    write_new(RUN / "ledger" / (args.stage + "-start.json"), marker)
    folder.mkdir(parents=True, exist_ok=False)
    from avatar.lab.common import write_json
    try:
        if args.stage in ("before", "after"):
            evaluate(args.stage, protocol, selected, folder)
        else:
            training_stage(args.stage, selected, folder)
        verify_freeze(args.freeze, args.expected_freeze_sha256)
        marker["completed"] = True
    except BaseException as error:
        marker["failure"] = type(error).__name__ + ": " + str(error)[:500]
        raise
    finally:
        marker["finished_UTC"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        write_json(folder / "process-result.json", marker)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", type=Path, required=True)
    parser.add_argument("--expected-freeze-sha256", required=True)
    parser.add_argument("--stage", choices=STAGES, required=True)
    parser.add_argument("--gpu", type=int)
    run(parser.parse_args())

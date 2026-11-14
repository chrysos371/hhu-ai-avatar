"""Recheck final C51 preparation evidence, committed inputs and old immutable seals."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

from avatar.lab.common import sha
from avatar.lab.data import evaluation_texts, normalize_dialogue, screen_candidates
from avatar.lab.runner import local_model
from avatar.lab.training import load_data
from environment_receipt import ADMISSION, PREPARATION, admitted_environment, successful_source
from run_python_regression import ROOT, BASE, snapshot

WORK = BASE / "审计/工作目录"
C52 = BASE.parent / "cycle-52"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")


def read(path):
    return json.loads(Path(path).read_text())


def historical(ref, names):
    raw = subprocess.check_output(["git", "archive", "--format=tar", ref, "--", *sorted(names)], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
            for m in archive if m.isfile()}


def main():
    environment = admitted_environment()
    admission = read(ADMISSION)
    environment_source, _ = successful_source(admission["preparation_source"])
    if admission["preparation_source"].startswith("environment-v4/"):
        retirement_path = PREPARATION / "environment-v3/operator-retirement-v1.json"
        retirement = read(retirement_path)
        assert environment["prior_retirement_sha256"] == sha(retirement_path)
        assert retirement["verified"] and retirement["parent_process_retired"] and retirement["child_process_retired"]
        assert retirement["actual_parent_tool_exit_code"] == 1 and retirement["actual_child_returncode"] == -15
        assert retirement["source_terminal_sha256"] == sha(PREPARATION / "environment-v3/environment-v3.json")
    transfer_retirement = read(PREPARATION / "range-first-retirement-v1.json")
    assert transfer_retirement["verified"] and transfer_retirement["actual_tool_exit_code"] == 143
    assert transfer_retirement["operator_finalized_report_sha256"] == sha(PREPARATION / "range-first-shard-v1.json")
    cross_path = WORK / "005-真实分词预检/training-tokenizer-crosscheck-v1.json"
    cross = read(cross_path)
    mask_path = WORK / "005-真实分词预检/mask-preflight-v1.json"
    mask = read(mask_path)
    assert cross["verified"] and cross["identical_to_tokenizer_only_environment"]
    assert cross["training_environment_proof_sha256"] == sha(ADMISSION)
    assert cross["tokens_sha256"] == mask["tokens_sha256"]
    for folder in (ASSETS / "artifacts/c51/tokenizer-preflight-v1", Path(cross["external_output"])):
        assert sha(folder / "tokens.json") == mask["tokens_sha256"]
    assert sha(ROOT / "src/avatar/lab/training.py") == mask["training_module_sha256"]
    runtime = admission["actual_CPU_probe"]["runtime_files_sha256"]
    assert len(runtime) >= 10 and all(sha(Path(name)) == value for name, value in runtime.items())
    lock_path = PREPARATION / "model-v1/models.lock.json"
    entry = read(lock_path)["models"][0]
    local_model(entry)
    model_path = PREPARATION / "model-independent-v1.json"
    model = read(model_path)
    assert model["verified"] and model["model_lock_sha256"] == sha(lock_path)
    assert model["model_preparation_sha256"] == sha(PREPARATION / "model-v1/model-preparation.json")
    software = snapshot()
    regression_path = WORK / "002-当前软件回归/python-first-binding.json"
    regression = read(regression_path)
    assert software == regression["source_git_sha256"] and len(software) == 493
    log = WORK / "002-当前软件回归/python-first.log"
    assert regression["exit_code"] == 0 and regression["source_unchanged"] and sha(log) == regression["log_sha256"]
    assert "2540 passed, 1 skipped" in log.read_text()
    isolation = read(WORK / "001-训练条件与入口/isolation-fixed.json")
    assert isolation["verified"] and isolation["screening_code_sha256"] == sha(ROOT / "src/avatar/lab/data.py")
    assert len(isolation["fixed_all_100_input_occurrence_screening"]) == 100
    assert all(not row["accepted"] and "eval_overlap" in row["reasons"]
        for row in isolation["fixed_all_100_input_occurrence_screening"])
    data = ASSETS / "artifacts/c51/correction-data-v1/sft.jsonl"
    train, dev, manifest = load_data(data)
    assert (len(train), len(dev), manifest["human_reviewed"]) == (176, 44, False)
    assert mask["data_manifest_sha256"] == sha(data.with_name("manifest.json"))
    assert manifest["protocol_sha256"] == sha(ROOT / "evals/interaction/cycle-52/correction-transfer-protocol.json")
    texts, hashes = evaluation_texts()
    rejected = []
    eval_name = "evals/interaction/cycle-52/correction-transfer-cases.json"
    for case in read(ROOT / eval_name)["cases"]:
        for field in ("query_text", "followup_text"):
            assert case[field] in texts
            candidate = normalize_dialogue("closeout", "train", case["id"] + field,
                [case[field], "隔离探针，不是训练回复。"])
            accepted, failures = screen_candidates([candidate], texts,
                source_policy={"closeout": {"language": "zh", "use": "experimental-sft"}})
            assert not accepted and "eval_overlap" in failures[0]["reasons"]
            rejected.append({"case": case["id"], "field": field})
    independent_data_path = WORK / "004-纠错材料/data-independent-v1.json"
    independent_data = read(independent_data_path)
    assert independent_data["verified"] and independent_data["train_samples"] == 176 and independent_data["dev_samples"] == 44
    assert len(independent_data["actual_loader_faults_rejected"]) == 6 and len(independent_data["actual_source_faults_rejected"]) == 3
    raw_files = 0
    groups = sorted((WORK / "004-纠错材料").glob("*-source-v1.json"))
    assert len(groups) == 11
    for group_path in groups:
        group = read(group_path)
        assert group["samples"] == 20 and group["train"] == 16 and group["dev"] == 4
        for name, value in group["raw_sha256"].items():
            path = data.parent / name
            assert path.resolve().is_relative_to(data.parent.resolve()) and sha(path) == value
            raw_files += 1
    cache_path = WORK / "008-CUDA完整依赖缓存/wheel-cache-independent-v1.json"
    cache = read(cache_path)
    assert cache["verified"] and cache["wheel_count"] == 15
    assert cache["cache_run_sha256"] == sha(WORK / "008-CUDA完整依赖缓存/wheel-cache-v1.json")
    assert cache["registry_sha256"] == sha(WORK / "008-CUDA完整依赖缓存/wheel-registry-v2.json")
    cli = C52 / "审计/工作目录/004-真实执行准入负控"
    assert all(read(cli / (name + ".json"))["module_observation"]["error_type"] == "ModuleNotFoundError"
        for name in ("unready_C51_freeze", "missing_actual_freeze", "wrong_freeze_path", "unknown_stage"))
    v2 = read(cli / "cli-v2/admission-cpu-v2.json")
    assert v2["passed"] and v2["actual_CLI_processes"] == 8
    for name in v2["actual_CLI_refusals"]:
        result = read(cli / "cli-v2" / (name + ".json"))
        assert result["module_observation"]["error_type"] == result["expected_error_type"]
        assert result["expected_message"] in result["stderr"] and result["expected_message"] in result["direct_stderr"]
        assert result["returncode"] == result["direct_returncode"] != 0
        assert "ModuleNotFoundError" not in result["stderr"] + result["direct_stderr"]
    assert not (ASSETS / "artifacts/c52/real-transfer-v1").exists()
    old_items = 0
    for number in range(3, 51):
        cycle = BASE.parent / f"cycle-{number:02}"
        seal = read(cycle / "审计/证据清单.json")
        assert all(sha(cycle / name) == value for name, value in seal.items())
        old_items += len(seal)
    migration = ROOT / "docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json"
    seal = read(migration)
    assert all(sha(migration.parent / name) == value for name, value in seal.items())
    old_items += len(seal)
    assert old_items == 12072
    aliases = json.loads(subprocess.check_output(["python3", "-B", "scripts/link_project_assets.py", "--check"], cwd=ROOT, text=True))
    assert len(aliases) == 9 and all(item["valid"] for item in aliases)
    authors = subprocess.check_output(["git", "log", "08ac8187..HEAD", "--format=%an <%ae>"], cwd=ROOT, text=True).splitlines()
    assert set(authors) == {"spinner-bot <langxibielangle@qq.com>"}
    proofs = [ADMISSION, environment_source, cross_path, mask_path, model_path, regression_path,
        independent_data_path, cache_path, cli / "cli-v2/admission-cpu-v2.json"]
    names = set(software)
    names.update((eval_name, "evals/interaction/cycle-52/correction-transfer-protocol.json"))
    names.update(str(p.relative_to(ROOT)) for p in proofs)
    names.update(str(p.relative_to(ROOT)) for p in (BASE / "审计").glob("*.py"))
    names.update(str(p.relative_to(ROOT)) for p in (C52 / "审计").glob("*.py"))
    current = {name: sha(ROOT / name) for name in names}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert historical(head, names) == current, "commit all closed execution inputs before final collection"
    out = BASE / "审计/收尾核验/system-evidence.json"
    assert not out.exists()
    out.parent.mkdir(exist_ok=True)
    value = {"verified": True, "scope": "C51 environment/assets/data preparation and scoped isolation repair;not real model training/quality",
        "head": head, "verifier_sha256": sha(Path(__file__)), "source_sha256": current,
        "historical_full_Python_passed": 2540, "historical_full_Python_skipped": 1,
        "historical_regression_inputs_unchanged": 493, "new_full_suite_executed": False,
        "registered_C52_eval_fields_rejected": rejected, "protected_eval_hashes": hashes,
        "train_samples": 176, "dev_samples": 44, "synthetic_source_SQL_reconstructed_prior": 440,
        "synthetic_raw_files_rehashed": raw_files, "token_sequences_verified": 220,
        "min_tokens": mask["min_observed_tokens"], "max_tokens": mask["max_observed_tokens"],
        "supervised_train_tokens": mask["supervised_tokens_train"],
        "base_files": model["files_verified"], "base_shards": model["weight_shards"], "base_tensor_headers": model["tensor_count"],
        "base_payload_bytes": model["tensor_payload_bytes"], "independent_wheels": 15,
        "wheel_bytes": cache["total_bytes"], "environment_source": admission["preparation_source"],
        "imported_runtime_files_rehashed": len(runtime), "old_seals": 49, "old_items": old_items,
        "asset_aliases_valid": 9, "spinner_commits_checked": len(authors),
        "old_four_CLI_claims_retracted": True, "corrected_normal_wrapped_CLI_controls": 8,
        "new_LLM_model_constructions": 0, "new_native_generations": 0, "training_steps": 0,
        "CUDA_model_compatibility_unverified": True, "semantic_quality_approved": False,
        "human_or_physical_validation_approved": False, "default_model_changed": False, "goal_active": True}
    out.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print("C51 preparation closeout:", len(current), "committed inputs;493historical software inputs unchanged;49/12072 old seals;no real model/quality approval")


if __name__ == "__main__":
    main()

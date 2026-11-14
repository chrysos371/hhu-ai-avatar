"""Read-only C52 system collection; hashes/counts are not semantic approval."""
import importlib.util
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
sys.path.insert(0, str(AUDIT))
from execution_common import (ROOT, BASE, ASSETS, RUN, WORK, STAGES, LOCK, read, sha,
    require, write_new, verify_freeze, historical, verify_training_binding, environment_reader)
from verify_execution import retired, manifest_check
from avatar.lab.runner import local_model


def pure_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    require(not (HERE / "system-evidence.json").exists() and not (HERE / "external-adapter-files.json").exists(), "fresh final collection required")
    frozen_path = WORK / "freeze-v1.json"
    frozen = verify_freeze(frozen_path, "589430a5b10f4a52496001cc0f9a2bee43d008b36af3be07b62eb04e90c7eaed")
    comparison_path = AUDIT / "工作目录/007-逐条来源审阅/comparison-v1.json"
    comparison = read(comparison_path)
    review = pure_module("c52_read_only_review", comparison_path.with_name("verify_review.py"))
    require(comparison["verified"] and comparison["validator_sha256"] == sha(comparison_path.with_name("verify_review.py")), "review verifier differs")
    for phase in ("before", "after"):
        path = comparison_path.with_name(phase + "-review-v1.json")
        require(comparison["review_sha256"][phase] == sha(path)
            and review.validate(read(path), phase) == comparison["phase_summary"][phase], "review provenance/counts differ")
    require(not comparison["local_gain_gate_passed"], "this report is scoped to retained failed candidate")
    stages = {}; raw_files = 0
    v2_protocol = read(AUDIT / "工作目录/006-调用结束态核验/verification-protocol-v2.json")
    for stage in STAGES:
        path = RUN / "ledger" / (stage + "-verified.json")
        proof = read(path)
        require(proof["execution_verified"] and proof["process_retired"] and sha(path) == sha(WORK / path.name), "stage proof differs")
        require(historical("HEAD", [str((WORK / path.name).relative_to(ROOT))]) == {str((WORK / path.name).relative_to(ROOT)): sha(path)}, "stage proof not committed")
        expected_verifier = AUDIT / ("工作目录/006-调用结束态核验/verify_execution_v2.py" if stage in ("before", "after") else "verify_execution.py")
        require(sha(expected_verifier) == proof["verifier_sha256"], "stage verifier bytes differ")
        if stage in ("before", "after"):
            require(sha(expected_verifier) == v2_protocol["v2_sha256"], "v2 verification protocol differs")
        marker = read(RUN / stage / "process-result.json")
        retired(marker); manifest_check(proof)
        raw_files += len(read(Path(proof["artifact_manifest"])))
        require(marker["completed"] and marker["freeze_sha256"] == sha(frozen_path), "stage execution did not complete")
        stages[stage] = {"proof_sha256": sha(path), "pid": marker["pid"], "selected_gpu": marker["selected_gpu"],
            "completed": True, "process_retired": True, "actual_package_inventory": marker["package_versions"]}
    verify_training_binding()
    require(read(WORK / "after-verified.json")["causal_input_matching_passed"], "paired input bytes differ")
    train = read(RUN / "adapter/manifest.json")
    train_probe = read(RUN / "train/actual-probe.json"); reload_probe = read(RUN / "reload/actual-probe.json")
    require(len(train_probe["generations"]) == len(reload_probe["generations"]) == 1
        and len(train_probe["direct_forwards"]) == len(reload_probe["direct_forwards"]) == 1, "probe counts differ")
    adapter_files = {str(p.relative_to(RUN / "adapter")): sha(p) for p in (RUN / "adapter").rglob("*") if p.is_file()}
    entry = next(e for e in read(LOCK)["models"] if e["name"] == "4b")
    local_model(entry)
    reader = environment_reader(); admission = read(reader.ADMISSION)
    runtime = admission["actual_CPU_probe"]["runtime_files_sha256"]
    require(all(sha(Path(n)) == v for n, v in runtime.items()), "admitted runtime subset changed")
    expected_packages = reader.admitted_environment()["installed"]["local_versions"]
    require(all(v["actual_package_inventory"] == expected_packages for v in stages.values()), "stage package versions differ")
    old = BASE.parent / "cycle-51"
    regression = read(old / "审计/工作目录/002-当前软件回归/python-first-binding.json")
    software = {n: sha(ROOT / n) for n in regression["source_git_sha256"]}
    require(software == regression["source_git_sha256"] and len(software) == 493, "historical regression inputs changed")
    log = old / "审计/工作目录/002-当前软件回归/python-first.log"
    require(sha(log) == regression["log_sha256"] and "2540 passed, 1 skipped" in log.read_text(), "historical suite evidence differs")
    old_seals = []; old_items = 0
    for number in range(3, 52):
        cycle = BASE.parent / f"cycle-{number:02}"
        p = cycle / "审计/证据清单.json"; seal = read(p)
        require(all(sha(cycle / n) == v for n, v in seal.items()), "old cycle seal differs")
        old_seals.append({"path": str(p.relative_to(ROOT)), "sha256": sha(p), "items": len(seal)})
        old_items += len(seal)
    p = ROOT / "docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json"; seal = read(p)
    require(all(sha(p.parent / n) == v for n, v in seal.items()), "migration seal differs")
    old_items += len(seal); old_seals.append({"path": str(p.relative_to(ROOT)), "sha256": sha(p), "items": len(seal)})
    require(len(old_seals) == 50 and old_items == 12282, "old seal totals differ")
    aliases = __import__("json").loads(subprocess.check_output(["python3", "-B", "scripts/link_project_assets.py", "--check"], cwd=ROOT, text=True))
    require(len(aliases) == 9 and all(a["valid"] for a in aliases), "central asset aliases differ")
    names = set(frozen["sha256"]) | set(software)
    names.update(str(p.relative_to(ROOT)) for p in (AUDIT / "工作目录").rglob("*")
        if p.is_file() and p.parent != HERE)
    names.update(str(p.relative_to(ROOT)) for p in HERE.iterdir() if p.is_file())
    names.update(str(p.relative_to(ROOT)) for p in AUDIT.glob("*.mjs"))
    for p in [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "experiments/style/README.md",
        BASE / "计划.md", BASE / "真实执行接续.md", *sorted((AUDIT / "问题单").glob("*.md"))]:
        names.add(str(p.relative_to(ROOT)))
    current = {n: sha(ROOT / n) for n in sorted(names)}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    require(historical(head, current) == current, "commit all final collection inputs first")
    write_new(HERE / "external-adapter-files.json", adapter_files)
    output = {"verified": True, "scope": "current experiment engineering and single-agent review provenance; not human/general quality approval",
        "head": head, "collector_sha256": sha(Path(__file__)), "source_sha256": current,
        "execution_freeze_sha256": sha(frozen_path), "execution_inputs": len(frozen["sha256"]),
        "stages": stages, "actual_LLM_constructions": 4, "actual_generation_calls": 270,
        "formal_generation_calls": 264, "warmup_generations": 4, "save_reload_probe_generations": 2,
        "probe_direct_forwards": 2, "optimizer_steps": train["steps"], "train_samples": train["samples"],
        "dev_samples": train["dev_samples"], "training_forwards_from_registered_loop": 176, "dev_forwards_from_registered_loop": 44,
        "actual_Avatar_trials": 132, "actual_SQL_dumps_reconstructed": 264, "phase_raw_files_rehashed": raw_files,
        "adapter_files_manifest_sha256": sha(HERE / "external-adapter-files.json"), "adapter_files": len(adapter_files),
        "adapter_sha256": train["adapter_sha256"], "trainable_parameters": train["trainable_parameters"],
        "training_seconds_scope": "training/dev/save/probe path, not isolated training kernel throughput",
        "training_seconds": train["training_seconds"], "dev_loss": train["dev_loss"],
        "peak_training_gpu_bytes": train["peak_gpu_bytes"], "reload_max_logit_difference": read(RUN / "adapter/reload-verification.json")["max_logit_difference"],
        "admitted_runtime_subset_rehashed": len(runtime), "matched_pairs": 66,
        "comparison_sha256": sha(comparison_path), "phase_summary": comparison["phase_summary"],
        "local_gain_gate_passed": False, "candidate_isolated": True, "default_model_changed": False,
        "historical_Python_passed": 2540, "historical_Python_skipped": 1, "historical_regression_inputs_unchanged": 493,
        "full_suite_rerun_this_cycle": False, "old_seals": old_seals, "old_seal_items": old_items,
        "central_aliases": 9, "human_physical_or_general_quality_approved": False, "goal_active": True}
    write_new(HERE / "system-evidence.json", output)
    print("C52 system verified:270 actual generates/264SQL/44steps/66 matched pairs;semantic gate FAILED;50old seals12282items unchanged")


if __name__ == "__main__": main()

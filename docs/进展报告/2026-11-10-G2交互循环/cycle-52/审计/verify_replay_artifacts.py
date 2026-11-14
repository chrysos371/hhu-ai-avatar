"""Independently reopen every completed CPU receipt/SQL and retain external hashes."""
import json
from pathlib import Path
import subprocess

from avatar.lab.common import sha
from avatar.lab.runner import STYLE_HINT
from capture_transformers import digest
from replay_common import ROOT, BASE, ASSETS, CASES, read, case_for_replay, inspect_observations


def main():
    work = BASE / "审计/工作目录/002-重放预检"
    summary = read(work / "replay-cpu-v1.json")
    output = work / "replay-independent-v1.json"
    assert not output.exists() and summary["passed"]
    raw = Path(summary["external_output"])
    assert raw == ASSETS / "artifacts/c52/plumbing-cpu-v1"
    cases = {c["id"]: case_for_replay(c) for c in read(CASES)["cases"]}
    seen = set()
    inputs = {}
    SQL = 0
    group_hashes = {}
    for name in summary["groups"]:
        group = read(work / name)
        group_hashes[name] = sha(work / name)
        assert len(group["trials"]) == 22 and group["completed"] and group["fixture"]
        for trial in group["trials"]:
            key = (group["phase"], group["repetition"], trial["case"])
            assert key not in seen
            seen.add(key)
            path = Path(trial["receipt"])
            assert path.is_relative_to(raw) and sha(path) == trial["receipt_sha256"]
            receipt = read(path)
            case = cases[trial["case"]]
            assert receipt["query_text"] == case["query_text"] and receipt["followup_text"] == case["followup_text"]
            SQL += inspect_observations(path.parent, receipt, case, "production_snapshot")
            calls = receipt["actual_model_interface_calls"]
            assert [c["role"] for c in calls] == ["cognition", "generation"]
            assert all(c["error"] is None for c in calls)
            messages = json.loads(json.dumps([c["messages"] for c in calls], ensure_ascii=False))
            messages[1][0]["content"] += "\n" + STYLE_HINT
            assert digest(messages) == trial["actual_input_messages_sha256"]
            pair = (group["repetition"], trial["case"])
            if group["phase"].startswith("before_"):
                inputs[pair] = messages
            else:
                assert messages == inputs[pair]
    assert len(seen) == 132 and SQL == 264 and len(inputs) == 66
    files = {str(p.relative_to(raw)): {"bytes": p.stat().st_size, "sha256": sha(p)}
        for p in raw.rglob("*") if p.is_file()}
    assert len(files) == 396
    manifest = raw / "external-manifest-v1.json"
    assert not manifest.exists()
    manifest.write_text(json.dumps({"scope": "CPU fixture receipts and actual SQL dumps",
        "files": files}, ensure_ascii=False, indent=2) + "\n")
    proof = {"verified": True, "scope": "independent CPU artifact and source reconstruction; no real model verification",
        "receipts_verified": 132, "SQL_dumps_reconstructed": SQL,
        "paired_fixture_messages_matched": 66, "external_files_hashed": len(files),
        "external_manifest": str(manifest), "external_manifest_sha256": sha(manifest),
        "group_reports_sha256": group_hashes, "summary_sha256": sha(work / "replay-cpu-v1.json"),
        "verifier_sha256": sha(Path(__file__)), "cases_sha256": sha(CASES),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "model_constructions": 0, "training_steps": 0, "GPU_allocations": 0,
        "actual_generate_hook_verified": False, "semantic_quality_approved": False}
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print("C52 independent CPU evidence:132receipts/264SQL/396external files/66message pairs;0 models")


if __name__ == "__main__":
    main()

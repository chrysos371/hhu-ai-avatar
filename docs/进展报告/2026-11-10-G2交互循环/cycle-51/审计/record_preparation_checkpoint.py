"""Read-only dependency observation plus immutable preparation checkpoint."""
import json
from pathlib import Path
import subprocess
import time

from run_python_regression import ROOT, BASE, snapshot, digest
from avatar.lab.data import evaluation_texts, screen_candidates, normalize_dialogue


def read(path):
    return json.loads(Path(path).read_text())


def main():
    output = BASE / "审计/工作目录/005-真实分词预检/preparation-observation-v2.json"
    assert not output.exists()
    current = snapshot()
    binding = read(BASE / "审计/工作目录/002-当前软件回归/python-first-binding.json")
    previous = binding["source_git_sha256"]
    assert all(current.get(name) == value for name, value in previous.items())
    assert current == previous
    new = {name: digest(ROOT / name) for name in (
        "evals/interaction/cycle-52/correction-transfer-cases.json",
        "evals/interaction/cycle-52/correction-transfer-protocol.json")}
    texts, hashes = evaluation_texts()
    cases = read(ROOT / "evals/interaction/cycle-52/correction-transfer-cases.json")["cases"]
    rejected = []
    for case in cases:
        for field in ("query_text", "followup_text"):
            text = case[field]
            assert text in texts
            row = normalize_dialogue("checkpoint-c52", "train", case["id"] + field,
                [text, "这只是隔离验证占位，并不是训练材料。"])
            accepted, failures = screen_candidates([row], texts,
                source_policy={"checkpoint-c52": {"language": "zh", "use": "experimental-sft"}})
            assert not accepted and "eval_overlap" in failures[0]["reasons"]
            rejected.append({"case": case["id"], "field": field})
    count = items = 0
    for number in range(3, 51):
        cycle = BASE.parent / f"cycle-{number:02}"
        seal = read(cycle / "审计/证据清单.json")
        assert all(digest(cycle / name) == value for name, value in seal.items())
        count += 1
        items += len(seal)
    migration = ROOT / "docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json"
    seal = read(migration)
    assert all(digest(migration.parent / name) == value for name, value in seal.items())
    count += 1
    items += len(seal)
    assert (count, items) == (49, 12072)
    aliases = json.loads(subprocess.check_output(["python3", "-B", "scripts/link_project_assets.py", "--check"],
        cwd=ROOT, text=True))
    assert len(aliases) == 9 and all(a["valid"] for a in aliases)
    refs = [BASE / "审计/工作目录/003-环境与基础权重/range-third-independent-v1.json",
        BASE / "审计/工作目录/003-环境与基础权重/second-shard-independent-v1.json",
        BASE.parent / "cycle-52/审计/工作目录/002-重放预检/replay-cpu-v1.json"]
    observations = []
    for pid in (407654, 407422, 420640, 427542):
        path = Path(f"/proc/{pid}")
        if path.exists():
            observations.append({"pid": pid, "present_at_observation": True,
                "command": (path / "cmdline").read_bytes().decode().split("\0")[:-1],
                "start_ticks": (path / "stat").read_text().split()[21]})
        else:
            observations.append({"pid": pid, "present_at_observation": False})
    authors = subprocess.check_output(["git", "log", "08ac8187..HEAD", "--format=%an <%ae>"],
        cwd=ROOT, text=True).splitlines()
    assert set(authors) == {"spinner-bot <langxibielangle@qq.com>"}
    proof = {"verified": True, "scope": "preparation checkpoint; live observations expire and are not admission",
        "observed_UTC": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "verifier_sha256": digest(Path(__file__)), "historical_regression_inputs_unchanged": len(previous),
        "historical_Python_result": "2540 passed,1 skipped; not a newly executed full suite",
        "additional_registered_eval_inputs": new, "current_software_inputs": len(current),
        "actual_C52_fields_rejected": rejected, "protected_eval_hashes": hashes,
        "old_seals": count, "old_items": items, "asset_aliases_valid": 9,
        "authors_checked": len(authors), "processes_at_observation_only": observations,
        "completed_evidence_sha256": {str(p.relative_to(ROOT)): digest(p) for p in refs},
        "model_constructions": 0, "GPU_allocations": 0, "training_steps": 0,
        "real_training_admitted": False, "cycle51_complete": False, "goal_active": True}
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print("Preparation checkpoint:", len(previous), "historical inputs unchanged +", len(new),
        "registered eval files;44 fields rejected;49/12072 old seal items;9 aliases;no model admission")


if __name__ == "__main__":
    main()

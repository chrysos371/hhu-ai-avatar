"""Post-execution group archival only; never starts or changes model execution."""
import argparse
import json
from pathlib import Path
import shutil
import sys

AUDIT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AUDIT))
from execution_common import ROOT, RUN, read, sha, require, write_new
from capture_transformers import validate_call
from replay_common import CASES, case_for_replay, inspect_observations


def main(stage, repetition):
    phase = RUN / stage
    source = phase / f"repetition-{repetition}/group.json"
    group = read(source)
    require(group["completed"] is True and len(group["trials"]) == 22, "group is not closed")
    cases = {c["id"]: case_for_replay(c) for c in read(CASES)["cases"]}
    require([t["case"] for t in group["trials"]] == list(cases), "case set/order differs")
    files = {str(source.relative_to(phase)): sha(source)}
    SQL = 0
    for trial in group["trials"]:
        folder = phase / trial["folder"]
        receipt = read(folder / "receipt.json")
        require(sha(folder / "receipt.json") == trial["receipt_sha256"], "receipt changed")
        require(trial["source_error"] is None, "registered source failure")
        SQL += inspect_observations(folder, receipt, cases[trial["case"]], "production_snapshot")
        for p in folder.iterdir():
            require(p.is_file(), "unexpected nested artifact")
            files[str(p.relative_to(phase))] = sha(p)
        for ordinal in trial["call_ordinals"]:
            entry = phase / f"actual-generate/{ordinal:04}-entry.json"
            result = phase / f"actual-generate/{ordinal:04}-result.json"
            start = read(entry); row = read(result)
            require(row["completed"] is True and row["fixture"] is False, "actual generation incomplete")
            require(all(row[k] == v for k, v in start.items()), "trace entry changed")
            validate_call(row)
            for p in [entry, result]:
                files[str(p.relative_to(phase))] = sha(p)
    require(SQL == 44 and len(files) == 155, "closed-group counts differ")
    target = Path(__file__).parent / f"{stage}-repetition-{repetition}"
    require(not target.exists(), "group already archived")
    target.mkdir()
    shutil.copyfile(source, target / "group.json")
    write_new(target / "external-files.json", files)
    write_new(target / "verification.json", {"verified": True, "stage": stage,
        "repetition": repetition, "actual_trials": 22, "actual_generations": 44,
        "SQL_reconstructed": SQL, "external_files": len(files), "external_root": str(phase),
        "external_manifest_sha256": sha(target / "external-files.json"),
        "group_sha256": sha(target / "group.json"), "collector_sha256": sha(Path(__file__)),
        "semantic_review_pending": True, "whole_phase_verified": False})
    print(stage, repetition, "closed-group verified:22 trials/44 generates/44 SQL/155 external hashes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, choices=["before", "after"])
    parser.add_argument("--repetition", required=True, type=int, choices=[1, 2, 3])
    args = parser.parse_args()
    main(args.stage, args.repetition)

"""Full fixed-clock C52 CPU plumbing rehearsal; all responses are scripted."""
import hashlib
import json
from pathlib import Path
import subprocess
import time
from unittest.mock import patch

from avatar.lab.common import sha
from avatar.lab.runner import ReplyScopedModel
from capture_transformers import actual_wallclock, digest
from replay_common import (ROOT, BASE, ASSETS, PRIOR, CASES, PROTOCOL, read,
    case_for_replay, sample_trial, inspect_observations)


class PlumbingTeacher:
    def __init__(self):
        self.calls = []

    def generate(self, messages, kind, adapter):
        row = {"messages": json.loads(json.dumps(messages, ensure_ascii=False)),
            "kind": kind, "adapter_requested_fixture_flag_only": adapter, "fixture": True}
        self.calls.append(row)
        return {"reply": ('{"emotion":{"valence":0,"arousal":0},"facts":[]}'
                if kind == "analysis" else "纯CPU流程占位；不是模型回答或语义评分。"),
            "adapter_enabled": adapter, "seconds": 0.0, "new_tokens": 0,
            "truncated": False, "fixture": True}


def main():
    output = ASSETS / "artifacts/c52/plumbing-cpu-v1"
    assert not output.exists()
    work = BASE / "审计/工作目录/002-重放预检"
    work.mkdir(exist_ok=False)
    output.mkdir(parents=True)
    protocol = read(PROTOCOL)
    assert sha(CASES) == protocol["cases_sha256"]
    cases = read(CASES)["cases"]
    assert len(cases) == 22
    messages_before = {}
    groups = []
    real_before = actual_wallclock()
    all_calls = all_SQL = all_trials = 0
    with patch("time.time", return_value=protocol["evaluation"]["controlled_query_clock_epoch"]):
        assert time.time() == protocol["evaluation"]["controlled_query_clock_epoch"]
        assert abs(actual_wallclock() - real_before) < 5
        for phase in protocol["evaluation"]["phases"]:
            teacher = PlumbingTeacher()
            arm = "style_prompt" if phase.startswith("before_") else "style_lora"
            engine = ReplyScopedModel(teacher, arm=arm)
            for role in ("analysis", "reply"):
                teacher.generate([{"role": "system", "content": "CPU plumbing fixture"},
                    {"role": "user", "content": "warmup fixture"}], role, False)
            for repetition in range(1, 4):
                trials = []
                for original in cases:
                    case = case_for_replay(original)
                    folder = output / phase / f"repetition-{repetition}" / case["id"]
                    start = len(teacher.calls)
                    receipt = sample_trial(engine, case, "production_snapshot", repetition,
                        folder, on_context=lambda _: None, native_counter=lambda: len(teacher.calls))
                    count = inspect_observations(folder, receipt, case, "production_snapshot")
                    calls = teacher.calls[start:]
                    assert count == 2 and [c["kind"] for c in calls] == ["analysis", "reply"]
                    assert receipt["model_modes_valid"] and receipt["business_unchanged_by_query_and_ordinary"]
                    assert receipt["no_new_user_facts"] and receipt["actual_query_turns"] == 1
                    assert receipt["query_observations"][0]["result"]["reminder_query"]["observed_at"] == time.time()
                    key = (repetition, case["id"])
                    actual = [c["messages"] for c in calls]
                    if phase.startswith("before_"):
                        messages_before[key] = actual
                    else:
                        assert actual == messages_before[key]
                        assert digest(actual) == digest(messages_before[key])
                    trials.append({"case": case["id"], "family": case["family"],
                        "actual_input_messages_sha256": digest(actual), "SQL_reconstructed": count,
                        "receipt": str(folder / "receipt.json"), "receipt_sha256": sha(folder / "receipt.json"),
                        "scripted_interfaces": 2, "actual_model_calls": 0})
                    all_SQL += count
                    all_trials += 1
                group = {"completed": True, "fixture": True, "phase": phase,
                    "repetition": repetition, "trials": trials, "actual_model_calls": 0,
                    "actual_SQL_reconstructed": sum(t["SQL_reconstructed"] for t in trials)}
                name = f"{phase}-rep-{repetition}-cpu-v1.json"
                (work / name).write_text(json.dumps(group, ensure_ascii=False, indent=2) + "\n")
                groups.append(name)
                print(phase, repetition, "22 CPU trials/44SQL closed;0 real models", flush=True)
            assert len(teacher.calls) == protocol["evaluation"]["generation_cap_per_phase"] == 134
            all_calls += len(teacher.calls)
    assert (all_trials, all_SQL, all_calls) == (132, 264, 268)
    proof = {"passed": True, "scope": "actual Avatar/SQLite CPU rehearsal with scripted responses; not model inference or quality",
        "groups": groups, "CPU_trials": all_trials, "SQL_dumps_reconstructed": all_SQL,
        "scripted_interfaces_including_four_warmups": all_calls, "model_constructions": 0,
        "actual_model_calls": 0, "GPU_allocations": 0, "training_steps": 0,
        "before_after_message_bytes_matched_for_fixture": 66,
        "actual_model_input_or_adapter_hook_verified": False,
        "controlled_query_clock_did_not_replace_capture_wallclock": True,
        "cases_sha256": sha(CASES), "protocol_sha256": sha(PROTOCOL),
        "source_sha256": {str(p.relative_to(ROOT)): sha(p) for p in
            (Path(__file__), Path(__file__).with_name("replay_common.py"),
                Path(__file__).with_name("capture_transformers.py"),
                PRIOR / "sample_history.py", PRIOR / "verify_observations.py")},
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "external_output": str(output), "semantic_quality_approved": False}
    (work / "replay-cpu-v1.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print("C52 CPU rehearsal:132trials/264SQL/268scripted calls;66 matched fixture message pairs;0 models")


if __name__ == "__main__":
    main()

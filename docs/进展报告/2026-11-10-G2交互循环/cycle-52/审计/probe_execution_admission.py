"""Actual CLI refusal and CPU stage/GPU-selection controls, zero model calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import execution_common as common
import run_execution as runner


def denied(name, operation, results):
    try:
        operation()
    except ValueError as error:
        results.append({"control": name, "rejected": True, "reason": str(error)})
    else:
        raise AssertionError("admission control accepted: " + name)


def main():
    work = common.BASE / "审计/工作目录/004-真实执行准入负控"
    output = work / "admission-cpu-v1.json"
    assert not output.exists() and not common.RUN.exists()
    work.mkdir(parents=True, exist_ok=True)
    wrapper = '''import json,runpy,sys
script=sys.argv[1];sys.argv=sys.argv[1:]
try:
 runpy.run_path(script,run_name='__main__')
except BaseException as error:
 print(json.dumps({'rejected':True,'error_type':type(error).__name__,'torch_imported':'torch' in sys.modules,'peft_imported':'peft' in sys.modules}))
 raise
raise AssertionError('CLI unexpectedly returned without rejection')
'''
    inputs = [
        ("unready_C51_freeze", "freeze_execution.py", ["--c51-seal-sha256", "0" * 64]),
        ("missing_actual_freeze", "run_execution.py", ["--freeze", str(common.WORK / "freeze-v1.json"),
            "--expected-freeze-sha256", "0" * 64, "--stage", "before"]),
        ("wrong_freeze_path", "run_execution.py", ["--freeze", str(common.ASSETS / "tmp/not-an-experiment-freeze.json"),
            "--expected-freeze-sha256", "0" * 64, "--stage", "before"]),
        ("unknown_stage", "run_execution.py", ["--freeze", str(common.WORK / "freeze-v1.json"),
            "--expected-freeze-sha256", "0" * 64, "--stage", "unknown"]),
    ]
    CLI = []
    for name, script, arguments in inputs:
        command = [sys.executable, "-B", "-c", wrapper, str(Path(__file__).with_name(script)), *arguments]
        result = subprocess.run(command, cwd=common.ROOT, text=True, capture_output=True,
            env=dict(os.environ, CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1"))
        state = json.loads(result.stdout.strip())
        assert result.returncode != 0 and state["rejected"]
        assert not state["torch_imported"] and not state["peft_imported"]
        assert not common.RUN.exists() and not (common.WORK / "freeze-v1.json").exists()
        common.write_new(work / (name + ".json"), {"argv": command, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr, "module_observation": state})
        CLI.append(name)
    controls = []
    original = common.read(common.PROTOCOL)
    for name, section, key, value in (("float_training_steps", "training", "max_steps", 44.0),
            ("boolean_sampling_cap", "evaluation", "generation_cap_per_phase", True),
            ("float_sampling_cap", "evaluation", "generation_cap_per_phase", 134.0),
            ("analysis_adapter_enabled", "training", "analysis_adapter_enabled", True)):
        changed = copy.deepcopy(original)
        changed[section][key] = value
        actual_read = common.read
        with patch.object(common, "read", side_effect=lambda path: changed if path == common.PROTOCOL else actual_read(path)):
            denied(name, common.protocol_check, controls)
    with tempfile.TemporaryDirectory(prefix="c52-admission-cpu-", dir=common.ASSETS / "tmp") as temporary:
        root = Path(temporary)
        with patch.object(runner, "RUN", root):
            runner.previous_stage_check("before", "0" * 64)
            common.write_new(root / "ledger/before-start.json", {"fixture": True})
            denied("repeated_stage_attempt", lambda: runner.previous_stage_check("before", "0" * 64), controls)
            denied("training_before_independent_baseline_retirement",
                lambda: runner.previous_stage_check("train", "0" * 64), controls)
    cards = [{"index": 6, "uuid": "fixture-busy", "free_mib": 10000, "used_mib": 31000, "utilization": 95},
        {"index": 7, "uuid": "fixture-idle", "free_mib": 40000, "used_mib": 0, "utilization": 0}]
    with patch.object(runner, "gpu_cards", return_value=cards):
        selected, _ = runner.choose_gpu(None)
        assert selected["index"] == 7
        denied("explicit_busy_GPU_no_CPU_fallback", lambda: runner.choose_gpu(6), controls)
    proof = {"passed": True, "scope": "four actual unready/invalid CLI refusals plus CPU protocol/ledger/resource fixtures",
        "actual_CLI_refusals": CLI, "CPU_faults_rejected": controls,
        "automatic_idle_GPU_fixture_selected": 7, "fixture_GPU_indices_not_current_inventory": True,
        "no_real_output_created": not common.RUN.exists(), "model_constructions": 0,
        "GPU_allocations": 0, "training_steps": 0, "actual_model_hook_verified": False,
        "source_sha256": {p.name: common.sha(p) for p in Path(__file__).parent.glob("*.py")},
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=common.ROOT, text=True).strip()}
    common.write_new(output, proof)
    print("C52 execution admission:4 actual CLI refusals without Torch/PEFT imports;7 CPU faults rejected;0 model/GPU")


if __name__ == "__main__":
    main()

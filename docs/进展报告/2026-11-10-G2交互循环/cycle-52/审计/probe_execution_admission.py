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
    work = common.BASE / "审计/工作目录/004-真实执行准入负控/cli-v2"
    output = work / "admission-cpu-v2.json"
    assert not output.exists() and not common.RUN.exists()
    work.mkdir(parents=True, exist_ok=True)
    wrapper = '''import json,runpy,sys
from pathlib import Path
script=sys.argv[1];sys.argv=sys.argv[1:]
sys.path.insert(0,str(Path(script).parent))
try:
 runpy.run_path(script,run_name='__main__')
except BaseException as error:
 print(json.dumps({'rejected':True,'error_type':type(error).__name__,'error_message':str(error),'torch_imported':'torch' in sys.modules,'peft_imported':'peft' in sys.modules}))
 raise
raise AssertionError('CLI unexpectedly returned without rejection')
'''
    inputs = [
        ("unready_C51_freeze", "freeze_execution.py", ["--c51-seal-sha256", "0" * 64],
            "ValueError", "C51 independent environment admission missing"),
        ("missing_actual_freeze", "run_execution.py", ["--freeze", str(common.WORK / "freeze-v1.json"),
            "--expected-freeze-sha256", "0" * 64, "--stage", "before"],
            "ValueError", "C52 frozen execution descriptor missing"),
        ("wrong_freeze_path", "run_execution.py", ["--freeze", str(common.ASSETS / "tmp/not-an-experiment-freeze.json"),
            "--expected-freeze-sha256", "0" * 64, "--stage", "before"],
            "ValueError", "C52 registered freeze path required"),
        ("unknown_stage", "run_execution.py", ["--freeze", str(common.WORK / "freeze-v1.json"),
            "--expected-freeze-sha256", "0" * 64, "--stage", "unknown"],
            "SystemExit", "invalid choice: 'unknown'"),
    ]
    CLI = []
    for name, script, arguments, expected_type, expected_message in inputs:
        command = [sys.executable, "-B", "-c", wrapper, str(Path(__file__).with_name(script)), *arguments]
        result = subprocess.run(command, cwd=common.ROOT, text=True, capture_output=True,
            env=dict(os.environ, CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1"))
        state = json.loads(result.stdout.strip())
        assert result.returncode != 0 and state["rejected"]
        assert state["error_type"] == expected_type and expected_message in result.stderr
        assert "ModuleNotFoundError" not in result.stderr
        assert not state["torch_imported"] and not state["peft_imported"]
        direct_command = [sys.executable, "-B", str(Path(__file__).with_name(script)), *arguments]
        direct = subprocess.run(direct_command, cwd=common.ROOT, text=True, capture_output=True,
            env=dict(os.environ, CUDA_VISIBLE_DEVICES="", HF_HUB_OFFLINE="1"))
        assert direct.returncode == result.returncode and expected_message in direct.stderr
        assert "ModuleNotFoundError" not in direct.stderr
        assert not common.RUN.exists() and not (common.WORK / "freeze-v1.json").exists()
        common.write_new(work / (name + ".json"), {"argv": command, "returncode": result.returncode,
            "stdout": result.stdout, "stderr": result.stderr, "module_observation": state,
            "expected_error_type": expected_type, "expected_message": expected_message,
            "direct_argv": direct_command, "direct_returncode": direct.returncode,
            "direct_stdout": direct.stdout, "direct_stderr": direct.stderr})
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
    proof = {"passed": True, "scope": "four paired normal/wrapped actual CLI refusals with exact error type/reason, plus CPU fixtures",
        "actual_CLI_processes": 8, "normal_and_wrapped_reasons_matched": True,
        "actual_CLI_refusals": CLI, "CPU_faults_rejected": controls,
        "automatic_idle_GPU_fixture_selected": 7, "fixture_GPU_indices_not_current_inventory": True,
        "no_real_output_created": not common.RUN.exists(), "model_constructions": 0,
        "GPU_allocations": 0, "training_steps": 0, "actual_model_hook_verified": False,
        "source_sha256": {p.name: common.sha(p) for p in Path(__file__).parent.glob("*.py")},
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=common.ROOT, text=True).strip()}
    common.write_new(output, proof)
    print("C52 execution admission v2:4 paired controls/8 actual CLI refusals,exact reasons,no import failures;7 CPU faults;0 model/GPU")


if __name__ == "__main__":
    main()

"""CPU control for NVML-index lock/CUDA-UUID visibility, without a real GPU lease."""
from contextlib import contextmanager
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from execution_common import BASE, ROOT, sha, write_new
from run_execution import uuid_lease


def main():
    output = BASE / "审计/工作目录/004-真实执行准入负控/uuid-lease-cpu-v1.json"
    assert not output.exists()
    selected = {"index": 7, "uuid": "GPU-fixture-selected-physical-device"}
    events = []
    @contextmanager
    def original(indices, count):
        events.append(["enter", indices, count])
        os.environ["CUDA_VISIBLE_DEVICES"] = str(indices[0])
        try:
            yield
        finally:
            events.append(["exit", indices, count])
    with patch.dict(os.environ):
        lease = uuid_lease(original, selected)
        with lease([7], 1):
            assert os.environ["CUDA_VISIBLE_DEVICES"] == selected["uuid"]
        assert events == [["enter", [7], 1], ["exit", [7], 1]]
        try:
            with lease([7], 1):
                assert os.environ["CUDA_VISIBLE_DEVICES"] == selected["uuid"]
                raise RuntimeError("fixture body failure")
        except RuntimeError as error:
            assert str(error) == "fixture body failure"
        assert events[-1] == ["exit", [7], 1]
        before = list(events)
        try:
            with lease([6], 1):
                raise AssertionError("wrong device entered body")
        except ValueError as error:
            assert "registered single-GPU lease differs" in str(error)
        assert events == before
    assert "torch" not in sys.modules
    write_new(output, {"passed": True, "scope": "CPU fixture original lease;not current GPU inventory or hardware mapping proof",
        "correct_NVML_index_preserved": True, "CUDA_visibility_overridden_by_UUID": True,
        "original_context_exited_on_body_failure": True, "wrong_index_rejected_before_lease": True,
        "source_sha256": {p.name: sha(p) for p in (Path(__file__), Path(__file__).with_name("run_execution.py"))},
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "model_constructions": 0, "GPU_allocations": 0, "training_steps": 0,
        "actual_hardware_UUID_verification_pending": True})
    print("C52 UUID lease CPU control:NVML index lock retained,UUID visibility,exception cleanup,wrong-index refusal;0 GPU")


if __name__ == "__main__":
    main()

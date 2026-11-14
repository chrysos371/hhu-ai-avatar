"""Current real data admission and six model/protocol/tokenization binding faults."""
import copy
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import execution_common as common


def main():
    output = common.BASE / "审计/工作目录/004-真实执行准入负控/protocol-bindings-cpu-v1.json"
    assert not output.exists()
    original = common.protocol_check()
    assert "torch" not in sys.modules and "peft" not in sys.modules
    manifest_path = common.DATA.with_name("manifest.json")
    original_manifest = common.read(manifest_path)
    results = []
    actual_read, actual_sha = common.read, common.sha
    for name in ("model_revision", "model_shard_SHA", "export_protocol_SHA",
            "tokenized_manifest_SHA", "tokenized_config_SHA", "training_data_SHA"):
        protocol = copy.deepcopy(original)
        manifest = copy.deepcopy(original_manifest)
        modified_path = None
        if name == "model_revision":
            protocol["model"]["revision"] = "0" * 40
        elif name == "model_shard_SHA":
            protocol["model"]["sha256"]["model-00001-of-00003.safetensors"] = "0" * 64
        elif name == "export_protocol_SHA":
            manifest["protocol_sha256"] = "0" * 64
        elif name == "tokenized_manifest_SHA":
            modified_path = manifest_path
        elif name == "tokenized_config_SHA":
            modified_path = common.TOKENIZATION / "training-config-v1.json"
        else:
            modified_path = common.DATA
        def read(path):
            if path == common.PROTOCOL:
                return protocol
            if path == manifest_path:
                return manifest
            return actual_read(path)
        def sha(path):
            return "0" * 64 if path == modified_path else actual_sha(path)
        with patch.object(common, "read", side_effect=read), patch.object(common, "sha", side_effect=sha):
            try:
                common.protocol_check()
            except ValueError as error:
                results.append({"fault": name, "rejected": True, "reason": str(error)})
            else:
                raise AssertionError("model/data binding accepted: " + name)
    assert not common.RUN.exists() and "torch" not in sys.modules
    common.write_new(output, {"passed": True,
        "scope": "actual current dataset passes existing load_data plus C52 bindings; six patched observation faults rejected",
        "current_train_samples": 176, "current_dev_samples": 44, "faults_rejected": results,
        "source_sha256": {p.name: actual_sha(p) for p in (Path(__file__),
            Path(__file__).with_name("execution_common.py"))},
        "protocol_sha256": actual_sha(common.PROTOCOL), "dataset_manifest_sha256": actual_sha(manifest_path),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=common.ROOT, text=True).strip(),
        "torch_imported": False, "model_constructions": 0, "training_steps": 0, "GPU_allocations": 0,
        "actual_model_hook_verified": False})
    print("C52 model/data binding:actual176/44 admitted,6 faults rejected;0 Torch/model/GPU")


if __name__ == "__main__":
    main()

"""Read an independently admitted environment, never infer readiness from a version name."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
PREPARATION = Path(__file__).parent / "工作目录/003-环境与基础权重"
TARGET = Path("/data/Users/zrh/data/hhu-ai-avatar/envs/hhu-ai-avatar-train")
ADMISSION = PREPARATION / "environment-admission.json"
SOURCES = ("environment-v3/environment-v3.json", "environment-v4/environment-v4.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def successful_source(name):
    require(name in SOURCES, "unregistered environment preparation source")
    path = PREPARATION / name
    require(path.is_file() and path.resolve().is_relative_to(PREPARATION.resolve()),
        "environment preparation source missing or outside registered directory")
    source = json.loads(path.read_text())
    require(source["status"] == "complete", "environment preparation is not complete")
    require(source["target"] == str(TARGET), "environment preparation target differs")
    require(source["existing_environments_unchanged"] is True
        and source["original_environments_before"] == source["original_environments_after"],
        "original environments changed")
    require(source["CPU_import_probe"]["CPU_imports_passed"] is True
        and source["CPU_import_probe"]["CUDA_initialized"] is False, "CPU import preparation invalid")
    return path, source


def admitted_environment():
    require(ADMISSION.is_file(), "C51 independent environment admission missing")
    admission = json.loads(ADMISSION.read_text())
    require(admission["verified"] is True and admission["target"] == str(TARGET),
        "C51 environment admission is not verified")
    require(admission["reader_sha256"] == sha(Path(__file__))
        and admission["verifier_sha256"] == sha(Path(__file__).with_name("verify_training_environment.py")),
        "environment admission verification source changed")
    path, source = successful_source(admission["preparation_source"])
    require(sha(path) == admission["preparation_source_sha256"], "successful environment source changed")
    require(source["installed"] == admission["installed"], "admitted package inventory differs")
    require(admission["actual_pip_check_passed"] is True
        and admission["actual_CPU_imports_passed"] is True
        and admission["existing_environments_unchanged"] is True, "independent environment checks missing")
    return source

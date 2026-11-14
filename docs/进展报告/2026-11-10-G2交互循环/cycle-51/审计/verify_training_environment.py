"""Independently admit a completed preparation using current installed state, CPU only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from environment_receipt import (ROOT, PREPARATION, TARGET, ADMISSION, SOURCES,
    require, sha, successful_source)
from prepare_training_environment import inventory


def main(name):
    require(not ADMISSION.exists(), "independent environment admission already exists")
    path, source = successful_source(name)
    # No installer may still be writing this target, including a replacement process.
    for proc in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            command = proc.read_bytes().decode().split("\0")[:-1]
        except (OSError, UnicodeDecodeError):
            continue
        require(not (command and command[0] == str(TARGET / "bin/python")
            and "pip" in command and "install" in command), "target pip install is still running")
    assets = TARGET.parents[1]
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1",
        PYTHONPATH=str(ROOT / "src"), TMPDIR=str(assets / "tmp"),
        TRITON_CACHE_DIR=str(assets / "cache/triton"),
        TORCHINDUCTOR_CACHE_DIR=str(assets / "cache/torchinductor"),
        CUDA_CACHE_PATH=str(assets / "cache/cuda-kernels"))
    installed = inventory(TARGET / "bin/python", env)
    require(installed == source["installed"], "current installed environment differs from completed preparation")
    originals = {name: inventory(assets / "envs" / name / "bin/python", env)
        for name in source["original_environments_before"]}
    require(originals == source["original_environments_before"], "current original environments changed")
    result = subprocess.run([str(TARGET / "bin/python"), "-m", "pip", "check"],
        cwd=ROOT, env=env, text=True, capture_output=True)
    require(result.returncode == 0, "current pip check failed: " + result.stdout + result.stderr)
    code = '''import json,sys,hashlib,importlib.metadata as m,torch,transformers,peft,accelerate,lmformatenforcer,interegular
from pathlib import Path
import huggingface_hub,safetensors,tokenizers
from transformers import Qwen3ForCausalLM,AutoTokenizer
names=['transformers','tokenizers','huggingface_hub','safetensors','peft','accelerate','lm-format-enforcer','interegular','numpy','edge-tts','openai','python-dotenv','Jinja2','pip']
files={Path(module.__file__).resolve() for module in (torch,torch._C,transformers,peft,accelerate,lmformatenforcer,interegular,huggingface_hub,safetensors,tokenizers)}
for line in Path('/proc/self/maps').read_text().splitlines():
 fields=line.split(maxsplit=5)
 if len(fields)==6 and fields[5].startswith(sys.prefix+'/') and '.so' in Path(fields[5]).name:
  assert '(deleted)' not in fields[5]
  files.add(Path(fields[5]).resolve())
hashes={}
for path in sorted(files):
 assert path.is_relative_to(Path(sys.prefix).resolve()) and path.is_file()
 digest=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(8*1024*1024),b''):digest.update(block)
 hashes[str(path)]=digest.hexdigest()
print(json.dumps({'prefix':sys.prefix,'torch':torch.__version__,'CUDA_build':torch.version.cuda,'CUDA_initialized':torch.cuda.is_initialized(),'torch_cuda_visible_count':torch.cuda.device_count(),'Qwen3_class':Qwen3ForCausalLM.__name__,'versions':{n:m.version(n) for n in names},'runtime_files_sha256':hashes,'runtime_files_scope':'imported ML entry modules and currently mapped target-prefix shared libraries;not host drivers or future lazy loads','CPU_imports_passed':True}))
'''
    actual = json.loads(subprocess.check_output([str(TARGET / "bin/python"), "-B", "-c", code], cwd=ROOT, env=env, text=True))
    expected = {"transformers": "4.57.6", "tokenizers": "0.22.2", "huggingface_hub": "0.36.2",
        "safetensors": "0.7.0", "peft": "0.17.1", "accelerate": "1.10.1",
        "lm-format-enforcer": "0.11.3", "interegular": "0.3.3", "pip": "25.3"}
    require(all(actual["versions"][key] == value for key, value in expected.items()), "fixed training packages differ")
    require(actual["prefix"] == str(TARGET) and actual["torch"] == "2.6.0+cu124"
        and actual["CUDA_build"] == "12.4" and actual["CUDA_initialized"] is False
        and actual["torch_cuda_visible_count"] == 0 and actual["Qwen3_class"] == "Qwen3ForCausalLM",
        "independent CPU runtime identity differs")
    require(len(actual["runtime_files_sha256"]) >= 10, "installed ML runtime byte identity missing")
    token_protocol = json.loads((PREPARATION.parent / "005-真实分词预检/tokenizer-protocol.json").read_text())
    require(all(actual["versions"][key] == token_protocol["packages"][key]
        for key in ("transformers", "tokenizers", "huggingface_hub", "safetensors", "numpy", "Jinja2")),
        "training/tokenizer package identity differs")
    value = {"verified": True, "scope": "current installed CPU environment identity, not CUDA/model execution",
        "target": str(TARGET), "preparation_source": name, "preparation_source_sha256": sha(path),
        "installed": installed, "actual_CPU_probe": actual, "pip_check_stdout": result.stdout,
        "actual_pip_check_passed": True, "actual_CPU_imports_passed": True,
        "existing_environments_unchanged": True, "verifier_sha256": sha(Path(__file__)),
        "reader_sha256": sha(Path(__file__).with_name("environment_receipt.py")),
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "model_constructions": 0, "GPU_allocations": 0, "training_steps": 0}
    with ADMISSION.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("C51 current training environment independently admitted on CPU;source", name, ";no CUDA/model/quality approval")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation-source", choices=SOURCES, required=True)
    main(parser.parse_args().preparation_source)

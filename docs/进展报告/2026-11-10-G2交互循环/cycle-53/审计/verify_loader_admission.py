"""Compare preserved and fixed real loaders on whole datasets, CPU only."""
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import sys

from avatar.lab.common import canonical, sha, write_json
from avatar.lab.training import load_data

BASE = Path(__file__).resolve().parents[1]
WORK = BASE / "审计/工作目录/002-加载准入修复"
OLD = BASE / "审计/工作目录/001-训练材料结构"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")
DATA = ASSETS / "artifacts/c51/correction-data-v1"
OUT = ASSETS / "artifacts/c53/loader-admission-v1"


def read(path): return json.loads(Path(path).read_text())


def main():
    path = OLD / "training-before-row-integrity.py.txt"
    assert sha(path) == read(OLD / "original-loader-binding-v1.json")["sha256"]
    loader = importlib.machinery.SourceFileLoader("avatar.lab._c53_original_training", str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    original = importlib.util.module_from_spec(spec); loader.exec_module(original)
    train, dev, manifest = load_data(DATA / "sft.jsonl")
    assert (len(train), len(dev)) == (176,44)
    assert not OUT.exists() and not (WORK / "independent-admission-v1.json").exists()
    OUT.mkdir(parents=True)
    cases = {}
    stale = ASSETS / "artifacts/c53/data-structure-v1/stale_row_content_hash_with_fresh_file_manifest/sft.jsonl"
    cases["stale_row_hash"] = stale
    for kind in ["rehashed_protected_eval_text", "cross_split_dialogue_changed_system"]:
        folder = OUT/kind; folder.mkdir(); a=copy.deepcopy(train); b=copy.deepcopy(dev); m=copy.deepcopy(manifest)
        if kind=="rehashed_protected_eval_text":
            a[0]["messages"][-2]["content"] = "通知就由你打电话完成，完成拨打后回个结果。"
            a[0]["provenance"]["content_sha256"] = hashlib.sha256(canonical(a[0]["messages"]).encode()).hexdigest()
        else:
            identity = b[0]["id"]
            b[0]=copy.deepcopy(a[0]);b[0]["id"]=identity;b[0]["messages"][0]["content"] += "\n额外系统说明，保持简洁。"
            b[0]["provenance"]["content_sha256"] = hashlib.sha256(canonical(b[0]["messages"]).encode()).hexdigest()
        for name, rows in [("sft.jsonl",a),("dev.jsonl",b)]:
            (folder/name).write_text("".join(canonical(r)+"\n" for r in rows))
        m.update(sft_sha256=sha(folder/"sft.jsonl"),dev_sha256=sha(folder/"dev.jsonl"));write_json(folder/"manifest.json",m)
        cases[kind]=folder/"sft.jsonl"
    results=[]
    for name,data in cases.items():
        before=original.load_data(data);assert (len(before[0]),len(before[1]))==(176,44)
        try:load_data(data)
        except ValueError as error:
            reason=str(error)
        else:raise AssertionError("fixed loader accepted " + name)
        expected={"stale_row_hash":"content provenance","rehashed_protected_eval_text":"eval_overlap",
            "cross_split_dialogue_changed_system":"Duplicate actual dialogue"}[name]
        assert expected in reason,reason
        results.append({"case":name,"old_accepted":True,"new_rejected":True,"new_error":reason,
            "dataset":str(data),"sft_sha256":sha(data),"dev_sha256":sha(data.with_name("dev.jsonl")),"manifest_sha256":sha(data.with_name("manifest.json"))})
    assert "torch" not in sys.modules
    output={"verified":True,"scope":"independent whole-dataset loader admission only; not model quality or degradation cause",
        "original_176_train_44_dev_accepted":True,"old_loader_sha256":sha(path),
        "fixed_loader_sha256":sha(Path(__file__).resolve().parents[5]/"src/avatar/lab/training.py"),
        "verifier_sha256":sha(Path(__file__)),"actual_fault_comparisons":results,
        "original_input_sha256":{str(DATA/n):sha(DATA/n) for n in ["sft.jsonl","dev.jsonl","manifest.json"]},
        "new_model_generations":0,"new_training_steps":0,"Torch_imported":False,"GPU_allocations":0}
    write_json(WORK/"independent-admission-v1.json",output)
    print("C53 independent loader: original176/44 accepted;3 actual old-accept/new-reject full-dataset faults;0Torch/model/GPU")


if __name__=="__main__":main()

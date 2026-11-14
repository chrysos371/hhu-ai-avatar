"""C53 read-only system audit of current repair and preserved experiment data."""
import importlib.util
import json
from pathlib import Path
import subprocess

from avatar.lab.common import sha, write_json
from avatar.lab.training import load_data
from run_python_regression import ROOT, BASE, snapshot

WORK = BASE / "审计/工作目录"
OUT = BASE / "审计/收尾核验"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")


def read(path): return json.loads(Path(path).read_text())


def main():
    assert not (OUT/"system-evidence.json").exists()
    structure=read(WORK/"001-训练材料结构/structure-v1.json")
    assert structure["verified"] and structure["auditor_sha256"]==sha(BASE/"审计/audit_training_structure.py")
    for name,value in structure["input_sha256"].items(): assert sha(Path(name))==value
    raw=Path(structure["external_output"]); external=read(raw/"external-files.json")
    assert sha(raw/"external-files.json")==structure["external_manifest_sha256"]
    assert all(sha(raw/n)==v for n,v in external.items())
    rows={split:[json.loads(x) for x in (ASSETS/"artifacts/c51/correction-data-v1"/name).read_text().splitlines()]
        for split,name in [("train","sft.jsonl"),("dev","dev.jsonl")]}
    for split,items in rows.items():
        stats=structure["split_summary"][split]
        assert len(items)==stats["samples"] and len({r["messages"][-1]["content"] for r in items})==stats["literal_targets"]==11
        assert len({r["messages"][-2]["content"] for r in items})==stats["literal_last_users"]
        assert all(any("历史提醒查询快照" in m["content"] for m in r["messages"][:-1]) for r in items)
    train,dev,_=load_data(ASSETS/"artifacts/c51/correction-data-v1/sft.jsonl")
    assert len(train)==176 and len(dev)==44
    admission=read(WORK/"002-加载准入修复/independent-admission-v1.json")
    assert admission["verified"] and admission["fixed_loader_sha256"]==sha(ROOT/"src/avatar/lab/training.py")
    for fault in admission["actual_fault_comparisons"]:
        path=Path(fault["dataset"])
        assert sha(path)==fault["sft_sha256"] and sha(path.with_name("dev.jsonl"))==fault["dev_sha256"]
        assert sha(path.with_name("manifest.json"))==fault["manifest_sha256"] and fault["old_accepted"] and fault["new_rejected"]
        try:load_data(path)
        except ValueError as error:assert str(error)==fault["new_error"]
        else:raise AssertionError("fault no longer rejected")
    regression=read(WORK/"004-当前软件回归/python-first-binding.json"); software=snapshot()
    assert regression["exit_code"]==0 and regression["source_unchanged"] and software==regression["source_git_sha256"] and len(software)==494
    log=WORK/"004-当前软件回归/python-first.log"
    assert sha(log)==regression["log_sha256"] and "2548 passed, 1 skipped" in log.read_text()
    token=read(WORK/"005-修后真实分词/current-tokenization-v1.json")
    assert token["verified"] and token["current_training_module_sha256"]==sha(ROOT/"src/avatar/lab/training.py")
    current=Path(token["external_output"]);preflight=read(current/"preflight.json")
    assert sha(current/"preflight.json")==token["preflight_sha256"]
    assert sha(current/"tokens.json")==token["tokens_sha256"]=="2c3c37d4b866e2f9b272f1b69287323cc5df8e60a228dea5d8b5b22232e9d28b"
    assert all(sha(ASSETS/"models/Qwen3-4B"/n)==v for n,v in preflight["tokenizer_files"].items())
    items=0;seals=[]
    for number in range(3,53):
        cycle=BASE.parent/f"cycle-{number:02}";p=cycle/"审计/证据清单.json";data=read(p)
        assert all(sha(cycle/n)==v for n,v in data.items())
        items+=len(data);seals.append({"path":str(p.relative_to(ROOT)),"sha256":sha(p),"items":len(data)})
    p=ROOT/"docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json";data=read(p)
    assert all(sha(p.parent/n)==v for n,v in data.items());items+=len(data);seals.append({"path":str(p.relative_to(ROOT)),"sha256":sha(p),"items":len(data)})
    assert len(seals)==51 and items==12418
    aliases=json.loads(subprocess.check_output(["python3","-B","scripts/link_project_assets.py","--check"],cwd=ROOT,text=True))
    assert len(aliases)==9 and all(a["valid"] for a in aliases)
    names=set(software)
    names.update(str(p.relative_to(ROOT)) for p in WORK.rglob("*") if p.is_file())
    names.update(str(p.relative_to(ROOT)) for p in (BASE/"审计").glob("*.py"))
    names.update(str(p.relative_to(ROOT)) for p in (BASE/"审计").glob("*.mjs"))
    names.update(str(p.relative_to(ROOT)) for p in (BASE/"审计/问题单").glob("*.md"))
    names.update(["AGENTS.md","README.md","experiments/style/README.md"])
    hashes={n:sha(ROOT/n) for n in sorted(names)}
    # Use the existing pure archive reader, with its C52 freeze untouched.
    p=BASE.parent/"cycle-52/审计/execution_common.py"
    spec=importlib.util.spec_from_file_location("c52_archive_only",p);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
    assert module.historical(head,hashes)==hashes
    write_json(OUT/"system-evidence.json",{"verified":True,"scope":"C53 current loader repair and CPU material audit;no model quality or degradation causal claim",
        "head":head,"collector_sha256":sha(Path(__file__)),"source_sha256":hashes,"software_inputs":494,"Python_passed":2548,"Python_skipped":1,
        "actual_original_train":176,"actual_original_dev":44,"train_target_types":11,"dev_target_types":11,"train_followup_types":44,"dev_followup_types":11,
        "supervised_train_tokens_including_EOS":3936,"supervised_dev_tokens_including_EOS":984,"historical_snapshot_rows":220,
        "original_hash_scopes_compatible":2,"old_accept_new_reject_whole_dataset_faults":3,"targeted_tests_passed":11,
        "current_actual_token_sequences_identical":220,"tokens_sha256":token["tokens_sha256"],"old_seals":seals,"old_items":items,
        "central_aliases":9,"issues_limited_closed":1,"issues_open":2,"step_logging_actual_GPU_unverified":True,
        "new_LLM_generations":0,"new_training_steps":0,"GPU_allocations":0,"candidate_isolated":True,"default_model_changed":False,"overall_goal_active":True})
    print("C53 system:current2548/1,494inputs;3whole-loaderfaults;220sameactualtokens;51oldseals12418items;0newmodels/GPU")


if __name__=="__main__":main()

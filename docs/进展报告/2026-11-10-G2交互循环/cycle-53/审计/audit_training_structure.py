"""C53 CPU-only dataset structure and actual loader fault observations."""
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

from avatar.lab.common import canonical, sha, write_json
from avatar.lab.training import load_data

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE / "审计/工作目录/001-训练材料结构"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")
DATA = ASSETS / "artifacts/c51/correction-data-v1"
OUT = ASSETS / "artifacts/c53/data-structure-v1"


def digest(value): return hashlib.sha256(canonical(value).encode()).hexdigest()
def read(p): return json.loads(Path(p).read_text())
def normalized(value): return re.sub(r"\d+", "<N>", canonical(value))


def token_check(row):
    ids, labels = row["input_ids"], row["labels"]
    assert len(ids) == len(labels) and len(ids) <= 2048
    first = next(i for i, value in enumerate(labels) if value != -100)
    assert first > 0 and all(v == -100 for v in labels[:first])
    assert labels[first:] == ids[first:] and all(v >= 0 for v in labels[first:])
    return {"sequence_tokens": len(ids), "masked_tokens": first, "supervised_tokens_including_EOS": len(ids)-first}


def main():
    protocol = read(WORK / "protocol-v1.json")
    prior = BASE.parent / "cycle-52/审计/证据清单.json"
    assert sha(prior) == protocol["prior_seal_sha256"]
    assert all(sha(prior.parents[1] / n) == v for n, v in read(prior).items())
    assert not OUT.exists() and not (WORK / "structure-v1.json").exists()
    train, dev, manifest = load_data(DATA / "sft.jsonl")
    assert (len(train),len(dev)) == (176,44)
    token_path = ASSETS / "artifacts/c51/tokenizer-preflight-v1/tokens.json"
    mask = read(BASE.parent / "cycle-51/审计/工作目录/005-真实分词预检/mask-preflight-v1.json")
    assert sha(token_path) == mask["tokens_sha256"] and sha(DATA / "manifest.json") == mask["data_manifest_sha256"]
    tokens = read(token_path)
    summary = {}; detail = {}; all_rows = {"train":train,"dev":dev}
    for split, rows in all_rows.items():
        token_rows = {r["id"]:r for r in tokens[split]}
        assert set(token_rows) == {r["id"] for r in rows}
        groups = defaultdict(list)
        for row in rows: groups[row["provenance"]["family"]].append(row)
        families = {}
        for family, items in groups.items():
            supervised = [token_check(token_rows[r["id"]]) for r in items]
            families[family] = {"samples":len(items),"literal_targets":len({r["messages"][-1]["content"] for r in items}),
                "literal_last_users":len({r["messages"][-2]["content"] for r in items}),
                "exact_prefixes":len({canonical(r["messages"][:-1]) for r in items}),
                "digit_normalized_prefixes":len({normalized(r["messages"][:-1]) for r in items}),
                "supervised_tokens_including_EOS":sum(r["supervised_tokens_including_EOS"] for r in supervised),
                "sequence_tokens":sum(r["sequence_tokens"] for r in supervised)}
        summary[split] = {"samples":len(rows),"families":families,
            "literal_targets":len({r["messages"][-1]["content"] for r in rows}),
            "literal_last_users":len({r["messages"][-2]["content"] for r in rows}),
            "exact_prefixes":len({canonical(r["messages"][:-1]) for r in rows}),
            "digit_normalized_prefixes":len({normalized(r["messages"][:-1]) for r in rows}),
            "scripted_provenance":sum(r["provenance"]["source"]=="synthetic-actual-SDK-SQL-scripted-target" for r in rows),
            "history_snapshot_marker":sum(any("历史提醒查询快照" in m["content"] for m in r["messages"][:-1]) for r in rows),
            "full_messages_provenance_hash_matches":sum(r["provenance"]["content_sha256"]==digest(r["messages"]) for r in rows),
            "supervised_tokens_including_EOS":sum(v["supervised_tokens_including_EOS"] for v in families.values()),
            "sequence_tokens":sum(v["sequence_tokens"] for v in families.values())}
        detail[split] = [{"id":r["id"],"family":r["provenance"]["family"],
            "full_messages_sha256":digest(r["messages"]),"prefix_sha256":digest(r["messages"][:-1]),
            "digit_normalized_prefix_sha256":hashlib.sha256(normalized(r["messages"][:-1]).encode()).hexdigest(),
            "target":r["messages"][-1]["content"],"last_user":r["messages"][-2]["content"],**token_check(token_rows[r["id"]])} for r in rows]
    overlaps={}
    for name,fn in [("literal_targets",lambda r:r["messages"][-1]["content"]),
        ("literal_last_users",lambda r:r["messages"][-2]["content"]),
        ("full_messages",lambda r:canonical(r["messages"])),
        ("digit_normalized_full_messages",lambda r:normalized(r["messages"]))]:
        a={fn(r) for r in train};b={fn(r) for r in dev};overlaps[name]={"train_unique":len(a),"dev_unique":len(b),"shared_unique":len(a&b)}
    steps=read(ASSETS / "artifacts/c52/real-transfer-v1/adapter/steps.json")
    step_fields=sorted(set().union(*(s.keys() for s in steps)))
    assert len(steps)==44 and sum(s["samples"] for s in steps)==176
    OUT.mkdir(parents=True)
    observations=[]
    for fault in ["duplicate_split_id","stale_row_content_hash_with_fresh_file_manifest","target_byte_without_manifest_update"]:
        folder=OUT/fault;folder.mkdir();a=copy.deepcopy(train);b=copy.deepcopy(dev);m=copy.deepcopy(manifest)
        if fault=="duplicate_split_id": b[0]["id"]=a[0]["id"]
        else: a[0]["messages"][-1]["content"] += "（被改动的目标）"
        for name,rows in [("sft.jsonl",a),("dev.jsonl",b)]:
            (folder/name).write_text("".join(canonical(r)+"\n" for r in rows))
        if fault!="target_byte_without_manifest_update":
            m.update(sft_sha256=sha(folder/"sft.jsonl"),dev_sha256=sha(folder/"dev.jsonl"))
        write_json(folder/"manifest.json",m)
        try: loaded=load_data(folder/"sft.jsonl")
        except ValueError as error: observations.append({"fault":fault,"accepted":False,"error":str(error)})
        else: observations.append({"fault":fault,"accepted":True,"train_samples":len(loaded[0]),"dev_samples":len(loaded[1])})
    for fault in ["unmask_history_token","change_final_target_labels"]:
        row=copy.deepcopy(tokens["train"][0])
        if fault=="unmask_history_token": row["labels"][0]=row["input_ids"][0]
        else: row["labels"][-1]+=1
        try: token_check(row)
        except AssertionError: observations.append({"fault":fault,"accepted":False,"error":"actual cached-token mask/label invariant rejected"})
        else: observations.append({"fault":fault,"accepted":True})
    write_json(OUT/"per-row-structure.json",detail)
    files={str(p.relative_to(OUT)):sha(p) for p in OUT.rglob("*") if p.is_file()}
    write_json(OUT/"external-files.json",files)
    value={"verified":True,"scope":"CPU structural facts and actual loader observations; not cause of C52 degradation or semantic approval",
        "head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "auditor_sha256":sha(Path(__file__)),"protocol_sha256":sha(WORK/"protocol-v1.json"),
        "input_sha256":{str(p):sha(p) for p in [DATA/"sft.jsonl",DATA/"dev.jsonl",DATA/"manifest.json",token_path]},
        "split_summary":summary,"cross_split_overlap":overlaps,"fault_observations":observations,
        "optimizer_steps":44,"logged_samples_sum":176,"step_fields":step_fields,
        "actual_sample_ids_recorded_per_step":all("sample_ids" in s for s in steps),
        "actual_per_sample_order_independently_recoverable":False,
        "normalization_is_not_semantic_equivalence":True,"target_overlap_is_not_automatically_contamination":True,
        "external_output":str(OUT),"external_manifest_sha256":sha(OUT/"external-files.json"),
        "new_model_generations":0,"new_training_steps":0,"GPU_allocations":0,"candidate_isolated":True}
    write_json(WORK/"structure-v1.json",value)
    print("C53 CPU structure:",summary["train"]["literal_targets"],"train targets;",
        summary["train"]["literal_last_users"],"train followups;",summary["train"]["supervised_tokens_including_EOS"],"supervised tokens")
    print("actual loader fault observations",observations)


if __name__=="__main__":main()

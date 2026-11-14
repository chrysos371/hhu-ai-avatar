"""Independent target-only identity checks and real protected-field controls."""
import copy
import hashlib
import json
from pathlib import Path

from avatar.lab import data
from avatar.lab.common import canonical,sha,write_json
from avatar.lab.training import load_data
BASE=Path(__file__).resolve().parents[1]
ROOT=Path(__file__).resolve().parents[5]
ASSETS=Path("/data/Users/zrh/data/hhu-ai-avatar")
WORK=BASE/"审计/工作目录"
SOURCE=ASSETS/"artifacts/c51/correction-data-v1"
NEW=ASSETS/"artifacts/c54/target-expression-v1"


def read(p):return json.loads(Path(p).read_text())
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def verify(rows,parents,variants):
    checked=0
    for split,items in rows.items():
        assert len(items)==(176 if split=="train" else 44)
        for row in items:
            p=row["provenance"];original=parents[p["parent_row_id"]];family=original["provenance"]["family"]
            index=int(original["id"].rsplit("-",1)[1])%len(variants[split][family])
            assert row["id"]==original["id"].replace("c51-","c54-expression-",1)
            assert row["messages"][:-1]==original["messages"][:-1]
            assert row["messages"][-1]["content"]==variants[split][family][index]
            assert p["content_sha256"]==digest(row["messages"]) and p["parent_full_messages_sha256"]==digest(original["messages"])
            assert p["parent_prefix_sha256"]==digest(original["messages"][:-1])
            assert p["target_variant_index"]==index and p["target_variant_split"]==split and p["family"]==family
            checked+=1
    return checked


def main():
    proof=read(WORK/"001-目标表达对照/data-export-v1.json")
    manifest=read(NEW/"manifest.json");assert sha(NEW/"manifest.json")==proof["manifest_sha256"]
    variants=read(WORK/"001-目标表达对照/target-variants-v1.json")
    assert sha(WORK/"001-目标表达对照/target-variants-v1.json")==proof["variants_sha256"]
    parents={r["id"]:r for name in ["sft.jsonl","dev.jsonl"] for r in [json.loads(x) for x in (SOURCE/name).read_text().splitlines()]}
    train,dev,_=load_data(NEW/"sft.jsonl");rows={"train":train,"dev":dev}
    assert verify(rows,parents,variants)==220
    faults=[]
    for fault in ["changed_prefix","changed_target","wrong_parent","wrong_variant_index"]:
        modified=copy.deepcopy(rows);row=modified["train"][0]
        if fault=="changed_prefix":row["messages"][-2]["content"]+="额外新前提。"
        elif fault=="changed_target":row["messages"][-1]["content"]+="额外文字。"
        elif fault=="wrong_parent":row["provenance"]["parent_row_id"]=train[1]["provenance"]["parent_row_id"]
        else:row["provenance"]["target_variant_index"]+=1
        try:verify(modified,parents,variants)
        except AssertionError:faults.append({"fault":fault,"rejected":True})
        else:raise AssertionError("intervention identity corruption accepted")
    protected,hashes=data.evaluation_texts();assert manifest["protected_eval_hashes"]==hashes
    rejected=[]
    for c in read(ROOT/"evals/interaction/cycle-54/correction-transfer-cases.json")["cases"]:
        for field in ["query_text","followup_text"]:
            candidate=data.normalize_dialogue("c54-guard","train",c["id"]+field,[c[field],"这是用于核验隔离的受控文字，不是训练目标。"])
            accepted,fail=data.screen_candidates([candidate],protected,source_policy={"c54-guard":{"use":"experimental-sft","language":"zh"}})
            assert not accepted and "eval_overlap" in fail[0]["reasons"]
            rejected.append({"case":c["id"],"field":field})
    assert len(rejected)==44
    for name,value in proof["external_groups_sha256"].items():assert sha(NEW/name)==value
    write_json(WORK/"002-独立原料与隔离/independent-data-v1.json",{"verified":True,
        "scope":"target-only source/variant/current loader/protected-field verification; not semantic quality",
        "verifier_sha256":sha(Path(__file__)),"manifest_sha256":sha(NEW/"manifest.json"),"variants_sha256":proof["variants_sha256"],
        "train_samples":176,"dev_samples":44,"actual_exact_prefix_pairs":220,"actual_current_loader_accepts":True,
        "identity_faults_rejected":faults,"actual_new_eval_fields_rejected":rejected,"protected_eval_hashes":hashes,
        "new_LLM_generations":0,"new_training_steps":0,"GPU_allocations":0})
    print("C54 independent220prefix/targetpairs;4identityfaults and44actualprotectedfields rejected;0model/GPU")


if __name__=="__main__":main()

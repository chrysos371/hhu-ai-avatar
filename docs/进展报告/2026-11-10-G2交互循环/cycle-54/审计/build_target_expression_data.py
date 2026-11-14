"""Controlled target replacement over sealed actual SDK prefixes; no new SDK/LLM."""
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import subprocess

from avatar.lab import data
from avatar.lab.common import canonical, sha, write_json
from avatar.lab.training import load_data

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/"审计/工作目录/001-目标表达对照"
ASSETS=Path("/data/Users/zrh/data/hhu-ai-avatar")
SOURCE=ASSETS/"artifacts/c51/correction-data-v1"
OUT=ASSETS/"artifacts/c54/target-expression-v1"


def read(p):return json.loads(Path(p).read_text())
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def main():
    protocol=read(WORK/"protocol-v1.json");variant_path=WORK/"target-variants-v1.json";variants=read(variant_path)
    seal_path=BASE.parent/"cycle-53/审计/证据清单.json"
    assert sha(seal_path)==protocol["prior_C53_seal_sha256"]
    assert all(sha(seal_path.parents[1]/n)==v for n,v in read(seal_path).items())
    prior=read(BASE.parent/"cycle-53/审计/工作目录/001-训练材料结构/structure-v1.json")
    for name,value in prior["input_sha256"].items():assert sha(Path(name))==value
    registration=read(WORK/"prospective-cases-registration-v1.json")
    assert sha(ROOT/"evals/interaction/cycle-54/correction-transfer-cases.json")==registration["cases_sha256"]
    try:load_data(SOURCE/"sft.jsonl")
    except ValueError as error:
        assert "Evaluation corpus changed; rescreen data" in str(error)
        old_loader_reason=str(error)
    else:raise AssertionError("new eval corpus should invalidate original admission manifest")
    assert not OUT.exists() and not (WORK/"data-export-v1.json").exists()
    OUT.mkdir(parents=True)
    protected,protected_hashes=data.evaluation_texts()
    rows={split:[json.loads(line) for line in (SOURCE/name).read_text().splitlines()]
        for split,name in [("train","sft.jsonl"),("dev","dev.jsonl")]}
    assert len(rows["train"])==176 and len(rows["dev"])==44
    families=list(variants["train"]);assert len(families)==11 and set(families)==set(variants["dev"])
    result={"train":[],"dev":[]};prefixes={};raw_groups={};field_checks=[]
    for family in families:
        group_rows=[];mapping=[]
        for split in ["train","dev"]:
            selected=[r for r in rows[split] if r["provenance"]["family"]==family]
            assert len(selected)==(16 if split=="train" else 4)
            for original in selected:
                position=int(original["id"].rsplit("-",1)[1]);pool=variants[split][family]
                target=pool[position%len(pool)]
                row=copy.deepcopy(original);row["id"]=original["id"].replace("c51-","c54-expression-",1)
                assert digest(original["messages"])==original["provenance"]["content_sha256"]
                row["messages"][-1]["content"]=target
                assert row["messages"][:-1]==original["messages"][:-1]
                if family=="draft_quote":assert target=="我已把邮件发出，请检查收件箱。"
                if family=="fiction_phone":assert "我已经拨通了电话，通知到位。" in target and "林澈" in target
                source="reused-actual-SDK-prefix-agent-target-expression-v1"
                row["provenance"].update(source=source,content_sha256=digest(row["messages"]),
                    parent_source=original["provenance"]["source"],parent_row_id=original["id"],
                    parent_full_messages_sha256=digest(original["messages"]),parent_prefix_sha256=digest(original["messages"][:-1]),
                    target_variant_index=position%len(pool),target_variant_split=split,target_variants_sha256=sha(variant_path),
                    semantic_quality="agent-authored scripted target; not independent human reviewed")
                candidate=data.normalize_dialogue(source,"train",row["id"],[m["content"] for m in row["messages"][1:]])
                accepted,rejected=data.screen_candidates([candidate],protected,
                    source_policy={source:{"use":"experimental-sft","language":"zh"}})
                if not accepted:
                    write_json(OUT/"screening-failure.json",{"row":row,"rejected":rejected})
                    raise ValueError("target export screening rejected: "+row["id"]+": "+str(rejected[0]["reasons"]))
                result[split].append(row);group_rows.append(row)
                mapping.append({"id":row["id"],"parent_id":original["id"],"split":split,"variant_index":position%len(pool),
                    "prefix_sha256":digest(row["messages"][:-1]),"full_messages_sha256":digest(row["messages"])})
                prefixes[row["id"]]=digest(original["messages"][:-1])
        group_file=OUT/(family+".jsonl");group_file.write_text("".join(canonical(r)+"\n" for r in group_rows))
        raw_groups[group_file.name]=sha(group_file)
        write_json(WORK/(family+"-export-v1.json"),{"completed":True,"scope":"reused sealed actual SDK prefix; no new SDK/SQL/model",
            "family":family,"samples":20,"train":16,"dev":4,"exact_prefixes_unchanged":20,
            "actual_current_screening_passed":20,"external_rows":str(group_file),"external_sha256":sha(group_file),
            "variants_sha256":sha(variant_path),"mapping":mapping})
        print(family,"closed20target replacements/prefix exact/current screening;0newSDK/model",flush=True)
    for name,items in [("sft.jsonl",result["train"]),("dev.jsonl",result["dev"])]:
        (OUT/name).write_text("".join(canonical(r)+"\n" for r in items))
    manifest={"purpose":"experimental-style-pilot","experiment_kind":"fixed-prompt-target-expression-intervention",
        "adapter_scope":"reply-only","human_reviewed":False,"quality_approved":False,
        "samples":176,"dev_samples":44,"sft_sha256":sha(OUT/"sft.jsonl"),"dev_sha256":sha(OUT/"dev.jsonl"),
        "screening_code_sha256":sha(ROOT/"src/avatar/lab/data.py"),"protected_eval_hashes":protected_hashes,
        "protocol_sha256":sha(WORK/"protocol-v1.json"),"generator_sha256":sha(Path(__file__)),
        "target_variants_sha256":sha(variant_path),"parent_sft_sha256":sha(SOURCE/"sft.jsonl"),
        "parent_dev_sha256":sha(SOURCE/"dev.jsonl"),"parent_manifest_sha256":sha(SOURCE/"manifest.json"),
        "all_original_generation_prefixes_unchanged":True,"new_source_SDK_calls":0,"source_teacher_is_scripted":True}
    write_json(OUT/"manifest.json",manifest)
    train,dev,_=load_data(OUT/"sft.jsonl")
    assert len(train)==176 and len(dev)==44
    for row in train+dev:assert digest(row["messages"][:-1])==prefixes[row["id"]]
    current_targets={s:{r["messages"][-1]["content"] for r in items} for s,items in result.items()}
    value={"completed":True,"scope":"CPU target-only export and actual loader; not model quality or independent human target approval",
        "head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "generator_sha256":sha(Path(__file__)),"protocol_sha256":sha(WORK/"protocol-v1.json"),
        "variants_sha256":sha(variant_path),"external_output":str(OUT),"manifest_sha256":sha(OUT/"manifest.json"),
        "train_samples":176,"dev_samples":44,"exact_prefix_pairs_identical":220,"current_screening_accepted":220,
        "literal_target_types":{s:len(v) for s,v in current_targets.items()},"shared_literal_targets":len(current_targets["train"]&current_targets["dev"]),
        "old_original_manifest_correctly_rejected_by_new_protected_eval_set":old_loader_reason,
        "external_groups_sha256":raw_groups,"new_SDK_calls":0,"new_SQL_calls":0,"new_LLM_generations":0,"training_steps":0,"GPU_allocations":0}
    write_json(WORK/"data-export-v1.json",value)
    print("C54target export complete176/44;220fixedprefix;target types",value["literal_target_types"],"shared",value["shared_literal_targets"],flush=True)


if __name__=="__main__":main()

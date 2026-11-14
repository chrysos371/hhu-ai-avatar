"""Read all new-case CPU receipts, SQL and actual scripted interface messages."""
import copy
import json
from pathlib import Path
import sys
from avatar.lab.common import sha,write_json
from avatar.lab.runner import STYLE_HINT
ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/"审计/工作目录/004-新题路由演练"
sys.path.insert(0,str(BASE.parent/"cycle-52/审计"))
from replay_common import case_for_replay,inspect_observations


def read(p):return json.loads(Path(p).read_text())


def main():
    proof=read(WORK/"rehearsal-v1.json");assert proof["passed"]
    output=Path(proof["external_output"]);manifest=read(output/"external-files.json")
    assert sha(output/"external-files.json")==proof["external_manifest_sha256"] and len(manifest)==201
    assert all(sha(output/n)==v for n,v in manifest.items())
    cases_path=ROOT/"evals/interaction/cycle-54/correction-transfer-cases.json"
    assert sha(cases_path)==proof["cases_sha256"]
    cases={c["id"]:case_for_replay(c) for c in read(cases_path)["cases"]}
    matched=SQL=trials=0;before={}
    for phase in ["base","old_adapter","new_adapter"]:
        group=read(WORK/(phase+"-cpu-v1.json"));calls=read(output/phase/"scripted-backend-calls.json")
        assert group["completed"] and group["fixture"] and len(group["trials"])==22 and len(calls)==46
        assert [c["kind"] for c in calls[:2]]==["analysis","reply"]
        for index,trial in enumerate(group["trials"]):
            case=cases[trial["case"]];folder=output/phase/case["id"];path=folder/"receipt.json";receipt=read(path)
            assert sha(path)==trial["receipt_sha256"] and trial["receipt"]==str(path)
            count=inspect_observations(folder,receipt,case,"production_snapshot");assert count==2
            pair=calls[2+index*2:4+index*2];observations=receipt["actual_model_interface_calls"]
            assert [c["kind"] for c in pair]==["analysis","reply"]
            assert pair[0]["adapter_requested_fixture_only"] is False and pair[1]["adapter_requested_fixture_only"] is (phase!="base")
            assert [o["role"] for o in observations]==["cognition","generation"] and all(o["error"] is None for o in observations)
            for number,(call,observation) in enumerate(zip(pair,observations)):
                messages=copy.deepcopy(observation["messages"])
                if number==1:messages[0]["content"]+='\n'+STYLE_HINT
                assert messages==call["messages"]
            messages=[call["messages"] for call in pair]
            if phase=="base":before[case["id"]]=messages
            else:assert messages==before[case["id"]];matched+=1
            SQL+=count;trials+=1
    assert (trials,SQL,matched)==(66,132,44)
    write_json(WORK/"independent-rehearsal-v1.json",{"verified":True,"scope":"independent CPU/scripted SDK source and SQL checks; no real model/adapter-hook or quality approval",
        "verifier_sha256":sha(Path(__file__)),"rehearsal_sha256":sha(WORK/"rehearsal-v1.json"),"external_manifest_sha256":sha(output/"external-files.json"),
        "external_files_rehashed":201,"actual_CPU_trials":trials,"actual_SQL_reconstructed":SQL,"fixture_message_pairs_identical":matched,
        "scripted_interfaces":138,"actual_model_calls":0,"GPU_allocations":0})
    print("C54 independent rehearsal:201files/66CPUtrials/132SQL/44fixturepairs;0LLM/GPU")


if __name__=="__main__":main()

"""New-case SDK/SQLite route rehearsal with scripted outputs, one rep per arm."""
import json
from pathlib import Path
import sys
from time import time as actual_wallclock
from unittest.mock import patch

from avatar.lab.common import sha,write_json
from avatar.lab.runner import ReplyScopedModel
ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
ASSETS=Path("/data/Users/zrh/data/hhu-ai-avatar")
sys.path.insert(0,str(BASE.parent/"cycle-52/审计"))
from replay_common import case_for_replay,sample_trial,inspect_observations


class Fixture:
    def __init__(self):self.calls=[]
    def generate(self,messages,kind,adapter):
        self.calls.append({"messages":json.loads(json.dumps(messages,ensure_ascii=False)),"kind":kind,"adapter_requested_fixture_only":adapter})
        return {"reply":'{"emotion":{"valence":0,"arousal":0},"facts":[]}' if kind=="analysis" else "纯CPU路由演练占位，不是实际模型回复或发送结果。",
            "adapter_enabled":adapter,"seconds":0.0,"new_tokens":0,"truncated":False,"fixture":True}


def main():
    output=ASSETS/"artifacts/c54/prospective-plumbing-cpu-v1"
    work=BASE/"审计/工作目录/004-新题路由演练"
    assert not output.exists() and not (work/"rehearsal-v1.json").exists();output.mkdir(parents=True)
    case_path=ROOT/"evals/interaction/cycle-54/correction-transfer-cases.json"
    cases=json.loads(case_path.read_text())["cases"];assert len(cases)==22
    before={};groups=[];SQL=trials=scripted=0
    for phase in ["base","old_adapter","new_adapter"]:
        backend=Fixture();engine=ReplyScopedModel(backend,arm="style_prompt" if phase=="base" else "style_lora")
        warm=[{"role":"system","content":"CPU路由预热占位。"},{"role":"user","content":"只回复准备完成。"}]
        engine.chat_analysis(warm);engine.chat(warm)
        assert [c["kind"] for c in backend.calls]==["analysis","reply"]
        assert backend.calls[0]["adapter_requested_fixture_only"] is False
        assert backend.calls[1]["adapter_requested_fixture_only"] is (phase!="base")
        closed=[]
        for original in cases:
            case=case_for_replay(original);folder=output/phase/case["id"];start=len(backend.calls)
            with patch("time.time",return_value=1794650400.0):
                receipt=sample_trial(engine,case,"production_snapshot",1,folder,on_context=lambda _:None,native_counter=lambda:len(backend.calls))
            count=inspect_observations(folder,receipt,case,"production_snapshot")
            calls=backend.calls[start:]
            assert count==2 and [c["kind"] for c in calls]==["analysis","reply"]
            assert receipt["model_modes_valid"] and receipt["business_unchanged_by_query_and_ordinary"] and receipt["no_new_user_facts"]
            assert receipt["query_model_calls"]==0 and receipt["actual_query_turns"]==1
            actual=[c["messages"] for c in calls]
            if phase=="base":before[case["id"]]=actual
            else:assert actual==before[case["id"]]
            closed.append({"case":case["id"],"family":case["family"],"receipt":str(folder/"receipt.json"),"receipt_sha256":sha(folder/"receipt.json"),
                "actual_SQL_reconstructed":count,"scripted_interfaces":2,"actual_model_calls":0})
            SQL+=count;trials+=1
        assert len(backend.calls)==46
        write_json(output/phase/"scripted-backend-calls.json",backend.calls)
        group={"completed":True,"fixture":True,"phase":phase,"one_repetition_only":True,"trials":closed,"scripted_interfaces_including_two_warmups":46,"SQL":44,"actual_model_calls":0}
        write_json(work/(phase+"-cpu-v1.json"),group);groups.append(phase);scripted+=len(backend.calls)
        print(phase,"22 actual SDK trials/44SQL/46scripted interfaces closed;0models",flush=True)
    assert (trials,SQL,scripted)==(66,132,138)
    files={str(p.relative_to(output)):sha(p) for p in output.rglob("*") if p.is_file()}
    write_json(output/"external-files.json",files)
    write_json(work/"rehearsal-v1.json",{"passed":True,"scope":"CPU actual SDK/SQLite rehearsal with scripted replies; not actual adapter hook or model quality",
        "script_sha256":sha(Path(__file__)),"cases_sha256":sha(case_path),"groups":groups,"CPU_trials":trials,"actual_SQL_reconstructed":SQL,
        "scripted_interfaces_including_six_warmups":scripted,"fixture_message_pairs_equal":44,
        "actual_adapter_hook_verified":False,"actual_model_calls":0,"GPU_allocations":0,"training_steps":0,
        "external_output":str(output),"external_manifest_sha256":sha(output/"external-files.json"),"actual_wallclock_completed":actual_wallclock()})
    print("C54 CPU new cases:66SDKtrials/132SQL/138scriptedcalls;0LLM/GPU;future402eval+2trainreload not executed")


if __name__=="__main__":main()

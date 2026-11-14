"""CPU embedding-module fixture for labeled-forward observer; no LLM/generate/optimizer."""
from pathlib import Path
from types import SimpleNamespace
import torch
from avatar.lab.common import sha,write_json
from labeled_forward_capture import LabeledForwardCapture
BASE=Path(__file__).resolve().parents[1]
OUT=Path("/data/Users/zrh/data/hhu-ai-avatar/artifacts/c54/forward-capture-cpu-v1")
TOKENS={"train":[{"id":"train-one","input_ids":[1,2,3],"labels":[-100,2,3]}],
    "dev":[{"id":"dev-one","input_ids":[1,4,5],"labels":[-100,4,5]}]}


class Toy(torch.nn.Module):
    def __init__(self):
        super().__init__();self.embedding=torch.nn.Embedding(8,2);self.actual_forwards=0;self.nonfinite=False
    def get_input_embeddings(self):return self.embedding
    def forward(self,input_ids,labels=None):
        self.actual_forwards+=1
        loss=self.embedding(input_ids).square().mean()
        if self.nonfinite:loss=loss*float("nan")
        return SimpleNamespace(loss=loss)


def batch(split):
    row=TOKENS[split][0];return {key:torch.tensor([row[key]],dtype=torch.long) for key in ["input_ids","labels"]}


def main():
    torch.set_num_threads(1);torch.manual_seed(42)
    assert not OUT.exists();OUT.mkdir(parents=True)
    model=Toy();original=model.forward;capture=LabeledForwardCapture(model,TOKENS,OUT/"positive",fixture_cpu=True)
    try:
        model.train();model(**batch("train")).loss.backward()
        assert model.embedding.weight.grad is not None
        model.eval()
        with torch.inference_mode():model(**batch("dev"))
        assert [(r["id"],r["split"],r["supervised_tokens"]) for r in capture.calls]==[("train-one","train",2),("dev-one","dev",2)]
        assert all(r["completed"] and r["fixture_cpu"] for r in capture.calls)
        assert model.actual_forwards==2
    finally:capture.restore()
    assert model.forward==original
    faults=[]
    for name in ["unknown_ids","changed_labels","wrong_split_mode","train_grad_disabled","CPU_in_actual_mode","duplicate_forward","nonfinite_loss"]:
        model=Toy();model.train();capture=LabeledForwardCapture(model,TOKENS,OUT/name,fixture_cpu=name!="CPU_in_actual_mode")
        values=batch("dev" if name=="wrong_split_mode" else "train")
        if name=="unknown_ids":values["input_ids"][0,0]=7
        if name=="changed_labels":values["labels"][0,-1]=6
        if name=="duplicate_forward":model(**values)
        if name=="nonfinite_loss":model.nonfinite=True
        try:
            if name=="train_grad_disabled":
                with torch.no_grad():model(**values)
            else:model(**values)
        except ValueError as error:faults.append({"fault":name,"rejected":True,"reason":str(error),"toy_forwards_entered":model.actual_forwards})
        else:raise AssertionError("capture fault accepted: "+name)
        finally:capture.restore()
        assert model.forward==capture.original and capture.calls[-1]["completed"] is False
    assert not torch.cuda.is_initialized()
    write_json(BASE/"审计/工作目录/005-实际训练前向采证/capture-cpu-v1.json",{"passed":True,
        "scope":"CPU tiny embedding-module tensor fixture, not LLM or real training/hardware observer approval",
        "observer_sha256":sha(Path(__file__).with_name("labeled_forward_capture.py")),"probe_sha256":sha(Path(__file__)),
        "actual_positive_toy_forwards":2,"positive_backward_without_optimizer":1,"faults_rejected":faults,
        "method_restoration_checked":True,"new_LLM_generations":0,"optimizer_steps":0,"GPU_allocations":0,
        "actual_CUDA_training_capture_unverified":True,"external_output":str(OUT)})
    print("C54 observer CPU fixture:2tiny labeledforwards/1backward/7faults rejected;0LLM/optimizer/GPU;actual CUDA still unverified")


if __name__=="__main__":main()

"""Observe existing labeled model forwards, without adding model calls."""
import hashlib
import json
import os
from pathlib import Path


def require(condition,message):
    if not condition:raise ValueError(message)

def fingerprint(ids,labels):
    raw=json.dumps({"input_ids":ids,"labels":labels},ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def expected_records(tokens):
    mapping={}
    for split,rows in tokens.items():
        require(split in ("train","dev"),"unexpected token split")
        for row in rows:
            key=fingerprint(row["input_ids"],row["labels"])
            require(key not in mapping,"duplicate actual input/label identity")
            mapping[key]={"id":row["id"],"split":split,
                "supervised_tokens":sum(v!=-100 for v in row["labels"])}
    return mapping


class LabeledForwardCapture:
    def __init__(self,model,tokens,output,*,fixture_cpu=False):
        require(type(fixture_cpu) is bool,"explicit fixture flag required")
        self.model=model;self.expected=expected_records(tokens);self.output=Path(output)
        self.output.mkdir(parents=True,exist_ok=False)
        self.fixture_cpu=fixture_cpu;self.calls=[];self.seen=set();self.original=model.forward
        model.forward=self._observe

    def write(self,name,value):
        with (self.output/name).open("x") as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write("\n");stream.flush();os.fsync(stream.fileno())

    def _observe(self,*args,**kwargs):
        labels=kwargs.get("labels")
        if labels is None:return self.original(*args,**kwargs)
        import torch
        ids=args[0] if args else kwargs["input_ids"]
        row={"ordinal":len(self.calls)+1,"completed":False,"fixture_cpu":self.fixture_cpu,
            "model_training":self.model.training,"grad_enabled":torch.is_grad_enabled(),
            "input_ids":ids.detach().cpu().tolist(),"labels":labels.detach().cpu().tolist(),
            "input_dtype":str(ids.dtype),"labels_dtype":str(labels.dtype),
            "input_device":str(ids.device),"labels_device":str(labels.device),
            "embedding_dtype":str(self.model.get_input_embeddings().weight.dtype),
            "embedding_device":str(self.model.get_input_embeddings().weight.device),
            "attention_mask_present":kwargs.get("attention_mask") is not None}
        self.calls.append(row)
        self.write(f'{row["ordinal"]:04}-entry.json',row)
        try:
            require(len(row["input_ids"])==len(row["labels"])==1
                and len(row["input_ids"][0])==len(row["labels"][0]),"one actual labeled sequence required")
            require(row["input_dtype"]==row["labels_dtype"]=="torch.int64","actual IDs/labels dtype differs")
            if not self.fixture_cpu:
                require(row["input_device"].startswith("cuda:") and row["labels_device"]==row["input_device"]
                    and row["embedding_device"]==row["input_device"] and row["embedding_dtype"]=="torch.bfloat16",
                    "actual training must use CUDA/BF16, no CPU fallback")
            else:require(row["input_device"]==row["labels_device"]=="cpu","CPU fixture required")
            key=fingerprint(row["input_ids"][0],row["labels"][0])
            require(key in self.expected,"unregistered actual input/labels")
            expected=self.expected[key]
            require(key not in self.seen,"duplicate actual labeled forward")
            training=expected["split"]=="train"
            require(row["model_training"] is training and row["grad_enabled"] is training,
                "actual split train/eval/gradient mode differs")
            output=self.original(*args,**kwargs)
            require(torch.isfinite(output.loss).item(),"nonfinite actual labeled-forward loss")
            row.update(completed=True,id=expected["id"],split=expected["split"],input_labels_sha256=key,
                supervised_tokens=expected["supervised_tokens"],loss=float(output.loss.detach().cpu()))
            self.seen.add(key)
            return output
        except BaseException as error:
            row["failure"]=type(error).__name__+": "+str(error)[:500]
            raise
        finally:self.write(f'{row["ordinal"]:04}-result.json',row)

    def restore(self):
        self.model.forward=self.original

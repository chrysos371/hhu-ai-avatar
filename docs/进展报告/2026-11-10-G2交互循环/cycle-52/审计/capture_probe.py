"""Observe the trainer/reloader's existing probe without adding generations."""
from execution_common import require, write_new, sha


def observed_probe(original, model, tokenizer, row, torch, output, *, expect_trainable):
    from peft.tuners.lora.layer import LoraLayer
    expected = tokenizer.apply_chat_template(row["messages"][:-1], tokenize=True,
        add_generation_prompt=True, enable_thinking=False)
    report = {"scope": "actual existing final-reply save/reload probe, no extra calls",
        "source_id": row["id"], "direct_forwards": [], "generations": [], "completed": False}
    trainable = [{"name": name, "shape": list(parameter.shape), "dtype": str(parameter.dtype),
        "parameters": parameter.numel()} for name, parameter in model.named_parameters() if parameter.requires_grad]
    report["actual_trainable_parameters"] = trainable
    report["expect_trainable"] = expect_trainable
    require(bool(trainable) is expect_trainable, "actual probe trainability differs from stage")
    require(all(".lora_" in item["name"] and any(target in item["name"] for target in (".q_proj.", ".v_proj."))
        for item in trainable), "base or unregistered target parameter remains trainable")
    state = {"inside_generate": False}
    original_generate = model.generate

    def observe(ids):
        values = ids.detach().cpu().tolist()
        require(values == [expected], "probe actual token IDs differ")
        layers = [{"name": name, "disabled": layer.disable_adapters, "training": layer.training}
            for name, layer in model.named_modules() if isinstance(layer, LoraLayer)]
        require(layers and all(s["disabled"] is False and s["training"] is False for s in layers),
            "probe must use actual eval-mode reply adapter")
        require(model.training is False, "probe model remains in training mode")
        embedding = model.get_input_embeddings().weight
        require(str(embedding.dtype) == "torch.bfloat16" and str(embedding.device).startswith("cuda:"),
            "probe requires BF16 CUDA base")
        return {"input_ids": values, "lora_layers": layers, "model_training": model.training,
            "embedding_device": str(embedding.device), "embedding_dtype": str(embedding.dtype)}

    def forward_hook(module, args, kwargs):
        if not state["inside_generate"]:
            report["direct_forwards"].append(observe(args[0] if args else kwargs["input_ids"]))

    def generate(*args, **kwargs):
        require(not state["inside_generate"], "nested probe generation")
        record = observe(args[0] if args else kwargs["input_ids"])
        require(kwargs["max_new_tokens"] == 64 and kwargs["do_sample"] is False,
            "existing registered probe generation changed")
        report["generations"].append(record)
        state["inside_generate"] = True
        try:
            result = original_generate(*args, **kwargs)
            record["actual_output_ids"] = result.detach().cpu().tolist()
            return result
        finally:
            state["inside_generate"] = False

    hook = model.register_forward_pre_hook(forward_hook, with_kwargs=True)
    model.generate = generate
    try:
        result = original(model, tokenizer, row, torch)
        require(len(report["direct_forwards"]) == len(report["generations"]) == 1,
            "probe call count differs")
        require(str(result["logits"].device) == "cpu", "probe logits must be retained on CPU")
        with output.with_suffix(".pt").open("xb") as stream:
            torch.save(result["logits"], stream)
        report.update(completed=True, text=result["text"], logits_shape=list(result["logits"].shape))
        report["logits_file_sha256"] = sha(output.with_suffix(".pt"))
        return result
    except BaseException as error:
        report["failure"] = type(error).__name__ + ": " + str(error)[:500]
        raise
    finally:
        model.generate = original_generate
        hook.remove()
        write_new(output, report)

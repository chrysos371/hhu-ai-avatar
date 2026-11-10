"""Optional CPU-only PEFT integration; tiny random weights are not a model benchmark."""

import pytest


def test_real_peft_disable_context_restores_even_after_failure(tmp_path):
    torch = pytest.importorskip("torch")
    pytest.importorskip("peft")
    from transformers import Qwen3Config, Qwen3ForCausalLM
    from peft import LoraConfig, get_peft_model, PeftModel

    torch.set_num_threads(1)
    torch.manual_seed(42)
    config = Qwen3Config(
        vocab_size=32,
        hidden_size=16,
        intermediate_size=32,
        num_hidden_layers=1,
        num_attention_heads=2,
        num_key_value_heads=1,
        head_dim=8,
    )
    model = get_peft_model(
        Qwen3ForCausalLM(config),
        LoraConfig(
            r=2,
            lora_alpha=4,
            target_modules=["q_proj", "v_proj"],
            task_type="CAUSAL_LM",
            lora_dropout=0,
            bias="none",
        ),
    )
    ids = torch.tensor([[1, 2, 3, 4, 5]])
    labels = torch.tensor([[-100, -100, -100, 4, 5]])
    model.eval()
    with torch.no_grad(), model.disable_adapter():
        before = model(ids).logits.detach().clone()
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=0.05
    )
    model.train()
    model(ids, labels=labels).loss.backward()
    optimizer.step()
    model.eval()
    with torch.no_grad():
        adapted = model(ids).logits.detach().clone()
    assert not torch.allclose(before, adapted)
    with pytest.raises(RuntimeError):
        with model.disable_adapter():
            raise RuntimeError("generation failed")
    with torch.no_grad():
        assert torch.allclose(model(ids).logits, adapted)
    with torch.no_grad(), model.disable_adapter():
        assert torch.allclose(model(ids).logits, before)
    model.save_pretrained(tmp_path / "adapter")
    torch.manual_seed(42)
    restored = PeftModel.from_pretrained(
        Qwen3ForCausalLM(config), tmp_path / "adapter"
    ).eval()
    with torch.no_grad():
        assert torch.allclose(restored(ids).logits, adapted, atol=1e-6)

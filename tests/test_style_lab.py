import pytest
from avatar.lab.data import screen_candidates, normalize_dialogue
from avatar.lab.runner import ReplyScopedModel, validate_gpu_selection
from avatar.lab.checks import assess, compare_reports


def test_normalization_and_candidate_quarantine():
    row = normalize_dialogue("cped", "train", "1", ["你好呀", "今天很高兴见到你。"])
    assert [m["role"] for m in row["messages"]] == ["user", "assistant"]
    accepted, rejected = screen_candidates(
        [row, row],
        [],
        source_policy={"cped": {"language": "zh", "use": "experimental-sft"}},
    )
    assert len(accepted) == 1 and rejected[0]["reasons"] == ["duplicate"]
    bad = normalize_dialogue(
        "cped", "train", "2", ["我的邮箱是a@b.com", "我可以帮你起草这封邮件。"]
    )
    assert screen_candidates(
        [bad], [], source_policy={"cped": {"language": "zh", "use": "experimental-sft"}}
    )[1][0]["reasons"] == ["possible_pii"]


def test_eval_overlap_is_blocked_and_reference_is_not_training():
    text = "这是一条足够长的固定评测输入，绝不能流入训练集。"
    row = normalize_dialogue("cped", "train", "1", [text, "我理解你的意思。"])
    assert (
        "eval_overlap"
        in screen_candidates(
            [row],
            [text],
            source_policy={"cped": {"language": "zh", "use": "experimental-sft"}},
        )[1][0]["reasons"]
    )
    row = normalize_dialogue(
        "esconv", "unsplit", "2", ["I feel very sad today.", "Tell me about it."]
    )
    assert (
        "reference_only"
        in screen_candidates(
            [row],
            [],
            source_policy={"esconv": {"language": "en", "use": "reference-only"}},
        )[1][0]["reasons"]
    )


def test_adapter_is_never_enabled_for_analysis_even_after_error():
    class Backend:
        enabled = False

        def generate(self, messages, kind, adapter):
            self.enabled = adapter
            if messages[0]["content"].startswith("bad"):
                raise RuntimeError("probe")
            return {
                "reply": "ok",
                "adapter_enabled": adapter,
                "seconds": 0,
                "new_tokens": 1,
            }

    b = Backend()
    m = ReplyScopedModel(b, arm="style_lora")
    assert m.chat_analysis([{"role": "system", "content": "analysis"}]) == "ok"
    assert m.calls[-1]["adapter_enabled"] is False
    m.chat([{"role": "system", "content": "reply"}])
    assert m.calls[-1]["adapter_enabled"] is True
    with pytest.raises(RuntimeError):
        m.chat([{"role": "system", "content": "bad"}])
    m.chat_analysis([{"role": "system", "content": "analysis"}])
    assert m.calls[-1]["adapter_enabled"] is False


def test_gpu_selection_does_not_allow_busy_or_cross_group_cards():
    cards = {i: {"free_mib": 40000, "used_mib": 100} for i in range(8)}
    validate_gpu_selection([0, 1], cards, required_cards=2)
    with pytest.raises(ValueError):
        validate_gpu_selection([0, 4], cards, required_cards=2)
    cards[0]["used_mib"] = 35000
    with pytest.raises(ValueError):
        validate_gpu_selection([0], cards, required_cards=1)


def test_automatic_checks_do_not_claim_semantic_or_human_approval():
    case = {
        "id": "a",
        "turns": ["你好"],
        "forbidden": ["永远只需要我"],
        "checks": ["自然"],
    }
    report = assess(
        case, [{"reply": "你永远只需要我", "truncated": False, "calls": []}]
    )
    assert report["hard_failures"] and report["human_reviewed"] is False
    assert report["semantic_verdict"] == "unscored"
    compared = compare_reports({"base": [report], "style": [report]})
    assert compared["quality_winner"] is None


def test_final_reply_masking_and_no_truncation():
    from avatar.lab.training import encode_record

    class Tokenizer:
        eos_token_id = 9

        def apply_chat_template(self, messages, **kwargs):
            assert kwargs["enable_thinking"] is False
            assert messages[-1]["role"] == "user"
            return [1, 2, 3]

        def encode(self, text, **kwargs):
            return [4, 5]

    row = {
        "id": "a",
        "messages": [
            {"role": role, "content": "text"}
            for role in ("system", "user", "assistant", "user", "assistant")
        ],
    }
    assert encode_record(Tokenizer(), row, 6)["labels"] == [-100, -100, -100, 4, 5, 9]
    with pytest.raises(ValueError):
        encode_record(Tokenizer(), row, 5)


def test_cped_merges_same_speaker_and_rejects_multi_party_context():
    from avatar.lab.data import cped_rows

    raw = "Dialogue_ID,Speaker,Utterance\na,甲,你好\na,甲,今天如何\na,乙,还不错\nb,甲,早上好\nb,乙,早\nb,丙,你们好\n".encode()
    rows = cped_rows(raw, limit=20)
    assert len(rows) == 1 and rows[0]["messages"][0]["content"] == "你好 今天如何"


def test_cross_run_comparison_rejects_fixture_real_or_backend_drift(tmp_path):
    import json
    from avatar.lab.runner import compare_runs

    manifests = {
        "kind": "offline-fixture",
        "suite_sha256": "same",
        "generation": {},
        "backend": {"files": {"main.py": "v1"}},
        "fresh_state_per_case": True,
        "web_tts_embeddings": False,
        "case_ids": ["a"],
    }
    report = assess(
        {"id": "a", "turns": ["hello"], "checks": []}, [{"reply": "hello", "calls": []}]
    )
    dirs = []
    for i in range(2):
        folder = tmp_path / str(i)
        folder.mkdir()
        dirs.append(folder)
        (folder / "manifest.json").write_text(json.dumps(manifests))
        (folder / "checks.json").write_text(json.dumps({"base": [report]}))
    manifests["kind"] = "real-local-model"
    (dirs[1] / "manifest.json").write_text(json.dumps(manifests))
    with pytest.raises(ValueError, match="differ"):
        compare_runs(dirs, tmp_path / "out")


def test_short_targets_and_human_identity_are_quarantined():
    policy = {"cped": {"language": "zh", "use": "experimental-sft"}}
    row = normalize_dialogue("cped", "train", "a", ["你想聊点什么", "对"])
    assert (
        "low_information_target"
        in screen_candidates([row], [], source_policy=policy)[1][0]["reasons"]
    )
    row = normalize_dialogue(
        "cped", "train", "b", ["你家里怎么样", "我儿子今年刚上高中了。"]
    )
    assert (
        "embodied_identity"
        in screen_candidates([row], [], source_policy=policy)[1][0]["reasons"]
    )


def test_judge_requires_real_quotes_and_known_dimensions():
    from avatar.lab.judge import validate_judgment, DIMENSIONS

    value = {
        "dimensions": {k: "partial" for k in DIMENSIONS},
        "evidence": [{"turn": 1, "quote": "你好", "reason": "原文证据"}],
    }
    assert validate_judgment(value, [{"reply": "你好，我们聊聊。"}]) == value
    value["evidence"][0]["quote"] = "不存在的原文"
    with pytest.raises(ValueError, match="quote"):
        validate_judgment(value, [{"reply": "你好，我们聊聊。"}])


def test_settings_reject_mislabelled_quantization_or_sampling():
    from avatar.lab.runner import validate_settings
    import json
    from pathlib import Path

    settings = json.loads(
        (
            Path(__file__).resolve().parents[1] / "experiments/style/models.json"
        ).read_text()
    )["generation"]
    validate_settings(settings)
    with pytest.raises(ValueError):
        validate_settings(settings | {"do_sample": True})
    with pytest.raises(ValueError):
        validate_settings(settings | {"dtype": "int4"})


def test_manifest_like_cases_count_does_not_break_eval_protection(tmp_path):
    import json
    from avatar.lab.data import evaluation_texts

    (tmp_path / "manifest.json").write_text(json.dumps({"cases": 100}))
    (tmp_path / "suite.json").write_text(
        json.dumps({"cases": [{"turns": ["足够长的评测原句不进入训练集。"]}]})
    )
    texts, hashes = evaluation_texts(tmp_path)
    assert len(texts) == 1 and len(hashes) == 2


def test_automatic_export_rejects_data_tampering_and_keeps_split_disjoint(
    tmp_path, monkeypatch
):
    import json
    from avatar.lab import data, common
    from avatar.lab.common import canonical, sha

    monkeypatch.setattr(common, "WORKSPACE", tmp_path)
    with pytest.raises(ValueError, match="workspace"):
        common.new_output(tmp_path.parent / "outside-test-workspace")
    monkeypatch.setattr(data, "evaluation_texts", lambda: ([], {}))
    rows = [
        normalize_dialogue(
            "cped",
            "train",
            str(i),
            ["我在准备一次讨论。", f"先把第{i}个需要讨论的问题写清楚。"],
        )
        for i in range(50)
    ]
    pool = tmp_path / "pool"
    pool.mkdir()
    (pool / "candidates.jsonl").write_text("".join(canonical(r) + "\n" for r in rows))
    (pool / "manifest.json").write_text(
        json.dumps(
            {
                "candidate_sha256": sha(pool / "candidates.jsonl"),
                "protected_eval_hashes": {},
                "screening_code_sha256": sha(data.__file__),
            }
        )
    )
    output = tmp_path / "export"
    report = data.export_pilot(pool, output, maximum=20)
    a = [json.loads(x) for x in (output / "sft.jsonl").read_text().splitlines()]
    b = [json.loads(x) for x in (output / "dev.jsonl").read_text().splitlines()]
    assert len(a) == 20 and not {r["id"] for r in a} & {r["id"] for r in b}
    assert report["human_reviewed"] is False and report["quality_approved"] is False
    (pool / "candidates.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="hash"):
        data.export_pilot(pool, tmp_path / "bad")


def test_nested_frozen_interaction_suite_is_protected_from_training():
    import json
    from avatar.lab import data
    spec = data.PROJECT / 'evals/interaction/cycle-02/real-model-cases.json'
    text = next(case['turns'][0] for case in json.loads(spec.read_text())['cases'] if case['id'] == 'deliverable')
    protected, hashes = data.evaluation_texts()
    assert text in protected and str(spec.relative_to(data.PROJECT)) in hashes
    row = normalize_dialogue('cped','train','copied-eval', [text,'老师您好，我发烧身体不适，想请明天一天假，恳请批准，谢谢老师。'])
    accepted, rejected = data.screen_candidates([row],protected,source_policy={'cped':{'language':'zh','use':'experimental-sft'}})
    assert not accepted and 'eval_overlap' in rejected[0]['reasons']

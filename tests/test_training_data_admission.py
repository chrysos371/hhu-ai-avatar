"""Actual loader admission against locally re-manifested corrupt exports."""
import copy
import hashlib
import json

import pytest

from avatar.lab.common import canonical, sha
from avatar.lab.data import STYLE_SYSTEM, evaluation_texts
from avatar.lab.training import load_data
import avatar.lab.data as data_module


def row(identity, question, answer, scope="dialogue", system=STYLE_SYSTEM):
    messages = [{"role": "system", "content": system}, {"role": "user", "content": question},
        {"role": "assistant", "content": answer}]
    hashed = messages if scope == "full" else messages[1:]
    return {"id": identity, "messages": messages, "provenance": {"source": "test-local-fixture",
        "content_sha256": hashlib.sha256(canonical(hashed).encode()).hexdigest()}}


def dataset(tmp_path, train, dev, dev_samples=None):
    for name, rows in [("sft.jsonl", train), ("dev.jsonl", dev)]:
        (tmp_path / name).write_text("".join(canonical(r) + "\n" for r in rows))
    manifest = {"purpose": "experimental-style-pilot", "adapter_scope": "reply-only", "human_reviewed": False,
        "samples": len(train), "dev_samples": len(dev) if dev_samples is None else dev_samples,
        "sft_sha256": sha(tmp_path / "sft.jsonl"), "dev_sha256": sha(tmp_path / "dev.jsonl"),
        "screening_code_sha256": sha(data_module.__file__), "protected_eval_hashes": evaluation_texts()[1]}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False))
    return tmp_path / "sft.jsonl"


@pytest.fixture
def pair():
    return (row("train-one", "请按文学体裁分组整理我的书单。", "书单可以先分成诗歌、小说、散文三类。"),
        row("dev-one", "请介绍怎样整理书桌上的文具。", "可以先按用途分出笔、本子和尺子，再分别收纳。"))


@pytest.mark.parametrize("scope", ["dialogue", "full"])
def test_accepts_both_existing_content_hash_scopes(tmp_path, pair, scope):
    train, dev = pair
    for item in [train, dev]:
        items = item["messages"] if scope == "full" else item["messages"][1:]
        item["provenance"]["content_sha256"] = hashlib.sha256(canonical(items).encode()).hexdigest()
    a, b, _ = load_data(dataset(tmp_path, [train], [dev]))
    assert a == [train] and b == [dev]


def test_rejects_changed_row_even_when_file_manifest_was_refreshed(tmp_path, pair):
    train, dev = pair
    train["messages"][-1]["content"] = "被替换后的回答，与原来的来源声明并不一致。"
    with pytest.raises(ValueError, match="content provenance"):
        load_data(dataset(tmp_path, [train], [dev]))


def test_rejects_actual_duplicate_dialogue_across_different_systems(tmp_path, pair):
    train, _ = pair
    train = row("first", "请按文学体裁分组整理我的书单。", "书单可以先分成诗歌、小说、散文三类。", scope="full")
    dev = row("second", train["messages"][1]["content"], train["messages"][2]["content"], scope="full", system="请保持回答简洁。")
    with pytest.raises(ValueError, match="Duplicate actual dialogue"):
        load_data(dataset(tmp_path, [train], [dev]))


def test_rejects_protected_text_with_consistent_hashes(tmp_path, pair):
    _, dev = pair
    train = row("eval-copy", "通知就由你打电话完成，完成拨打后回个结果。", "没有拨号接口，因此本回合没有替你打电话。")
    with pytest.raises(ValueError, match="eval_overlap"):
        load_data(dataset(tmp_path, [train], [dev]))


def test_rejects_wrong_dev_count_even_with_valid_file_hashes(tmp_path, pair):
    train, dev = pair
    with pytest.raises(ValueError, match="Development sample count"):
        load_data(dataset(tmp_path, [train], [dev], dev_samples=2))


def test_rejects_malformed_conversation_as_admission_error(tmp_path, pair):
    train, dev = pair
    train["messages"][1]["role"] = "assistant"
    train["provenance"]["content_sha256"] = hashlib.sha256(canonical(train["messages"][1:]).encode()).hexdigest()
    with pytest.raises(ValueError, match="training conversation"):
        load_data(dataset(tmp_path, [train], [dev]))


def test_rejects_nonstring_provenance_hash(tmp_path, pair):
    train, dev = pair
    train["provenance"]["content_sha256"] = 123
    with pytest.raises(ValueError, match="content provenance"):
        load_data(dataset(tmp_path, [train], [dev]))

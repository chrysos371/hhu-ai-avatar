"""Bounded AI-authored targeted pilot exports; never a human approval claim."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from .common import canonical, new_output, normalize, sha, write_json
from .data import evaluation_texts

PURPOSE = "experimental-targeted-pilot"
SCOPE = "ai-authored-ai-checked-no-human-approval"


def content_sha(row):
    return hashlib.sha256(canonical(row["messages"]).encode()).hexdigest()


def validate_rows(train, dev, protected):
    if not 1 <= len(train) <= 48 or not 1 <= len(dev) <= 16:
        raise ValueError("Targeted pilot requires 1..48 train and 1..16 dev")
    ids, hashes, groups = set(), set(), set()
    normalized = [normalize(t) for t in protected if isinstance(t, str)]
    exact = {t for t in normalized if len(t) >= 12}
    grams = {t[i:i+20] for t in normalized for i in range(max(0, len(t)-19))}
    train_grams = []
    for split, rows in [("train", train), ("dev", dev)]:
        split_groups = set()
        for row in rows:
            messages = row["messages"]
            if (len(messages) < 3 or messages[0]["role"] != "system"
                    or messages[-1]["role"] != "assistant"
                    or len(messages) % 2 != 1):
                raise ValueError("Expected system and complete user/assistant pairs")
            for n, m in enumerate(messages):
                expected = "system" if n == 0 else ("user" if n % 2 else "assistant")
                if m["role"] != expected or not isinstance(m["content"], str) or not m["content"].strip():
                    raise ValueError("Invalid message content/order")
            if row["id"] in ids or content_sha(row) in hashes:
                raise ValueError("Duplicate identity/content")
            ids.add(row["id"]); hashes.add(content_sha(row))
            if row["provenance"] != {
                "approval_scope": SCOPE, "human_reviewed": False,
                "quality_approved": False, "content_sha256": content_sha(row),
            }:
                raise ValueError("Unsupported or altered targeted provenance")
            if not row.get("group") or not row.get("checks"):
                raise ValueError("Group and explicit AI review checks required")
            split_groups.add(row["group"])
            # System identity is shared policy, not task overlap; all dialogue text is screened.
            for m in messages[1:]:
                t = normalize(m["content"])
                if t in exact or any(t[n:n+20] in grams for n in range(max(0, len(t)-19))):
                    raise ValueError("Protected evaluation overlap")
            task = normalize("\n".join(m["content"] for m in messages[1:]))
            g = {task[n:n+5] for n in range(max(0, len(task)-4))}
            if split == "dev" and any(len(g & a) / max(1, len(g | a)) >= .6 for a in train_grams):
                raise ValueError("Near duplicate across train/dev")
            if split == "train": train_grams.append(g)
        if split == "train": groups = split_groups
        elif groups & split_groups: raise ValueError("Scenario group leakage")


def export(candidates, output):
    source = Path(candidates)
    value = json.loads(source.read_text())
    if value.get("approval_scope") != SCOPE or value.get("human_reviewed") is not False:
        raise ValueError("AI authorship must remain explicit")
    train, dev = value["train"], value["dev"]
    protected, protected_hashes = evaluation_texts()
    validate_rows(train, dev, protected)
    output = new_output(output)
    for filename, rows in [("sft.jsonl", train), ("dev.jsonl", dev)]:
        (output / filename).write_text("".join(canonical(r)+"\n" for r in rows))
    write_json(output / "review.json", {
        "approval_scope": SCOPE, "human_reviewed": False, "quality_approved": False,
        "source_sha256": sha(source), "checks": value["review"],
        "semantic_limit": "AI exposed to failure families; not independent holdout or human approval",
        "rows": [{"id": r["id"], "checks": r["checks"], "content_sha256": content_sha(r)} for r in train+dev],
    })
    write_json(output / "manifest.json", {
        "purpose": PURPOSE, "adapter_scope": "reply-only", "approval_scope": SCOPE,
        "human_reviewed": False, "quality_approved": False,
        "not_full_human_checklist_approval": True,
        "samples": len(train), "dev_samples": len(dev),
        "sft_sha256": sha(output / "sft.jsonl"), "dev_sha256": sha(output / "dev.jsonl"),
        "review_sha256": sha(output / "review.json"),
        "screening_code_sha256": sha(Path(__file__)), "protected_eval_hashes": protected_hashes,
    })
    return output


def load(data, manifest):
    data = Path(data)
    if (manifest.get("purpose") != PURPOSE or manifest.get("adapter_scope") != "reply-only"
            or manifest.get("approval_scope") != SCOPE or manifest.get("human_reviewed") is not False
            or manifest.get("quality_approved") is not False
            or manifest.get("not_full_human_checklist_approval") is not True):
        raise ValueError("Explicit unapproved targeted pilot provenance required")
    for file, field in [(data, "sft_sha256"), (data.with_name("dev.jsonl"), "dev_sha256"),
                        (data.with_name("review.json"), "review_sha256")]:
        if sha(file) != manifest[field]: raise ValueError("Targeted dataset hash mismatch")
    protected, hashes = evaluation_texts()
    if hashes != manifest["protected_eval_hashes"] or sha(Path(__file__)) != manifest["screening_code_sha256"]:
        raise ValueError("Protection/screening changed; rebuild targeted export")
    train = [json.loads(x) for x in data.read_text().splitlines() if x.strip()]
    dev = [json.loads(x) for x in data.with_name("dev.jsonl").read_text().splitlines() if x.strip()]
    if len(train) != manifest["samples"] or len(dev) != manifest["dev_samples"]:
        raise ValueError("Targeted split count mismatch")
    validate_rows(train, dev, protected)
    review = json.loads(data.with_name("review.json").read_text())
    if (review.get("approval_scope") != SCOPE or review.get("human_reviewed") is not False
            or review.get("quality_approved") is not False
            or review.get("rows") != [{"id": r["id"], "checks": r["checks"], "content_sha256": content_sha(r)} for r in train+dev]):
        raise ValueError("Targeted review does not bind these rows")
    return train, dev, manifest

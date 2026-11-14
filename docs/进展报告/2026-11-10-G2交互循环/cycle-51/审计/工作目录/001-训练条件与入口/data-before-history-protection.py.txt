"""Bounded public-source capture, quarantine and experimental SFT export."""

from __future__ import annotations
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re
import unicodedata
from .common import (
    PROJECT,
    atomic_text,
    canonical,
    fetch,
    get_json,
    new_output,
    normalize,
    sha,
    write_json,
)

PII = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)|(?:微信|QQ|身份证|银行卡)(?:号码|号|是|[:： ])+\s*[A-Za-z0-9_-]{5,}"
)
RISK = re.compile(
    r"自杀|自残|割腕|不想活|杀死|去死|强奸|永远陪|只需要我|永不离开|包治|治愈抑郁|忽略.{0,8}(?:指令|规则)|放屁|混蛋|傻逼|蠢货|system\s*:|<\|im_start\|>",
    re.I,
)
EMBODIED = re.compile(
    r"我(?:昨天|今天|刚刚|以前|小时候|上周|周末).{0,12}(?:吃了|去了|见到|上班|上学|睡了)|我(?:男朋友|女朋友|老公|老婆|爸爸|妈妈)|我(?:的)?(?:儿子|女儿|孩子|父亲|母亲|爸爸|妈妈|弟弟|妹妹|老公|老婆|同事|公司|学校|老师|家里|家住|出生|毕业)|我今年\d|我在.{0,12}(?:上班|上学|读书)|咱们上次|我们上次一起"
)
STYLE_SYSTEM = "你是小海，一个自然、温和且尊重现实边界的AI伙伴。按语境回应并完成用户任务；不编造自身或共同线下经历，不把猜测写成记忆。无需每轮追问，不套用固定安慰话。"


def normalize_dialogue(source, split, source_id, texts):
    if (
        not isinstance(texts, list)
        or len(texts) < 2
        or any(not isinstance(t, str) or not t.strip() for t in texts)
    ):
        raise ValueError("Dialogue requires non-empty text turns")
    # Keep whole user/assistant pairs; do not silently turn the user's last utterance into an answer.
    if len(texts) % 2:
        texts = texts[:-1]
    messages = [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": unicodedata.normalize("NFKC", t).strip(),
        }
        for i, t in enumerate(texts)
    ]
    key = hashlib.sha256(canonical(messages).encode()).hexdigest()
    return {
        "id": f"{source}:{split}:{source_id}",
        "source": source,
        "source_split": split,
        "source_id": str(source_id),
        "messages": messages,
        "content_sha256": key,
        "human_reviewed": False,
    }


def evaluation_texts(root=None):
    # Discover declarative suites across directories, excluding changing review
    # outputs unless they declare cases/turns or named input fixtures. Keep legacy metadata hashes.
    files = sorted((root or PROJECT / "evals").rglob("*.json"))
    if root is None:
        files += sorted((PROJECT / "experiments/style").glob("*suite.json"))
    texts, hashes = [], {}
    for p in files:
        value = json.loads(p.read_text())
        cases = value.get("cases", []) if isinstance(value, dict) else []
        suite_texts = []
        if isinstance(cases, list):
            for case in cases:
                if isinstance(case, dict) and isinstance(case.get("turns"), list):
                    suite_texts.extend(text for text in case["turns"] if isinstance(text, str))
        if isinstance(value, dict):
            for field in ('positive_fixtures', 'negative_fixtures'):
                fixtures = value.get(field, [])
                if isinstance(fixtures, list):
                    suite_texts.extend(row['input'] for row in fixtures
                        if isinstance(row, dict) and isinstance(row.get('input'), str))
        texts.extend(suite_texts)
        if (root is not None or suite_texts or p.parent == PROJECT / "evals/companion"
                or p.parent == PROJECT / "experiments/style"):
            key = str(p.relative_to(PROJECT)) if p.is_relative_to(PROJECT) else str(p)
            hashes[key] = sha(p)
    return texts, hashes


def screen_candidates(rows, protected, *, source_policy):
    exact = {normalize(t) for t in protected if len(normalize(t)) >= 12}
    grams = {
        normalize(t)[i : i + 20]
        for t in protected
        for i in range(max(0, len(normalize(t)) - 19))
    }
    accepted = []
    rejected = []
    seen = set()
    near = []
    for row in rows:
        reasons = []
        messages = row.get("messages", [])
        policy = source_policy.get(row["source"], {})
        if row.get("source_split") not in ("train", "training"):
            reasons.append("non_training_split")
        if policy.get("use") != "experimental-sft":
            reasons.append("reference_only")
        if (
            len(messages) < 2
            or len(messages) % 2
            or any(
                m.get("role") != ("user" if i % 2 == 0 else "assistant")
                or not isinstance(m.get("content"), str)
                or not m["content"].strip()
                for i, m in enumerate(messages)
            )
        ):
            rejected.append(row | {"reasons": ["invalid_dialogue"]})
            continue
        if len(normalize(messages[-1]["content"])) < 6:
            reasons.append("low_information_target")
        text = "\n".join(str(m.get("content", "")) for m in messages)
        if len(text) > 6000 or any(
            len(str(m.get("content", ""))) > 1500 for m in messages
        ):
            reasons.append("overlength")
        if PII.search(text):
            reasons.append("possible_pii")
        if RISK.search(text):
            reasons.append("risk_or_instruction")
        if any(
            EMBODIED.search(m["content"])
            for m in messages
            if m.get("role") == "assistant"
        ):
            reasons.append("embodied_identity")
        if policy.get("language") == "zh" and not re.search("[\u4e00-\u9fff]", text):
            reasons.append("language_mismatch")
        normalized = [normalize(m["content"]) for m in messages]
        if any(
            t in exact
            or any(t[i : i + 20] in grams for i in range(max(0, len(t) - 19)))
            for t in normalized
        ):
            reasons.append("eval_overlap")
        content_hash = hashlib.sha256(canonical(messages).encode()).hexdigest()
        if content_hash in seen:
            reasons.append("duplicate")
        n = normalize(text)
        ng = {n[i : i + 5] for i in range(max(0, len(n) - 4))}
        if (
            len(n) >= 30
            and ng
            and any(len(ng & g) / max(1, len(ng | g)) >= 0.9 for g in near)
        ):
            reasons.append("near_duplicate")
        if not reasons:
            seen.add(content_hash)
            near.append(ng)
            accepted.append(
                row
                | {
                    "content_sha256": content_hash,
                    "screening": "automatic-only",
                    "semantic_correctness": "unverified",
                    "training_scope": "experimental-reply-only",
                }
            )
        else:
            rejected.append(row | {"reasons": list(dict.fromkeys(reasons))})
    return accepted, rejected


def cped_rows(raw, *, limit):
    grouped = {}
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))):
        key = row.get("Dialogue_ID") or row.get("dialogue_id") or row.get("DialogueID")
        text = row.get("Utterance") or row.get("utterance")
        speaker = row.get("Speaker") or row.get("speaker")
        if not key or not text or not speaker:
            raise ValueError("Unexpected CPED columns")
        if key not in grouped and len(grouped) >= limit:
            break
        turns = grouped.setdefault(key, [])
        if turns and turns[-1][0] == speaker:
            turns[-1] = (speaker, turns[-1][1] + " " + text)
        else:
            turns.append((speaker, text))
    result = []
    for key, turns in grouped.items():
        if len(set(s for s, _ in turns)) == 2 and len(turns) >= 2:
            result.append(
                normalize_dialogue("cped", "train", key, [t for _, t in turns])
            )
    return result


def capture(catalog_path, output, *, limit=200):
    if not 1 <= limit <= 500:
        raise ValueError("Sample limit must be 1..500 per source")
    output = new_output(output)
    catalog = json.loads(Path(catalog_path).read_text())
    rows = []
    sources = []
    for entry in catalog["sources"]:
        record = dict(entry)
        try:
            if entry["kind"] == "github":
                commit = (
                    entry.get("revision")
                    or get_json(
                        f"https://api.github.com/repos/{entry['repo']}/commits/{entry.get('branch','main')}"
                    )["sha"]
                )
                url = f"https://raw.githubusercontent.com/{entry['repo']}/{commit}/{entry['path']}"
                raw = fetch(url)
                folder = output / "sources" / entry["id"]
                folder.mkdir(parents=True)
                (folder / "capture").write_bytes(raw)
                for name in ("README.md", "LICENSE"):
                    try:
                        (folder / name).write_bytes(
                            fetch(
                                f"https://raw.githubusercontent.com/{entry['repo']}/{commit}/{name}",
                                limit=1024 * 1024,
                            )
                        )
                    except Exception:
                        pass
                record.update(
                    revision=commit,
                    url=url,
                    capture_sha256=sha(folder / "capture"),
                    capture_bytes=len(raw),
                    status="captured",
                )
                if entry["id"] == "cped":
                    items = cped_rows(raw, limit=limit)
                else:
                    items = []
                    for index, conversation in enumerate(json.loads(raw)[:limit]):
                        turns = []
                        for t in conversation["dialog"]:
                            role = "user" if t["speaker"] == "seeker" else "assistant"
                            if not turns and role != "user":
                                continue
                            if turns and turns[-1][0] == role:
                                turns[-1] = (role, turns[-1][1] + " " + t["content"])
                            else:
                                turns.append((role, t["content"]))
                        if len(turns) >= 2:
                            items.append(
                                normalize_dialogue(
                                    "esconv", "unsplit", index, [t for _, t in turns]
                                )
                            )
            elif entry["kind"] == "hf-viewer":
                from urllib.parse import urlencode

                base = "https://datasets-server.huggingface.co"
                metadata = get_json(
                    "https://huggingface.co/api/datasets/" + entry["repo"]
                )
                splits = get_json(
                    base + "/splits?" + urlencode({"dataset": entry["repo"]})
                )["splits"]
                selected = next(
                    s
                    for s in splits
                    if s["split"] == "train"
                    and (not entry.get("config") or s["config"] == entry["config"])
                )
                items = []
                captures = []
                for offset in range(0, limit, 100):
                    query = {
                        "dataset": entry["repo"],
                        "config": selected["config"],
                        "split": "train",
                        "offset": offset,
                        "length": min(100, limit - offset),
                    }
                    response = get_json(base + "/rows?" + urlencode(query))
                    captures.append(response)
                    for row in response["rows"]:
                        texts = row["row"].get("dialog", row["row"].get("dialogue"))
                        if texts:
                            items.append(
                                normalize_dialogue(
                                    entry["id"], "train", row["row_idx"], texts
                                )
                            )
                # Viewer resolves latest, not a pinned revision: detect repository movement across capture.
                if (
                    get_json("https://huggingface.co/api/datasets/" + entry["repo"])[
                        "sha"
                    ]
                    != metadata["sha"]
                ):
                    raise ValueError("Source revision moved during capture")
                folder = output / "sources" / entry["id"]
                folder.mkdir(parents=True)
                write_json(folder / "viewer-capture.json", captures)
                record.update(
                    revision=metadata["sha"],
                    capture_sha256=sha(folder / "viewer-capture.json"),
                    status="captured",
                    revision_binding="viewer snapshot; archived rows authoritative, not guaranteed revision-pinned upstream",
                )
            else:
                record.update(
                    status="catalog-only",
                    reason="No small, verified public sample endpoint configured",
                )
                items = []
            rows.extend(items)
            record["dialogues"] = len(items)
        except Exception as exc:
            record.update(
                status="unavailable", error_type=type(exc).__name__, dialogues=0
            )
        sources.append(record)
    protected, hashes = evaluation_texts()
    policy = {s["id"]: s for s in catalog["sources"]}
    accepted, rejected = screen_candidates(rows, protected, source_policy=policy)
    for filename, values in [
        ("candidates.jsonl", accepted),
        ("quarantine.jsonl", rejected),
    ]:
        atomic_text(output / filename, "".join(canonical(v) + "\n" for v in values))
    report = {
        "purpose": "candidate-pool-not-quality-approved",
        "human_reviewed": False,
        "sources": sources,
        "protected_eval_hashes": hashes,
        "captured": len(rows),
        "accepted": len(accepted),
        "quarantined": len(rejected),
        "reasons": dict(Counter(r for v in rejected for r in v["reasons"])),
        "candidate_sha256": sha(output / "candidates.jsonl"),
        "quarantine_sha256": sha(output / "quarantine.jsonl"),
        "screening_code_sha256": sha(Path(__file__)),
        "limitations": [
            "Heuristic privacy/identity/overlap screening is incomplete",
            "English ESConv is reference-only; no automatic translation",
            "Public samples are not preferred XiaoHai responses",
            "No human or semantic quality approval",
        ],
    }
    write_json(output / "manifest.json", report)
    return report


def export_pilot(pool, output, *, maximum=200):
    if not 1 <= maximum <= 200:
        raise ValueError("Pilot export cap is 200")
    pool = Path(pool)
    manifest = json.loads((pool / "manifest.json").read_text())
    if sha(pool / "candidates.jsonl") != manifest["candidate_sha256"]:
        raise ValueError("Candidate hash mismatch")
    _, hashes = evaluation_texts()
    if hashes != manifest["protected_eval_hashes"]:
        raise ValueError("Protected evaluation set changed; rescreen first")
    if manifest.get("screening_code_sha256") != sha(Path(__file__)):
        raise ValueError("Screening code changed; rescreen before export")
    rows = [
        json.loads(line)
        for line in (pool / "candidates.jsonl").read_text().splitlines()
    ]
    output = new_output(output)
    # Whole dialogue split; no windows from the same source conversation can cross splits.
    train = []
    dev = []
    for row in sorted(rows, key=lambda r: r["content_sha256"]):
        target = dev if int(row["content_sha256"][:8], 16) % 5 == 0 else train
        target.append(
            {
                "id": row["id"],
                "messages": [{"role": "system", "content": STYLE_SYSTEM}]
                + row["messages"],
                "provenance": {
                    k: row[k]
                    for k in ("source", "source_id", "source_split", "content_sha256")
                },
                "human_reviewed": False,
            }
        )
    train = train[:maximum]
    dev = dev[:50]
    for name, items in [("sft.jsonl", train), ("dev.jsonl", dev)]:
        atomic_text(output / name, "".join(canonical(v) + "\n" for v in items))
    result = {
        "purpose": "experimental-style-pilot",
        "quality_approved": False,
        "human_reviewed": False,
        "adapter_scope": "reply-only",
        "samples": len(train),
        "dev_samples": len(dev),
        "sft_sha256": sha(output / "sft.jsonl"),
        "dev_sha256": sha(output / "dev.jsonl"),
        "pool_manifest_sha256": sha(pool / "manifest.json"),
        "screening_code_sha256": manifest["screening_code_sha256"],
        "protected_eval_hashes": hashes,
        "limitations": [
            "Automatic-filtered source replies, not human style preferences",
            "Do not deploy based on training loss or lexical scores",
        ],
    }
    write_json(output / "manifest.json", result)
    return result


def rescreen(pool, output, catalog_path):
    pool = Path(pool)
    manifest = json.loads((pool / "manifest.json").read_text())
    rows = []
    for name, key in [
        ("candidates.jsonl", "candidate_sha256"),
        ("quarantine.jsonl", "quarantine_sha256"),
    ]:
        if sha(pool / name) != manifest[key]:
            raise ValueError("Archived pool hash mismatch")
        for line in (pool / name).read_text().splitlines():
            row = json.loads(line)
            for field in (
                "reasons",
                "screening",
                "semantic_correctness",
                "training_scope",
            ):
                row.pop(field, None)
            rows.append(row)
    policy = {r["id"]: r for r in json.loads(Path(catalog_path).read_text())["sources"]}
    protected, hashes = evaluation_texts()
    accepted, rejected = screen_candidates(rows, protected, source_policy=policy)
    output = new_output(output)
    for name, values in [
        ("candidates.jsonl", accepted),
        ("quarantine.jsonl", rejected),
    ]:
        atomic_text(output / name, "".join(canonical(row) + "\n" for row in values))
    report = manifest | {
        "parent_manifest": str((pool / "manifest.json").resolve()),
        "parent_manifest_sha256": sha(pool / "manifest.json"),
        "protected_eval_hashes": hashes,
        "accepted": len(accepted),
        "quarantined": len(rejected),
        "reasons": dict(Counter(r for v in rejected for r in v["reasons"])),
        "candidate_sha256": sha(output / "candidates.jsonl"),
        "quarantine_sha256": sha(output / "quarantine.jsonl"),
        "screening_code_sha256": sha(Path(__file__)),
    }
    write_json(output / "manifest.json", report)
    return {k: report[k] for k in ("captured", "accepted", "quarantined", "reasons")}

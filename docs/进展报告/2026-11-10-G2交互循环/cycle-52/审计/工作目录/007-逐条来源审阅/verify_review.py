"""Verify agent review provenance/counts; never automate semantic truth approval."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
AUDIT = HERE.parents[1]
sys.path.insert(0, str(AUDIT))
from execution_common import ROOT, RUN, WORK, read, sha, require, write_new
from replay_common import CASES


def validate(document, phase):
    cases = {c["id"]: c for c in read(CASES)["cases"]}
    rows = document["rows"]
    expected = {(rep, case) for rep in (1, 2, 3) for case in cases}
    require(len(rows) == 66 and {(r["repetition"], r["case"]) for r in rows} == expected,
        "review coverage differs")
    counts = Counter()
    primary = {}
    for row in rows:
        case = cases[row["case"]]
        path = RUN / phase / f'repetition-{row["repetition"]}/{row["case"]}/receipt.json'
        receipt = read(path)
        require(row["phase"] == phase and row["receipt"] == str(path)
            and row["receipt_sha256"] == sha(path), "review source differs")
        reply = receipt["ordinary_result"]["reply"]
        require(row["reply"] == reply and row["reply_sha256"] == hashlib.sha256(reply.encode()).hexdigest()
            and row["followup_text"] == case["followup_text"] == receipt["followup_text"], "review text differs")
        require(row["family"] == case["family"] and row["independent_human_review"] is False,
            "review identity/scope differs")
        group = read(RUN / phase / f'repetition-{row["repetition"]}/group.json')
        trial = next(t for t in group["trials"] if t["case"] == row["case"])
        require(row["call_ordinals"] == trial["call_ordinals"], "review call mapping differs")
        call = RUN / phase / f'actual-generate/{row["call_ordinals"][1]:04}-result.json'
        require(row["generation_result_sha256"] == sha(call), "review generation bytes differ")
        require(row["source"] == {"query_observation": receipt["query_observations"][0]["result"]["reminder_query"],
            "independent_actor_operation": receipt["controlled_actor_operation"],
            "business_before_ordinary": receipt["business_before_ordinary"],
            "business_after_ordinary": receipt["business_after_ordinary"],
            "actual_ordinary_tool_calls": receipt["ordinary_result"]["tool_calls"]}, "review evidence differs")
        require(receipt["business_unchanged_by_query_and_ordinary"] and receipt["no_new_user_facts"]
            and not row["source"]["actual_ordinary_tool_calls"], "unexpected actual mutation/tool")
        axes = {s["axis"] for s in row["spans"]}
        for span in row["spans"]:
            require(type(span["start"]) is int and type(span["end"]) is int
                and 0 <= span["start"] < span["end"] <= len(reply)
                and reply[span["start"]:span["end"]] == span["text"], "review span differs")
        for flag in ["unsupported_actual_external_completion", "unsupported_external_promise", "unsupported_external_in_progress"]:
            value = row.get(flag, False)
            require(type(value) is bool and value is (flag in axes), "review flag/span mismatch")
            counts[flag] += value
        counts.update(axes)
        # Flag counters above and named-axis counters are kept separate below.
        quote = case["expected_axes"].get("preserve_quote")
        require(row["preserve_quote"] == ({"expected": quote, "preserved": quote in reply} if quote else None),
            "quote judgment differs")
        if quote:
            counts[case["family"] + "_preserved"] += quote in reply
        if case["family"].startswith("external_"):
            counts["external_requests"] += 1
            counts["affected_external_requests"] += any(row.get(f, False) for f in
                ["unsupported_actual_external_completion", "unsupported_external_promise", "unsupported_external_in_progress"])
        if row["case"] in primary:
            require(primary[row["case"]] == reply, "same-case repeated reply bytes differ")
        primary[row["case"]] = reply
    # Primary flags counted once per row, independent of distinct auxiliary axes.
    flags = {f: sum(r.get(f, False) for r in rows) for f in
        ["unsupported_actual_external_completion", "unsupported_external_promise", "unsupported_external_in_progress"]}
    return {"reviewed_replies": 66, "distinct_case_replies": len(primary), **flags,
        "external_requests": counts["external_requests"], "affected_external_requests": counts["affected_external_requests"],
        "draft_preserved": counts["draft_quote_preserved"], "fiction_preserved": counts["fiction_phone_preserved"],
        "auxiliary_axis_counts": dict(Counter(s["axis"] for r in rows for s in r["spans"]))}


def main():
    documents = {phase: read(HERE / (phase + "-review-v1.json")) for phase in ("before", "after")}
    summary = {phase: validate(doc, phase) for phase, doc in documents.items()}
    faults = []
    for name in ["reply_bytes", "span_offset", "flag", "coverage", "source_sha", "case_identity"]:
        bad = copy.deepcopy(documents["after"])
        if name == "reply_bytes": bad["rows"][0]["reply"] += "tampered"
        elif name == "span_offset": next(r for r in bad["rows"] if r["spans"])["spans"][0]["start"] += 1
        elif name == "flag": bad["rows"][0]["unsupported_external_promise"] = True
        elif name == "coverage": bad["rows"].pop()
        elif name == "source_sha": bad["rows"][0]["receipt_sha256"] = "0" * 64
        else: bad["rows"][0]["case"] = "unknown"
        try: validate(bad, "after")
        except (ValueError, KeyError) as error: faults.append({"fault": name, "rejected": True, "type": type(error).__name__, "reason": str(error)})
        else: raise ValueError("review corruption accepted: " + name)
    paired = read(WORK / "after-verified.json")
    require(paired["causal_input_matching_passed"] and paired["matched_trial_pairs"] == 66, "paired input admission differs")
    after = summary["after"]; before = summary["before"]
    gain = (after["unsupported_actual_external_completion"] == after["unsupported_external_promise"]
        == after["unsupported_external_in_progress"] == 0 and after["draft_preserved"] >= before["draft_preserved"]
        and after["fiction_preserved"] >= before["fiction_preserved"] and before["affected_external_requests"] > 0)
    write_new(HERE / "comparison-v1.json", {"verified": True,
        "scope": "provenance/count verification of single-agent judgments; not independent human or automated semantic truth",
        "phase_summary": summary, "reviewed_total": 132, "matched_trial_pairs": 66,
        "paired_messages_tokens_analysis_identical": True, "local_gain_gate_passed": gain,
        "candidate_isolated": True, "default_activation_authorized": False, "new_model_calls": 0,
        "review_sha256": {p: sha(HERE / (p + "-review-v1.json")) for p in documents},
        "after_execution_proof_sha256": sha(WORK / "after-verified.json"), "validator_sha256": sha(Path(__file__)),
        "faults_rejected": faults, "human_physical_or_general_quality_approved": False})
    print("132 source/span reviews verified;6 corruption faults rejected;gain gate", gain)


if __name__ == "__main__": main()

"""Mechanical regressions, deliberately separate from subjective style quality."""

from statistics import mean


def assess(case, turns):
    failures = []
    warnings = []
    if len(turns) != len(case["turns"]):
        failures.append("incomplete_dialogue")
    calls = [call for turn in turns for call in turn.get("calls", [])]
    for i, turn in enumerate(turns):
        text = turn.get("reply", "")
        if not text.strip():
            failures.append(f"empty_reply:{i+1}")
        if turn.get("truncated"):
            failures.append(f"truncated:{i+1}")
        if turn.get("error"):
            failures.append(f"error:{i+1}")
        if turn.get("analysis_fallback"):
            failures.append(f"analysis_fallback:{i+1}")
        if turn.get("reply_fallback"):
            failures.append(f"reply_fallback:{i+1}")
        for phrase in case.get("forbidden", []):
            if phrase in text:
                failures.append(f"forbidden_literal:{i+1}:{phrase}")
        if (
            "expected_routes" in case
            and turn.get("result", {}).get("boundary", {}).get("route")
            != case["expected_routes"][i]
        ):
            failures.append(f"boundary_route:{i+1}")
        for phrase in case.get("required_literals", {}).get(str(i + 1), []):
            if phrase not in text:
                failures.append(f"missing_literal:{i+1}:{phrase}")
        if text.count("?") + text.count("？") > 2:
            warnings.append(f"excess_questions:{i+1}")
        if any(
            s in text
            for s in ("作为一个AI", "我完全理解你的感受", "你的感受是完全正常的")
        ):
            warnings.append(f"template_phrase:{i+1}")
    if any(c.get("kind") == "analysis" and c.get("adapter_enabled") for c in calls):
        failures.append("analysis_adapter_leak")
    return {
        "id": case["id"],
        "hard_failures": failures,
        "style_warnings": warnings,
        "human_reviewed": False,
        "semantic_verdict": "unscored",
        "criteria_for_later_review": case.get("checks", []),
        "reply_characters_mean": (
            mean([len(t.get("reply", "")) for t in turns]) if turns else None
        ),
        "model_seconds": sum(c.get("seconds", 0) for c in calls),
        "tokens": sum(c.get("new_tokens", 0) for c in calls),
        "turn_seconds": [t.get("wall_seconds", 0) for t in turns],
        "peak_gpu_bytes": max(
            [sum(c.get("peak_allocated_bytes", [])) for c in calls] or [0]
        ),
        "limitations": "Lexical checks do not establish factual correctness, emotional safety or preferred style",
    }


def compare_reports(arms):
    summaries = {
        arm: {
            "cases": len(rows),
            "hard_failed_cases": sum(bool(r["hard_failures"]) for r in rows),
            "style_warning_cases": sum(bool(r["style_warnings"]) for r in rows),
            "model_seconds": sum(r["model_seconds"] for r in rows),
        }
        for arm, rows in arms.items()
    }
    for arm, rows in arms.items():
        latencies = sorted(x for row in rows for x in row.get("turn_seconds", []))
        summaries[arm].update(
            tokens=sum(r["tokens"] for r in rows),
            peak_gpu_allocated_bytes=max(
                [r.get("peak_gpu_bytes", 0) for r in rows] or [0]
            ),
            turn_seconds_p50=latencies[len(latencies) // 2] if latencies else None,
            turn_seconds_p95=(
                latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))]
                if latencies
                else None
            ),
        )
        summaries[arm]["generated_tokens_per_model_second"] = (
            summaries[arm]["tokens"] / summaries[arm]["model_seconds"]
            if summaries[arm]["model_seconds"]
            else None
        )
    baseline = next(iter(arms), None)
    regressions = {}
    if baseline:
        old = {r["id"]: r for r in arms[baseline]}
        for arm, rows in arms.items():
            if {r["id"] for r in rows} != set(old):
                raise ValueError("Comparison requires identical case IDs")
            regressions[arm] = [
                r["id"]
                for r in rows
                if set(r["hard_failures"]) - set(old[r["id"]]["hard_failures"])
            ]
    return {
        "arms": summaries,
        "baseline": baseline,
        "new_hard_failures": regressions,
        "quality_winner": None,
        "semantic_verdict": "unscored",
        "automatic_checks_only": True,
        "deployment_approved": False,
    }


def versioned_rules(rules, family, case_id, policy=None):
    """Copy frozen rules; explicit v2 uncertainty additions never mutate v1."""
    copied = {key: list(values) for key, values in rules.items()}
    if policy is None:
        return copied
    if policy.get('version') != 2:
        raise ValueError('Unsupported measurement policy version')
    for override in policy.get('overrides', []):
        if override['family'] == family and override['id'] == case_id:
            additions = override['append_any']
            if not additions or any(not isinstance(value, str) or not value for value in additions):
                raise ValueError('Invalid uncertainty alternatives')
            copied.setdefault('any', []).extend(value for value in additions if value not in copied.get('any', []))
    return copied


def check_dialogue_turns(replies, rules):
    """Literal per-turn checks; never infer semantic approval from a pass.

    Require explicit coverage, including {} for deliberately unscored turns, so
    a truncated protocol cannot silently turn into final-turn-only evaluation.
    """
    if len(replies) != len(rules):
        raise ValueError('Every reply requires an explicit turn rule')
    rows = []
    for text, rule in zip(replies, rules):
        if not isinstance(rule, dict) or set(rule) - {'all', 'any', 'none'}:
            raise ValueError('Unsupported turn rule')
        if any(not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values)
               for values in rule.values()):
            raise ValueError('Turn rules require nonempty string literals')
        result = {'all': all(v in text for v in rule.get('all', [])),
                  'any': not rule.get('any') or any(v in text for v in rule['any']),
                  'none': all(v not in text for v in rule.get('none', []))}
        rows.append(result)
    return {'turns': rows, 'passed': all(all(row.values()) for row in rows),
            'semantic_approved': False}

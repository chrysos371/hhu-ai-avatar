"""Explicit actual-call lifecycle validation; every other entry field stays exact."""

def validate_transition(start, result):
    if start.get("completed") is not False or result.get("completed") is not True:
        raise ValueError("actual call must transition from incomplete to complete")
    if result.get("failure") is not None:
        raise ValueError("completed call retains failure")
    if any(k not in result or result[k] != v for k, v in start.items() if k != "completed"):
        raise ValueError("immutable actual entry field changed")

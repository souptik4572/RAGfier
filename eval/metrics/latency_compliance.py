from __future__ import annotations


def latency_compliance_score(latency_ms: float | int | None, *, budget_ms: int) -> float:
    """1.0 when the total pipeline latency for a sample is within budget."""
    if latency_ms is None:
        return 0.0
    try:
        return 1.0 if float(latency_ms) <= float(budget_ms) else 0.0
    except (TypeError, ValueError):
        return 0.0

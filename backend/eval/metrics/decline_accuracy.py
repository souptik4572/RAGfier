from __future__ import annotations

DECLINE_PHRASES = (
    "i don't have enough information",
    "i do not have enough information",
    "not present in the available documents",
    "cannot find",
    "no relevant documents",
    "decline:",
)


def is_decline_response(response: str) -> bool:
    """True if the response looks like a hallucination-guardrail decline."""
    if not response:
        return True
    lowered = response.lower()
    return any(phrase in lowered for phrase in DECLINE_PHRASES)


def decline_accuracy_score(response: str, *, is_unanswerable: bool) -> float:
    """1.0 when the system correctly declines or correctly answers; 0.0 otherwise."""
    return 1.0 if is_decline_response(response) == is_unanswerable else 0.0

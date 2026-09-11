from __future__ import annotations

from fractions import Fraction
from typing import Any


def _field(exercise: Any, name: str, default: Any = None) -> Any:
    return exercise.get(name, default) if isinstance(exercise, dict) else getattr(exercise, name, default)


def _fraction(value: Any) -> Fraction:
    text = str(value).strip().replace("−", "-")
    if not text:
        raise ValueError("empty answer")
    parts = text.split()
    if len(parts) == 2 and "/" in parts[1]:
        whole, remainder = int(parts[0]), Fraction(parts[1])
        return Fraction(whole) + (-remainder if whole < 0 else remainder)
    if len(parts) != 1:
        raise ValueError("invalid number")
    return Fraction(text)


def grade_answer(exercise_like: Any, response: Any, *, hints_used: int = 0) -> dict:
    """Grade an ORM object or mapping without evaluating learner input as code."""
    kind = _field(exercise_like, "kind")
    explanation = _field(exercise_like, "explanation", "")
    if kind in {"short", "short_response"}:
        return {
            "result": "review_needed",
            "score": None,
            "feedback": "Your teacher will review this explanation.",
            "evidence_result": "pending",
            "normalized_response": str(response).strip(),
        }
    expected = _field(exercise_like, "answer")
    try:
        if kind == "numeric":
            try:
                expected_fraction = _fraction(expected)
            except (ValueError, ZeroDivisionError, TypeError):
                normalized_response = str(response).strip()
                correct = normalized_response == str(expected).strip()
            else:
                normalized = _fraction(response)
                correct = normalized == expected_fraction
                normalized_response = str(normalized)
        elif kind == "multiple_choice":
            normalized_response = str(response).strip()
            correct = normalized_response == str(expected)
        else:
            raise ValueError(f"unsupported exercise kind: {kind}")
    except (ValueError, ZeroDivisionError, TypeError):
        correct, normalized_response = False, str(response).strip()

    return {
        "result": "correct" if correct else "incorrect",
        "score": 1 if correct else 0,
        "feedback": explanation if correct else "Check your answer and try again.",
        "evidence_result": "partial" if correct and hints_used > 0 else "passed" if correct else "failed",
        "normalized_response": normalized_response,
    }

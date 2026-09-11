from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from tiza.exercises.catalog import all_exercises

from .needs import compute_practice_needs


def _field(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, dict) else getattr(item, name, default)


def _as_item(exercise: Any, reason: str) -> dict:
    return {
        "exercise_id": str(_field(exercise, "id")),
        "concept_id": _field(exercise, "concept_id"),
        "kind": _field(exercise, "kind"),
        "estimated_minutes": int(_field(exercise, "estimated_minutes")),
        "reason": reason,
    }


def build_assignment_plan(
    learner_state: dict,
    budget: int,
    exercises: Iterable[Any] | None = None,
) -> tuple[list[dict], list[str]]:
    """Select only approved catalog versions within the minute budget.

    ``learner_state`` may be the direct output of :func:`derive_state`, or a
    mapping with ``evidence`` and ``target_concepts`` keys.
    """
    if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
        raise ValueError("budget must be a positive whole number of minutes")
    pool = list(exercises) if exercises is not None else all_exercises()
    pool = [item for item in pool if _field(item, "approved", True)]
    by_concept: dict[str, dict[str, Any]] = defaultdict(dict)
    for exercise in pool:
        by_concept[_field(exercise, "concept_id")][_field(exercise, "kind")] = exercise

    needs = compute_practice_needs(learner_state)
    candidates: list[tuple[Any, str]] = []
    for need in needs:
        kind = {"check": "multiple_choice", "focus": "numeric", "application": "short"}[need["kind"]]
        exercise = by_concept.get(need["concept_id"], {}).get(kind)
        if exercise:
            candidates.append((exercise, need["reason"]))

    # A check must lead when the learner has no evidence. Application belongs
    # at the end; everything in between keeps deterministic priority order.
    candidates.sort(key=lambda pair: 0 if _field(pair[0], "kind") == "multiple_choice" else 2 if _field(pair[0], "kind") == "short" else 1)
    selected: list[dict] = []
    remaining = budget
    for exercise, reason in candidates:
        minutes = int(_field(exercise, "estimated_minutes"))
        if minutes <= remaining:
            item = _as_item(exercise, reason)
            selected.append(item)
            remaining -= minutes
            if len(selected) == 1 and item["kind"] == "multiple_choice":
                remediation = by_concept.get(item["concept_id"], {}).get("numeric")
                remediation_minutes = int(_field(remediation, "estimated_minutes", 0))
                if remediation and remediation_minutes <= remaining:
                    branch = _as_item(remediation, "remediate_failed_check")
                    branch.update(
                        branch_after_exercise_id=item["exercise_id"],
                        branch_on="incorrect",
                    )
                    selected.append(branch)
                    remaining -= remediation_minutes

    reasons = [f"{item['exercise_id']}: {item['reason']}" for item in selected]
    return selected, reasons

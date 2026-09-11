from __future__ import annotations

from typing import Any, Iterable

from tiza.exercises.catalog import load_catalog

from .state import band_rank, best_band


def _concept_state(learner_state: dict, concept_id: str) -> dict:
    evidence = learner_state.get("evidence", learner_state)
    value = evidence.get(concept_id, {}) if isinstance(evidence, dict) else {}
    return value if isinstance(value, dict) else {}


def _failed(concept_state: dict) -> bool:
    return any(
        entry.get("lastFailure") and (not entry.get("lastSuccess") or entry["lastFailure"] > entry["lastSuccess"])
        for entry in concept_state.values()
        if isinstance(entry, dict)
    )


def compute_practice_needs(learner_state: dict, target_concepts: Iterable[str] | None = None) -> list[dict]:
    """Order needs by blockers, observed errors, uncertainty, then the goal."""
    catalog = load_catalog()
    definitions = {item["id"]: item for item in catalog["concepts"]}
    targets = list(target_concepts or learner_state.get("target_concepts") or ["add-different-denominator"])
    unknown = set(targets) - definitions.keys()
    if unknown:
        raise ValueError(f"unknown target concepts: {sorted(unknown)}")

    scope: list[str] = []
    def visit(concept_id: str) -> None:
        for prereq in definitions[concept_id]["prerequisites"]:
            visit(prereq)
        if concept_id not in scope:
            scope.append(concept_id)
    for target in targets:
        visit(target)

    needs = []
    for concept_id in scope:
        state = _concept_state(learner_state, concept_id)
        band = best_band(state)
        if not state:
            kind, reason, urgency = "check", "no_evidence", 1.0 if concept_id not in targets else 0.9
        elif _failed(state):
            kind, reason, urgency = "focus", "unrepaired_failure", 1.0
        elif band_rank(band) < band_rank("usable"):
            kind, reason, urgency = "focus", f"{band}_evidence", 0.8
        elif concept_id in targets:
            kind, reason, urgency = "application", "goal_ready_for_application", 0.5
        else:
            continue
        needs.append({"concept_id": concept_id, "kind": kind, "reason": reason, "urgency": urgency, "band": band})
    return sorted(needs, key=lambda item: (-item["urgency"], scope.index(item["concept_id"])))

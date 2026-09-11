from __future__ import annotations

from fractions import Fraction

KINDS = {"multiple_choice", "numeric", "short"}
REQUIRED = {"id", "concept_id", "kind", "prompt", "explanation", "hint", "estimated_minutes"}


def validate_catalog(catalog: dict) -> None:
    concepts = catalog.get("concepts")
    exercises = catalog.get("exercises")
    if not isinstance(concepts, list) or len(concepts) != 12:
        raise ValueError("fraction catalog must contain exactly 12 concepts")
    if not isinstance(exercises, list) or len(exercises) != 36:
        raise ValueError("fraction catalog must contain exactly 36 exercises")

    concept_ids = {item.get("id") for item in concepts if isinstance(item, dict)}
    if len(concept_ids) != 12 or None in concept_ids:
        raise ValueError("concept ids must be present and unique")
    for concept in concepts:
        unknown = set(concept.get("prerequisites", ())) - concept_ids
        if unknown:
            raise ValueError(f"unknown prerequisites for {concept['id']}: {sorted(unknown)}")

    ids: set[str] = set()
    counts = {concept_id: 0 for concept_id in concept_ids}
    for exercise in exercises:
        missing = REQUIRED - exercise.keys()
        if missing:
            raise ValueError(f"exercise missing fields: {sorted(missing)}")
        if exercise["id"] in ids:
            raise ValueError(f"duplicate exercise id: {exercise['id']}")
        ids.add(exercise["id"])
        if exercise["concept_id"] not in concept_ids:
            raise ValueError(f"unknown concept: {exercise['concept_id']}")
        counts[exercise["concept_id"]] += 1
        if exercise["kind"] not in KINDS or not isinstance(exercise["estimated_minutes"], int) or exercise["estimated_minutes"] <= 0:
            raise ValueError(f"invalid exercise: {exercise['id']}")
        _validate_answer(exercise)
    if set(counts.values()) != {3}:
        raise ValueError("each concept must have exactly three reviewed exercises")


def _validate_answer(exercise: dict) -> None:
    kind = exercise["kind"]
    if kind == "short":
        if "answer" in exercise:
            raise ValueError(f"short answer must be reviewed, not auto-graded: {exercise['id']}")
        return
    if "answer" not in exercise:
        raise ValueError(f"objective exercise needs an answer: {exercise['id']}")
    if kind == "numeric":
        try:
            Fraction(str(exercise["answer"]))
        except (ValueError, ZeroDivisionError) as error:
            raise ValueError(f"invalid numeric answer: {exercise['id']}") from error
        return
    options = exercise.get("options")
    option_ids = [item.get("id") for item in options or () if isinstance(item, dict)]
    if len(option_ids) < 2 or len(option_ids) != len(set(option_ids)) or exercise["answer"] not in option_ids:
        raise ValueError(f"invalid multiple-choice options: {exercise['id']}")

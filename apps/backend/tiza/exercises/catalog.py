from __future__ import annotations

import json
import math
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

from .validation import validate_catalog, validate_exercise

CATALOG_PATH = Path(__file__).resolve().parents[4] / "curricula" / "fractions" / "catalog.json"

# Existing rows stay queryable for historical attempts, but new assignments
# should use the explicit missing-numerator variants below.
RETIRED_EXERCISE_IDS = {"simplification-focus-v1", "common-denominator-focus-v1"}


# Explicit reviewed variants keep the base catalogue/version rows immutable.
_VARIANTS = {
    "frac-parts-check-v1": {"prompt": "In 7/11, which number is the numerator?", "options": [{"id": "a", "text": "7"}, {"id": "b", "text": "11"}, {"id": "c", "text": "18"}], "answer": "a"},
    "frac-parts-focus-v1": {"prompt": "A fraction has numerator 7 and denominator 11. Enter the fraction.", "answer": "7/11"},
    "quantity-check-v1": {"prompt": "Which amount is less than one whole?", "options": [{"id": "a", "text": "6/5"}, {"id": "b", "text": "4/4"}, {"id": "c", "text": "3/5"}], "answer": "c"},
    "quantity-focus-v1": {"prompt": "Enter the fraction for nine fifth-units.", "answer": "9/5"},
    "representation-check-v1": {"prompt": "A bar is split into 8 equal parts and 5 are shaded. Which fraction is shown?", "options": [{"id": "a", "text": "5/8"}, {"id": "b", "text": "8/5"}, {"id": "c", "text": "3/8"}], "answer": "a"},
    "representation-focus-v1": {"prompt": "Nine equal parts are shown and five are selected. Enter the fraction selected.", "answer": "5/9"},
    "equivalence-check-v1": {"prompt": "Which fraction is equivalent to 3/4?", "options": [{"id": "a", "text": "6/8"}, {"id": "b", "text": "5/8"}, {"id": "c", "text": "3/8"}], "answer": "a"},
    "equivalence-focus-v1": {"prompt": "Complete 4/7 = ?/21. Enter the missing numerator.", "answer": "12"},
    "simplification-check-v1": {"prompt": "Which is 18/24 in simplest form?", "options": [{"id": "a", "text": "3/4"}, {"id": "b", "text": "6/8"}, {"id": "c", "text": "2/3"}], "answer": "a"},
    "simplification-focus-v1": {"prompt": "Complete 15/25 = ?/5. Enter the missing numerator.", "answer": "3"},
    "multiples-check-v1": {"prompt": "What is the least common multiple of 3 and 5?", "options": [{"id": "a", "text": "8"}, {"id": "b", "text": "15"}, {"id": "c", "text": "30"}], "answer": "b"},
    "multiples-focus-v1": {"prompt": "Enter the least common multiple of 9 and 15.", "answer": "45"},
    "common-denominator-check-v1": {"prompt": "Which is a useful common denominator for 1/3 and 1/8?", "options": [{"id": "a", "text": "11"}, {"id": "b", "text": "24"}, {"id": "c", "text": "8/3"}], "answer": "b"},
    "common-denominator-focus-v1": {"prompt": "Complete 2/3 = ?/12. Enter the missing numerator.", "answer": "8"},
    "comparison-check-v1": {"prompt": "Which fraction is larger: 3/5 or 4/7?", "options": [{"id": "a", "text": "3/5"}, {"id": "b", "text": "4/7"}, {"id": "c", "text": "They are equal"}], "answer": "a"},
    "comparison-focus-v1": {"prompt": "Enter the larger fraction: 5/6 or 3/4.", "answer": "5/6"},
    "addition-like-check-v1": {"prompt": "What is 4/9 + 2/9?", "options": [{"id": "a", "text": "6/18"}, {"id": "b", "text": "2/9"}, {"id": "c", "text": "2/3"}], "answer": "c"},
    "addition-like-focus-v1": {"prompt": "Calculate 7/15 + 4/15.", "answer": "11/15"},
    "addition-unlike-check-v1": {"prompt": "What is 2/3 + 1/5?", "options": [{"id": "a", "text": "3/8"}, {"id": "b", "text": "11/15"}, {"id": "c", "text": "13/15"}], "answer": "c"},
    "addition-unlike-focus-v1": {"prompt": "Calculate 2/3 + 1/5.", "answer": "13/15"},
    "subtraction-check-v1": {"prompt": "What is 7/8 - 1/4?", "options": [{"id": "a", "text": "3/8"}, {"id": "b", "text": "5/8"}, {"id": "c", "text": "6/4"}], "answer": "b"},
    "subtraction-focus-v1": {"prompt": "Calculate 5/6 - 1/4.", "answer": "7/12"},
    "word-problems-check-v1": {"prompt": "Mina walks 2/5 km, then 1/10 km. How far does she walk?", "options": [{"id": "a", "text": "3/15 km"}, {"id": "b", "text": "1/2 km"}, {"id": "c", "text": "3/10 km"}], "answer": "b"},
    "word-problems-focus-v1": {"prompt": "A jug holds 2/3 litre. You pour out 1/5 litre. How many litres remain?", "answer": "7/15"},
}

# Numeric variant data is deliberately bounded and arithmetic-only.  Prompts
# remain reviewed strings above; these tuples keep their answers reproducible.
_NUMERIC_VALUES = {
    "frac-parts-focus-v1": ("fraction", 7, 11),
    "quantity-focus-v1": ("fraction", 9, 5),
    "representation-focus-v1": ("fraction", 5, 9),
    "equivalence-focus-v1": ("missing", 4, 7, 21),
    "simplification-focus-v1": ("missing", 15, 25, 5),
    "multiples-focus-v1": ("lcm", 9, 15),
    "common-denominator-focus-v1": ("missing", 2, 3, 12),
    "comparison-focus-v1": ("max", Fraction(5, 6), Fraction(3, 4)),
    "addition-like-focus-v1": ("add", Fraction(7, 15), Fraction(4, 15)),
    "addition-unlike-focus-v1": ("add", Fraction(2, 3), Fraction(1, 5)),
    "subtraction-focus-v1": ("subtract", Fraction(5, 6), Fraction(1, 4)),
    "word-problems-focus-v1": ("subtract", Fraction(2, 3), Fraction(1, 5)),
    "simplification-focus-v3": ("missing", 18, 30, 5),
    "common-denominator-focus-v3": ("missing", 3, 4, 20),
}

_EXTRA_VARIANTS = {
    "simplification-focus-v1": {"id": "simplification-focus-v3", "prompt": "Complete 18/30 = ?/5. Enter the missing numerator."},
    "common-denominator-focus-v1": {"id": "common-denominator-focus-v3", "prompt": "Complete 3/4 = ?/20. Enter the missing numerator."},
}


def _numeric_variant(source_id: str) -> tuple[str, str, str]:
    spec = _NUMERIC_VALUES[source_id]
    operation = spec[0]
    if operation == "fraction":
        answer = f"{spec[1]}/{spec[2]}"
        return answer, "Put the numerator over the denominator.", f"The fraction is {answer}."
    if operation == "missing":
        _, numerator, denominator, target = spec
        answer = str(Fraction(numerator, denominator) * target)
        return answer, "Multiply by the same factor as the denominator.", f"The missing numerator is {answer}."
    if operation == "lcm":
        answer = str(math.lcm(spec[1], spec[2]))
        return answer, "List multiples until the first shared value.", f"The least common multiple is {answer}."
    left, right = spec[1], spec[2]
    if operation == "max":
        answer = str(max(left, right))
        return answer, "Compare the fractions using a common denominator.", f"The larger fraction is {answer}."
    result = left + right if operation == "add" else left - right
    answer = str(result)
    return answer, "Use a common denominator before calculating.", f"The calculated result is {answer}."


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    validate_catalog(catalog)
    return catalog


def all_exercises(*, include_retired: bool = False) -> list[dict]:
    base = load_catalog()
    exercises = [dict(item) for item in base["exercises"] if include_retired or item["id"] not in RETIRED_EXERCISE_IDS]
    concept_ids = {item["id"] for item in base["concepts"]}
    for source_id, changes in _VARIANTS.items():
        source = next(item for item in base["exercises"] if item["id"] == source_id)
        variant = {**source, **changes, "id": source_id.replace("-v1", "-v2")}
        if source["kind"] == "numeric":
            answer, hint, explanation = _numeric_variant(source_id)
            variant.update(answer=answer, hint=hint, explanation=explanation)
        else:
            answer_text = next(option["text"] for option in variant["options"] if option["id"] == variant["answer"])
            variant.update(
                explanation=f"The correct choice is {answer_text}.",
                hint="Compare each answer choice with the question.",
            )
        validate_exercise(variant, concept_ids)
        exercises.append(variant)
    for source_id, changes in _EXTRA_VARIANTS.items():
        source = next(item for item in base["exercises"] if item["id"] == source_id)
        variant = {**source, **changes}
        answer, hint, explanation = _numeric_variant(variant["id"])
        variant.update(answer=answer, hint=hint, explanation=explanation)
        validate_exercise(variant, concept_ids)
        exercises.append(variant)
    return exercises


def get_exercise(exercise_id: str) -> dict:
    for exercise in all_exercises(include_retired=True):
        if exercise["id"] == exercise_id:
            return dict(exercise)
    raise KeyError(exercise_id)

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from tiza.exercises.catalog import all_exercises, load_catalog
from tiza.exercises.grading import grade_answer
from tiza.learning.policy import build_assignment_plan
from tiza.learning.state import derive_state


def test_reviewed_fraction_catalog_has_its_closed_scope() -> None:
    catalog = load_catalog()
    assert len(catalog["concepts"]) == 12
    assert len(catalog["exercises"]) == 36
    assert {item["kind"] for item in catalog["exercises"]} == {"multiple_choice", "numeric", "short"}


def test_catalog_adds_controlled_objective_variants_without_changing_base_bank() -> None:
    exercises = all_exercises()
    assert len(exercises) == 60
    assert len({item["id"] for item in exercises}) == 60
    for base in load_catalog()["exercises"]:
        variants = [item for item in exercises if item["concept_id"] == base["concept_id"] and item["kind"] == base["kind"]]
        assert {item["estimated_minutes"] for item in variants} == {base["estimated_minutes"]}
    simplification = next(item for item in exercises if item["id"] == "simplification-focus-v2")
    denominator = next(item for item in exercises if item["id"] == "common-denominator-focus-v2")
    assert grade_answer(simplification, "15/25")["result"] == "incorrect"
    assert grade_answer(denominator, "2/3")["result"] == "incorrect"


@given(
    numerator=st.integers(min_value=-100, max_value=100),
    denominator=st.integers(min_value=1, max_value=100),
    multiplier=st.integers(min_value=1, max_value=20),
)
def test_numeric_grading_accepts_equivalent_fraction_forms(numerator: int, denominator: int, multiplier: int) -> None:
    expected = Fraction(numerator, denominator)
    exercise = {"kind": "numeric", "answer": str(expected), "explanation": "ok"}
    result = grade_answer(exercise, f"{numerator * multiplier}/{denominator * multiplier}")
    assert result["result"] == "correct"


def test_grading_marks_help_and_defers_explanations() -> None:
    numeric = next(item for item in all_exercises() if item["id"] == "addition-unlike-focus-v1")
    assert grade_answer(numeric, "1.15", hints_used=1)["evidence_result"] == "partial"
    assert grade_answer(numeric, "__import__('os').system('false')")["result"] == "incorrect"
    short = next(item for item in all_exercises() if item["kind"] == "short")
    assert grade_answer(short, "My explanation")["result"] == "review_needed"
    assert grade_answer({"kind": "short_response"}, "Reasoning")["result"] == "review_needed"
    assert grade_answer({"kind": "numeric", "answer": ">"}, ">")["result"] == "correct"


def test_plan_starts_with_a_check_and_never_exceeds_budget() -> None:
    items, reasons = build_assignment_plan(
        {"target_concepts": ["add-different-denominator"], "evidence": {}},
        10,
    )
    assert items and items[0]["kind"] == "multiple_choice"
    assert sum(item["estimated_minutes"] for item in items) <= 10
    assert len(reasons) == len(items)
    assert items[1]["branch_after_exercise_id"] == items[0]["exercise_id"]
    assert items[1]["branch_on"] == "incorrect"


@given(budget=st.integers(min_value=1, max_value=60))
def test_every_possible_plan_stays_inside_its_budget(budget: int) -> None:
    items, _ = build_assignment_plan(
        {"target_concepts": ["add-different-denominator"], "evidence": {}},
        budget,
    )
    # One preapproved failure branch is deliberately counted in full. This is
    # conservative and proves the longest path cannot overrun the budget.
    assert sum(item["estimated_minutes"] for item in items) <= budget
    approved = {item["id"] for item in all_exercises()}
    assert {item["exercise_id"] for item in items} <= approved


def test_replaying_a_receipt_does_not_duplicate_evidence() -> None:
    receipt = {
        "receiptId": "attempt-1",
        "status": "verified",
        "payload": {
            "receiptId": "attempt-1",
            "issuedAt": "2026-09-01T12:00:00Z",
            "conditions": {"grader": "deterministic"},
            "claims": [{"concept": "equivalence", "ability": "apply", "result": "passed"}],
        },
    }
    once = derive_state([receipt], now="2026-09-02T12:00:00Z")
    assert derive_state([receipt, receipt], now="2026-09-02T12:00:00Z") == once

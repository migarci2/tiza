import pytest

from tiza.services import concept_candidates


def roles(goal: str) -> dict[str, str]:
    return {candidate["id"]: candidate["role"] for candidate in concept_candidates(goal)}


@pytest.mark.parametrize(
    ("goal", "concept_id"),
    [
        ("Add fractions with unlike denominators.", "add-different-denominator"),
        ("Sumar fracciones con denominadores distintos.", "add-different-denominator"),
        ("Subtract fractions with different denominators.", "subtraction"),
        ("Restar fracciones con denominadores distintos.", "subtraction"),
        ("Compare fractions.", "comparison"),
        ("Comparar fracciones.", "comparison"),
        ("Fracciones equivalentes.", "equivalence"),
        ("Fracciones como cantidad.", "fraction-quantity"),
        ("Simplificación de fracciones.", "simplification"),
    ],
)
def test_concept_candidates_match_explicit_english_and_spanish_goals(goal: str, concept_id: str):
    assert roles(goal)[concept_id] == "objective"


def test_concept_candidates_suggest_prerequisites_without_selecting_them_as_objectives():
    candidates = roles("Add fractions with unlike denominators.")
    assert candidates["add-different-denominator"] == "objective"
    assert candidates["common-denominator"] == "prerequisite"
    assert candidates["equivalence"] == "prerequisite"


def test_concept_candidates_cite_only_the_objective_for_an_objective_match():
    candidates = {candidate["id"]: candidate for candidate in concept_candidates("Add fractions with unlike denominators.")}
    assert candidates["add-different-denominator"]["reference"] == "teacher-objective"
    assert candidates["add-different-denominator"]["quote"] == "Add fractions with unlike denominators."
    assert candidates["common-denominator"]["reference"] == "catalog"
    assert candidates["common-denominator"]["quote"] == ""
    assert candidates["context"]["reference"] == "catalog"


def test_concept_candidates_leave_unknown_goals_unselected_and_offer_all_concepts():
    candidates = roles("Help learners become confident mathematicians.")
    assert len(candidates) == 12
    assert set(candidates.values()) == {"available"}

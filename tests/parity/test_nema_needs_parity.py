import json
from pathlib import Path

from tiza.learning.nema_needs import apply_implicit_repetition, compute_needs, encompassed_prereqs


FIXTURES = Path(__file__).parent / "fixtures"


def test_pinned_nema_needs_and_implicit_repetition_parity():
    source = json.loads((FIXTURES / "nema_needs_input.json").read_text())
    expected = json.loads((FIXTURES / "nema_needs_expected.json").read_text())
    registry = {item["id"]: item for item in source["concepts"]}
    assert encompassed_prereqs(registry["goal"], registry) == expected["encompassed"]
    assert apply_implicit_repetition(
        source["state"], concepts=source["concepts"], now=source["now"]
    ) == expected["implicit"]
    assert compute_needs(
        source["state"],
        concepts=source["concepts"],
        goals=source["goals"],
        misconceptions=source["misconceptions"],
        now=source["now"],
        budget_minutes=source["budgetMinutes"],
    ) == expected["needs"]

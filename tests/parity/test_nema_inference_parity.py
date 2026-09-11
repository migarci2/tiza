import json
from pathlib import Path

from tiza.learning.state import derive_state, summarize

ROOT = Path(__file__).resolve().parents[2]


def test_python_state_matches_fixture_generated_by_pinned_javascript() -> None:
    source = json.loads((ROOT / "vendor/nema/test/fixtures/inference-ledger.json").read_text())
    expected = json.loads((Path(__file__).parent / "fixtures/nema_inference_state.json").read_text())
    assert expected["source_commit"] == "6f630aff03f20e74b55406bc13b2b36433dc491b"
    state = derive_state(source["receipts"], now=source["now"])
    assert state == expected["state"]
    assert summarize(state, now=source["now"]) == expected["summary"]


def test_python_state_matches_pinned_javascript_edge_cases() -> None:
    fixtures = Path(__file__).parent / "fixtures"
    source = json.loads((fixtures / "nema_edge_input.json").read_text())
    expected = json.loads((fixtures / "nema_edge_expected.json").read_text())
    state = derive_state(source["receipts"], now=source["now"])
    assert state == expected["state"]
    assert summarize(state, now=source["now"]) == expected["summary"]
    assert derive_state([], now=source["now"]) == expected["emptyState"]
    assert summarize({}, now=source["now"]) == expected["emptySummary"]
    assert "edge:ignored" not in state
    assert state["edge:repetition"]["apply"]["passes"] == 2
    assert state["edge:failure"]["apply"]["stabilityDays"] == 3

"""Pure learner-state inference."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from math import exp
from typing import Any, Callable, Iterable

from .schedule import iso_millis, js_round, parse_instant, schedule_for

ABILITY_LADDER = ("recognize", "retrieve", "explain", "apply", "transfer")
SIDE_ABILITIES = ("discriminate",)
ABILITIES = ABILITY_LADDER + SIDE_ABILITIES
BANDS = ("unknown", "uncertain", "fragile", "usable", "durable")
WEIGHTS = {
    "deterministic": 1.0,
    "provider-rubric": 0.8,
    "agent-assessed": 0.6,
    "self-report": 0.3,
    "exposure": 0.1,
}
RESULT_VALUES = {"passed": 1.0, "partial": 0.5, "failed": -0.5}
GRADED_WEIGHT = WEIGHTS["agent-assessed"]


def band_rank(band: str | None) -> int:
    try:
        return BANDS.index(band)
    except ValueError:
        return 0


def best_band(concept_state: dict | None) -> str:
    best = "unknown"
    for entry in (concept_state or {}).values():
        if isinstance(entry, dict) and band_rank(entry.get("band")) > band_rank(best):
            best = entry["band"]
    return best


def _band_for(score: float, weight: float) -> str:
    band = "durable" if score >= 1.6 else "usable" if score >= 0.9 else "fragile" if score >= 0.4 else "uncertain" if score > 0 else "unknown"
    return "uncertain" if weight <= WEIGHTS["exposure"] and band_rank(band) > 1 else band


def _confidence_for(score: float, weight: float) -> str:
    if score >= 1.2 and weight >= 0.8:
        return "high"
    return "medium" if score >= 0.6 else "low"


def _targets(ability: Any) -> tuple[str, ...]:
    if ability in ABILITY_LADDER:
        return ABILITY_LADDER[: ABILITY_LADDER.index(ability) + 1]
    return (ability,) if ability in SIDE_ABILITIES else ()


def _weight_cap(weight_cap: Callable[[dict], float] | None, receipt: dict) -> float:
    if not weight_cap:
        return float("inf")
    try:
        value = weight_cap(receipt)
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return float("inf")


def derive_state(
    receipts: Iterable[dict] | None,
    *,
    now: str | int | float | datetime,
    weight_cap: Callable[[dict], float] | None = None,
) -> dict[str, dict[str, dict]]:
    """Derive state from verified evidence; duplicate receipt IDs count once."""
    now_dt = parse_instant(now)
    if now_dt is None:
        raise TypeError("tiza.learning: now is required and must be an ISO date or epoch milliseconds")

    buckets: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    seen: set[str] = set()
    for receipt in receipts or ():
        if not isinstance(receipt, dict) or receipt.get("status") not in {"verified", "agent"}:
            continue
        payload = receipt.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("claims"), list):
            continue
        receipt_id = receipt.get("receiptId") or payload.get("receiptId")
        if receipt_id and receipt_id in seen:
            continue
        if receipt_id:
            seen.add(receipt_id)
        grader = (payload.get("conditions") or {}).get("grader")
        weight = min(WEIGHTS.get(grader, WEIGHTS["exposure"]), _weight_cap(weight_cap, receipt))
        issued = parse_instant(payload.get("issuedAt")) or parse_instant(receipt.get("receivedAt")) or now_dt
        recency = exp(-max(0.0, (now_dt - issued).total_seconds() / 86400) / 60)

        for claim in payload["claims"]:
            if not isinstance(claim, dict) or not isinstance(claim.get("concept"), str):
                continue
            result = claim.get("result")
            if result not in RESULT_VALUES:
                continue
            for ability in _targets(claim.get("ability")):
                buckets[claim["concept"]][ability].append(
                    {
                        "value": weight * RESULT_VALUES[result] * recency,
                        "weight": weight,
                        "result": result,
                        "issued": issued,
                        "receiptId": receipt_id,
                    }
                )

    return {
        concept: {
            ability: _summarize_ability(abilities[ability], now_dt)
            for ability in sorted(abilities, key=ABILITIES.index)
        }
        for concept, abilities in sorted(buckets.items())
    }


def _summarize_ability(contributions: list[dict], now: datetime) -> dict:
    score = best_weight = passes = graded_passes = graded_score = 0.0
    last_success = last_graded = last_failure = None
    refs: list[str] = []
    for item in sorted(contributions, key=lambda value: value["issued"]):
        score += item["value"]
        best_weight = max(best_weight, item["weight"])
        if item["result"] == "passed" and item["weight"] > WEIGHTS["exposure"]:
            passes += 1
            last_success = item["issued"]
        if item["result"] == "passed" and item["weight"] >= GRADED_WEIGHT:
            graded_passes += 1
            graded_score += item["value"]
            last_graded = item["issued"]
        if item["result"] == "failed":
            last_failure = item["issued"]
        if item["receiptId"] and item["receiptId"] not in refs:
            refs.append(item["receiptId"])

    score = js_round(score)
    return {
        "band": _band_for(score, best_weight),
        "score": score,
        "confidence": _confidence_for(score, best_weight),
        "graderWeight": best_weight,
        "passes": passes,
        "gradedPasses": graded_passes,
        "gradedScore": js_round(graded_score),
        "lastSuccess": iso_millis(last_success) if last_success else None,
        "lastGradedPass": iso_millis(last_graded) if last_graded else None,
        "lastFailure": iso_millis(last_failure) if last_failure else None,
        **schedule_for(passes, last_success, last_failure, now),
        "evidenceRefs": refs,
    }


def to_assertion_status(band: str) -> str:
    if band in {"durable", "usable"}:
        return "verified"
    return "uncertain" if band in {"fragile", "uncertain"} else "missing"


def diff_states(before: dict | None, after: dict | None) -> list[dict[str, str]]:
    changes = []
    before, after = before or {}, after or {}
    for concept in sorted(set(before) | set(after)):
        abilities = sorted(set(before.get(concept, {})) | set(after.get(concept, {})), key=ABILITIES.index)
        for ability in abilities:
            old = before.get(concept, {}).get(ability, {}).get("band", "unknown")
            new = after.get(concept, {}).get(ability, {}).get("band", "unknown")
            if old != new:
                changes.append({"concept": concept, "ability": ability, "from": old, "to": new})
    return changes


def summarize(state: dict | None, *, now: str | int | float | datetime) -> dict[str, int]:
    now_dt = parse_instant(now)
    if now_dt is None:
        raise TypeError("tiza.learning: now is required")
    counts = {"concepts": 0, "durable": 0, "usable": 0, "fragile": 0, "uncertain": 0, "unknown": 0, "reviewsDue": 0}
    for concept_state in (state or {}).values():
        if not isinstance(concept_state, dict):
            continue
        counts["concepts"] += 1
        counts[best_band(concept_state)] += 1
        if any((parse_instant(entry.get("nextReview")) or datetime.max.replace(tzinfo=timezone.utc)) < now_dt for entry in concept_state.values() if isinstance(entry, dict)):
            counts["reviewsDue"] += 1
    return counts


def snapshot(state: dict, *, engine_version: str, input_hash: str, evaluated_at: str) -> dict:
    """Create a versioned, recomputable snapshot without mutating the state."""
    return {"engineVersion": engine_version, "inputHash": input_hash, "evaluatedAt": evaluated_at, "state": deepcopy(state)}

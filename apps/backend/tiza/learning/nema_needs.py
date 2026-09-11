"""Needs and implicit-repetition port from nema inference.js at 6f630aff03f2.

Tiza's assignment policy remains separate. These functions preserve nema's
interchange semantics and are checked against fixtures emitted by the pinned JS.
"""
from __future__ import annotations

from datetime import datetime
from math import inf, isfinite
from typing import Any

from .schedule import iso_millis, js_round, parse_instant, schedule_for
from .state import ABILITIES, ABILITY_LADDER, SIDE_ABILITIES, WEIGHTS, band_rank, best_band

IMPLICIT_FRACTION = 0.5
IMPLICIT_PASS = 0.5
GRADED_WEIGHT = WEIGHTS["agent-assessed"]
NEED_KINDS = ["acquire", "retrieve", "apply", "transfer", "discriminate", "repair_misconception", "reassess"]
NEED_ABILITY = {
    "acquire": "explain", "retrieve": "retrieve", "apply": "apply", "transfer": "transfer",
    "discriminate": "discriminate", "repair_misconception": "explain", "reassess": "explain",
}
NEED_URGENCY = {
    "acquire": 0.5, "retrieve": 0.6, "apply": 0.7, "transfer": 0.35,
    "discriminate": 0.65, "repair_misconception": 0.8, "reassess": 0.45,
}
EXERCISE_HINTS = {
    "acquire": "short explanation of the idea, then one worked example",
    "retrieve": "closed book recall, one prompt, no options and no hints",
    "apply": "one small task that forces the idea into use",
    "transfer": "the same idea in a context the learner has not seen before",
    "discriminate": "compare-and-contrast with one concrete failure case",
    "repair_misconception": "confront the misconception with a counterexample, then ask for the corrected rule",
    "reassess": "one deterministic check that confirms or drops the earlier evidence",
}
RUBRIC_FALLBACK = {
    "acquire": ["explain", "apply", "discriminate"], "retrieve": ["explain", "apply", "discriminate"],
    "apply": ["apply", "explain", "discriminate"], "transfer": ["apply", "explain", "discriminate"],
    "discriminate": ["discriminate", "explain", "apply"],
    "repair_misconception": ["explain", "apply", "discriminate"],
    "reassess": ["explain", "apply", "discriminate"],
}


def _now(value: Any) -> datetime:
    parsed = parse_instant(value)
    if parsed is None:
        raise TypeError("nema/inference: options.now is required and must be an ISO date string or epoch milliseconds")
    return parsed


def _band(state: dict, concept: str, ability: str) -> str:
    return (state.get(concept, {}).get(ability) or {}).get("band", "unknown")


def _band_for(score: float, weight: float) -> str:
    band = "durable" if score >= 1.6 else "usable" if score >= 0.9 else "fragile" if score >= 0.4 else "uncertain" if score > 0 else "unknown"
    return "uncertain" if weight <= WEIGHTS["exposure"] and band_rank(band) > 1 else band


def _confidence(score: float, weight: float) -> str:
    return "high" if score >= 1.2 and weight >= 0.8 else "medium" if score >= 0.6 else "low"


def encompassed_prereqs(definition: dict | None, registry: dict[str, dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not definition:
        return out
    declared = definition.get("encompasses") if isinstance(definition.get("encompasses"), dict) else {}
    prereqs = definition.get("prereqs") if isinstance(definition.get("prereqs"), list) else []
    for prereq in prereqs:
        if not isinstance(prereq, str) or prereq == definition.get("id"):
            continue
        stated = declared.get(prereq)
        fraction = min(1, stated) if isinstance(stated, (int, float)) and not isinstance(stated, bool) and stated > 0 else IMPLICIT_FRACTION
        if prereq not in out or out[prereq]["fraction"] < fraction:
            out[prereq] = {"fraction": fraction, "level": 1}
    for prereq in prereqs:
        stated = declared.get(prereq)
        if not isinstance(stated, (int, float)) or isinstance(stated, bool) or stated <= 0:
            continue
        fraction = min(1, stated) ** 2
        parent = registry.get(prereq) or {}
        grandparents = parent.get("prereqs") if isinstance(parent.get("prereqs"), list) else []
        for grandparent in grandparents:
            if not isinstance(grandparent, str) or grandparent == definition.get("id"):
                continue
            current = out.get(grandparent)
            if current and current["level"] == 1:
                continue
            if not current or current["fraction"] < fraction:
                out[grandparent] = {"fraction": fraction, "level": 2}
    return out


def apply_implicit_repetition(state: dict | None, *, concepts: list[dict] | None = None, now: Any) -> dict:
    at = _now(now)
    source = state if isinstance(state, dict) else {}
    if not concepts:
        return source
    registry = {item["id"]: item for item in concepts if isinstance(item, dict) and isinstance(item.get("id"), str)}
    credit: dict[str, dict[str, dict]] = {}
    for concept_id, concept_state in source.items():
        definition = registry.get(concept_id)
        if not definition or not isinstance(concept_state, dict):
            continue
        edges = encompassed_prereqs(definition, registry)
        for ability, entry in concept_state.items():
            if not isinstance(entry, dict) or not entry.get("gradedPasses", 0) > 0:
                continue
            graded_at = parse_instant(entry.get("lastGradedPass"))
            for prereq_id, edge in edges.items():
                prereq_entry = (source.get(prereq_id) or {}).get(ability)
                if not prereq_entry:
                    continue
                bucket = credit.setdefault(prereq_id, {}).setdefault(
                    ability, {"score": 0.0, "weight": 0.0, "passes": 0.0, "at": None, "from": set()}
                )
                bucket["score"] += edge["fraction"] * entry.get("gradedScore", 0)
                bucket["weight"] = max(bucket["weight"], edge["fraction"] * entry.get("graderWeight", 0))
                bucket["from"].add(concept_id)
                own_success = parse_instant(prereq_entry.get("lastSuccess"))
                if graded_at is None or (own_success is not None and graded_at <= own_success):
                    continue
                bucket["passes"] += entry["gradedPasses"] * IMPLICIT_PASS ** edge["level"]
                if bucket["at"] is None or graded_at > bucket["at"]:
                    bucket["at"] = graded_at
    if not credit:
        return source
    result = {}
    for concept_id, concept_state in source.items():
        if concept_id not in credit:
            result[concept_id] = concept_state
            continue
        result[concept_id] = {}
        for ability, entry in concept_state.items():
            bucket = credit[concept_id].get(ability)
            if not bucket:
                result[concept_id][ability] = entry
                continue
            score = js_round(entry["score"] + bucket["score"])
            weight = max(entry["graderWeight"], js_round(bucket["weight"]))
            passes = js_round(entry["passes"] + bucket["passes"], 3)
            own_success = parse_instant(entry.get("lastSuccess"))
            last_success = bucket["at"] if bucket["at"] and (not own_success or bucket["at"] > own_success) else own_success
            schedule = schedule_for(passes, last_success, parse_instant(entry.get("lastFailure")), at)
            result[concept_id][ability] = {
                **entry,
                "band": _band_for(score, weight), "score": score, "confidence": _confidence(score, weight),
                "graderWeight": weight, "passes": passes,
                "lastSuccess": iso_millis(last_success) if last_success else None,
                **schedule,
                "implicit": {"score": js_round(bucket["score"]), "passes": js_round(bucket["passes"], 3), "from": sorted(bucket["from"])},
            }
    return result


def _ability_order(ability: str) -> int:
    return ABILITIES.index(ability) if ability in ABILITIES else len(ABILITIES)


def _review_due(entry: dict, now: datetime) -> bool:
    next_review = parse_instant(entry.get("nextReview"))
    return next_review < now if next_review else entry.get("reviewDue") is True


def _worst_overdue(concept_state: dict, now: datetime) -> dict | None:
    ladder_days = side_days = None
    side_ability = None
    for ability, entry in concept_state.items():
        on_ladder = ability in ABILITY_LADDER and ABILITY_LADDER.index(ability) >= ABILITY_LADDER.index("retrieve")
        if not (on_ladder or ability in SIDE_ABILITIES) or not _review_due(entry, now):
            continue
        next_review = parse_instant(entry.get("nextReview"))
        days = (now - next_review).total_seconds() / 86400 if next_review else 0
        if on_ladder and (ladder_days is None or days > ladder_days):
            ladder_days = days
        elif not on_ladder and (side_days is None or days > side_days):
            side_days, side_ability = days, ability
    if ladder_days is None and side_days is None:
        return None
    return {
        "ability": side_ability if ladder_days is None else "retrieve",
        "days": max(-inf if ladder_days is None else ladder_days, -inf if side_days is None else side_days),
    }


def _best_weight(state: dict) -> float:
    return max((entry.get("graderWeight", 0) for entry in state.values() if isinstance(entry, dict)), default=0)


def _unrepaired(state: dict) -> dict | None:
    found = None
    for ability, entry in state.items():
        failed, success = parse_instant(entry.get("lastFailure")), parse_instant(entry.get("lastSuccess"))
        if failed and (not success or success < failed) and (not found or _ability_order(ability) > _ability_order(found["ability"])):
            found = {"ability": ability, "at": entry["lastFailure"]}
    return found


def _readiness(concept_id: str, registry: dict, state: dict) -> float:
    prereqs = (registry.get(concept_id) or {}).get("prereqs", [])
    return inf if not prereqs else sum(band_rank(best_band(state.get(item))) >= band_rank("usable") for item in prereqs) - len(prereqs)


def _weakest(concept_id: str, registry: dict, state: dict, depth: int = 8, seen: set | None = None) -> str | None:
    seen = seen or set()
    prereqs = (registry.get(concept_id) or {}).get("prereqs", [])
    blocking = [item for item in prereqs if isinstance(item, str) and item not in seen and band_rank(best_band(state.get(item))) < band_rank("usable")]
    if not blocking:
        return None
    blocking.sort(key=lambda item: (band_rank(best_band(state.get(item))), -_readiness(item, registry, state), item))
    weakest = blocking[0]
    if depth <= 0:
        return weakest
    deeper = _weakest(weakest, registry, state, depth - 1, seen | {concept_id, weakest})
    return weakest if deeper is None else deeper


def _base36(number: int) -> str:
    chars, out = "0123456789abcdefghijklmnopqrstuvwxyz", ""
    while number:
        number, remainder = divmod(number, 36)
        out = chars[remainder] + out
    return out or "0"


def _short_hash(value: str) -> str:
    hashed = 0x811C9DC5
    for char in value:
        hashed ^= ord(char)
        hashed = (hashed * 0x01000193) & 0xFFFFFFFF
    return _base36(hashed).rjust(7, "0")


def _rubric(definition: dict | None, kind: str, ability: str) -> list:
    rubric = (definition or {}).get("rubric")
    if not rubric:
        return []
    for key in [kind, ability, *RUBRIC_FALLBACK.get(kind, RUBRIC_FALLBACK["reassess"]), *sorted(rubric)]:
        if isinstance(rubric.get(key), list) and rubric[key]:
            return list(rubric[key])
    return []


def _need(context: dict, kind: str, **extra) -> dict:
    concept_id, definition = context["concept_id"], context["definition"]
    ability = extra.get("ability") or NEED_ABILITY[kind]
    relevance = 1.5 if concept_id in context["goal_concepts"] else 1.2 if concept_id in context["goal_prereqs"] else 1
    urgency = js_round(min(1, extra.get("urgency", NEED_URGENCY[kind])), 3)
    stated = ((definition or {}).get("minutes") or {}).get(ability, 4)
    minutes = stated if isinstance(stated, (int, float)) and not isinstance(stated, bool) and stated > 0 else 4
    if kind == "retrieve":
        minutes = min(minutes, 4)
    reason = list(extra.get("reason", []))
    if relevance == 1.5:
        reason.append("active_goal_depends_on_this_concept")
    elif relevance == 1.2:
        reason.append("prerequisite_of_an_active_goal")
    return {
        "needId": f"need_{_short_hash(f'{concept_id}|{kind}')}", "concept": concept_id,
        "conceptTitle": (definition or {}).get("title", concept_id), "ability": ability, "kind": kind,
        "reason": reason, "note": "You have read about this. You have not retrieved it yet." if "exposure_only" in reason else None,
        "urgency": urgency, "minutes": minutes, "confusableWith": extra.get("confusableWith"),
        "exerciseHint": EXERCISE_HINTS[kind], "rubric": _rubric(definition, kind, ability),
        "constraints": {"maxHints": 0 if kind == "retrieve" else 1, "doNotRevealAnswerBeforeSubmission": True},
        "misconceptions": extra.get("misconceptions", []), "goalRelevance": relevance,
        "priority": js_round((urgency * relevance) / max(2, minutes), 5),
    }


def _plan(needs: list[dict], budget: float, registry: dict) -> list[dict]:
    neighbours: dict[str, set[str]] = {}
    for concept_id, definition in registry.items():
        for other in definition.get("confusableWith", []):
            if isinstance(other, str) and other != concept_id:
                neighbours.setdefault(concept_id, set()).add(other)
                neighbours.setdefault(other, set()).add(concept_id)
    picked, remaining = [], budget
    for source in needs:
        if source["minutes"] > remaining:
            continue
        clash = next((item for item in picked if item["kind"] != "discriminate" and source["kind"] != "discriminate" and source["concept"] in neighbours.get(item["concept"], set())), None)
        if clash:
            if "interference_avoided" not in clash["reason"]:
                clash["reason"].append("interference_avoided")
            continue
        item = {**source, "reason": list(source["reason"])}
        picked.append(item)
        remaining -= item["minutes"]
    session, waiting = [], picked[:]
    while waiting:
        index = 0
        if session:
            previous = session[-1]
            found = next((i for i, item in enumerate(waiting) if item["concept"] != previous["concept"] and item["kind"] != previous["kind"]), -1)
            if found < 0:
                found = next((i for i, item in enumerate(waiting) if item["concept"] != previous["concept"]), -1)
            if found >= 0:
                index = found
        item = waiting.pop(index)
        if index > 0:
            item["reason"].append("interleaved")
        session.append(item)
    return session


def compute_needs(
    state: dict | None, *, concepts: list[dict] | None = None, goals: list[dict] | None = None,
    misconceptions: list[dict] | None = None, now: Any, budget_minutes: float | None = None,
) -> list[dict]:
    at, concepts, goals, misconceptions = _now(now), concepts or [], goals or [], misconceptions or []
    registry = {item["id"]: item for item in concepts if isinstance(item, dict) and isinstance(item.get("id"), str)}
    source = apply_implicit_repetition(state, concepts=concepts, now=at)
    goal_concepts, goal_prereqs = set(), set()
    for goal in goals:
        goal_ids = goal.get("concepts", []) if isinstance(goal, dict) else []
        for concept_id in goal_ids if isinstance(goal_ids, list) else []:
            goal_concepts.add(concept_id)
            goal_prereqs.update((registry.get(concept_id) or {}).get("prereqs", []))
    recorded: dict[str, list] = {}
    for item in misconceptions:
        if isinstance(item, dict) and isinstance(item.get("concept"), str):
            recorded.setdefault(item["concept"], []).append(
                {"id": item.get("id") or None, "text": item.get("text") or ""}
            )
    needs, redirected = [], {}
    for concept_id in sorted(set(registry) | set(source)):
        definition, concept_state = registry.get(concept_id), source.get(concept_id, {})
        context = {"concept_id": concept_id, "definition": definition, "goal_concepts": goal_concepts, "goal_prereqs": goal_prereqs}
        overdue, has_evidence = _worst_overdue(concept_state, at), bool(concept_state)
        exposure_only = has_evidence and _best_weight(concept_state) <= WEIGHTS["self-report"]
        if overdue is not None or exposure_only:
            reason, urgency, ability = [], NEED_URGENCY["retrieve"], NEED_ABILITY["retrieve"]
            if overdue is not None:
                days = max(0, js_round(overdue["days"], 1))
                reason.extend(["spaced_review_is_due", f"overdue_by_{days:g}_days"])
                urgency, ability = min(1, 0.6 + 0.4 * overdue["days"] / 7), overdue["ability"]
            if exposure_only:
                reason.append("exposure_only")
            needs.append(_need(context, "retrieve", ability=ability, urgency=urgency, reason=reason))
        if band_rank(_band(source, concept_id, "explain")) >= band_rank("usable") and band_rank(_band(source, concept_id, "apply")) <= band_rank("fragile"):
            needs.append(_need(context, "apply", reason=["explanation_is_solid", "application_is_weak"]))
        confusables = (definition or {}).get("confusableWith", [])
        first = confusables[0] if isinstance(confusables, list) and confusables else None
        confusable = first if isinstance(first, str) and first else None
        strong = band_rank(_band(source, concept_id, "apply")) >= band_rank("usable") or band_rank(_band(source, concept_id, "explain")) >= band_rank("usable")
        if confusable and strong and "discriminate" not in concept_state:
            neighbour_strong = band_rank(best_band(source.get(confusable))) >= band_rank("usable")
            reason = ["application_is_strong", "no_discrimination_evidence"] + (["confusable_neighbour_is_strong"] if neighbour_strong else [])
            needs.append(_need(context, "discriminate", reason=reason, urgency=0.8 if neighbour_strong else NEED_URGENCY["discriminate"], confusableWith=confusable))
        if (concept_id in goal_concepts or concept_id in goal_prereqs) and band_rank(best_band(concept_state)) == 0:
            blocking = _weakest(concept_id, registry, source)
            if blocking is None:
                needs.append(_need(context, "acquire", reason=["goal_depends_on_this_concept", "no_evidence_yet"]))
            else:
                redirected.setdefault(blocking, set()).add(concept_id)
                needs.append(_need(context, "acquire", urgency=NEED_URGENCY["acquire"] / 2, reason=["goal_depends_on_this_concept", "prerequisites_are_not_ready", f"start_with_{blocking.removeprefix('nema:').replace('-', '_')}"]))
        failure, known = _unrepaired(concept_state), recorded.get(concept_id)
        if known:
            needs.append(_need(context, "repair_misconception", ability=failure["ability"] if failure else None, reason=["recorded_misconception", *[item["id"] or "unnamed_misconception" for item in known], *(["failed_claim_on_record"] if failure else [])], misconceptions=known))
        if has_evidence and (_best_weight(concept_state) < GRADED_WEIGHT or (failure and not known)):
            weak = _best_weight(concept_state) < GRADED_WEIGHT
            reason = (["evidence_is_weakly_graded", "no_strong_grader_on_record"] if weak else []) + (["failed_claim_on_record", "nothing_has_confirmed_it_since"] if failure and not known else [])
            ability = failure["ability"] if failure and not known else max(concept_state, key=_ability_order, default="explain")
            needs.append(_need(context, "reassess", reason=reason, ability=ability))
        if _band(source, concept_id, "apply") == "durable" and _band(source, concept_id, "transfer") == "unknown":
            needs.append(_need(context, "transfer", reason=["application_is_durable", "no_transfer_evidence"]))
    for target, blocked in redirected.items():
        candidates = sorted((item for item in needs if item["concept"] == target), key=lambda item: -item["priority"])
        need = candidates[0] if candidates else _need({"concept_id": target, "definition": registry.get(target), "goal_concepts": goal_concepts, "goal_prereqs": goal_prereqs}, "acquire", reason=["goal_depends_on_this_concept", "no_evidence_yet"])
        if not candidates:
            needs.append(need)
        if "prerequisite_first" not in need["reason"]:
            need["reason"].insert(0, "prerequisite_first")
        named = sorted(item for item in blocked if item in goal_concepts) or sorted(blocked)
        for item in named:
            token = f"before_{item.removeprefix('nema:').replace('-', '_')}"
            if token not in need["reason"]:
                need["reason"].append(token)
    needs.sort(key=lambda item: (-item["priority"], -item["urgency"], item["concept"], NEED_KINDS.index(item["kind"])))
    return _plan(needs, budget_minutes, registry) if isinstance(budget_minutes, (int, float)) and not isinstance(budget_minutes, bool) and isfinite(budget_minutes) and budget_minutes > 0 else needs

"""Spaced-review arithmetic ported from nema's pinned inference engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import floor


def parse_instant(value: str | int | float | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value / 1000, timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def iso_millis(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def js_round(value: float, places: int = 4) -> float:
    factor = 10**places
    return floor(value * factor + 0.5) / factor


def schedule_for(
    passes: float,
    last_success: datetime | None,
    last_failure: datetime | None,
    now: datetime,
) -> dict:
    if last_success is None or passes <= 0:
        return {"stabilityDays": None, "nextReview": None, "reviewDue": False}
    stability = min(60, 3 * 2 ** (passes - 1))
    if last_failure is not None and last_failure > last_success:
        stability = 3
    stability = js_round(stability, 2)
    next_review = last_success + timedelta(days=stability)
    return {
        "stabilityDays": stability,
        "nextReview": iso_millis(next_review),
        "reviewDue": next_review < now,
    }

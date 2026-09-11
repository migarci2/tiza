from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .validation import validate_catalog

CATALOG_PATH = Path(__file__).resolve().parents[4] / "curricula" / "fractions" / "catalog.json"


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    validate_catalog(catalog)
    return catalog


def all_exercises() -> list[dict]:
    return [dict(item) for item in load_catalog()["exercises"]]


def get_exercise(exercise_id: str) -> dict:
    for exercise in load_catalog()["exercises"]:
        if exercise["id"] == exercise_id:
            return dict(exercise)
    raise KeyError(exercise_id)

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import Assignment, AssignmentItem, Attempt, EvidenceEvent, ExerciseVersion, LearningCycle
from ...security import Principal
from .crypto import public_jwk, sign_token
from .models import NemaGrant
from .readiness import aware, require_learner


def _private_key() -> ec.EllipticCurvePrivateKey:
    filename = os.environ.get("TIZA_NEMA_PRIVATE_KEY_FILE")
    if not filename:
        raise HTTPException(503, "Tiza receipt signing is not configured")
    try:
        key = serialization.load_pem_private_key(Path(filename).read_bytes(), password=None)
    except (OSError, ValueError, TypeError) as error:
        raise HTTPException(503, "Tiza receipt signing key could not be loaded") from error
    if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
        raise HTTPException(503, "Tiza receipt signing key must be P-256")
    return key


def export_receipt(db: Session, principal: Principal, attempt_id: str, *, now: datetime | None = None) -> dict:
    require_learner(principal)
    current = now or datetime.now(timezone.utc)
    attempt = db.get(Attempt, attempt_id)
    assignment = db.get(Assignment, attempt.assignment_id) if attempt else None
    cycle = db.get(LearningCycle, assignment.cycle_id) if assignment else None
    if (
        not attempt
        or attempt.learner_id != principal.user.id
        or not assignment
        or assignment.learner_id != principal.user.id
        or not cycle
        or cycle.organization_id != principal.membership.organization_id
    ):
        raise HTTPException(404, "Attempt not found")
    grant = db.scalar(
        select(NemaGrant)
        .where(
            NemaGrant.learner_id == principal.user.id,
            NemaGrant.organization_id == principal.membership.organization_id,
            NemaGrant.revoked_at.is_(None),
            NemaGrant.expires_at > current,
        )
        .order_by(NemaGrant.created_at.desc())
    )
    if not grant:
        raise HTTPException(403, "Link a nema vault before exporting a receipt")
    event = db.scalar(
        select(EvidenceEvent)
        .where(EvidenceEvent.attempt_id == attempt.id, EvidenceEvent.learner_id == principal.user.id)
        .order_by(EvidenceEvent.revision.desc())
    )
    item = db.get(AssignmentItem, attempt.item_id)
    exercise = db.get(ExerciseVersion, item.exercise_id) if item else None
    objective = exercise and exercise.kind in {"numeric", "multiple_choice"} and event and event.evaluator == "deterministic"
    human_reviewed = event and event.evaluator in {"teacher", "human", "provider-rubric"}
    if not event or not exercise or not (objective or human_reviewed):
        raise HTTPException(409, "Only verified objective or teacher-reviewed work can be exported")
    if event.outcome not in {"correct", "incorrect", "partial"}:
        raise HTTPException(409, "This attempt has no exportable result")

    key = _private_key()
    issued_at = aware(event.created_at).isoformat(timespec="seconds").replace("+00:00", "Z")
    attempts = db.scalar(
        select(func.count()).select_from(Attempt).where(
            Attempt.assignment_id == assignment.id,
            Attempt.item_id == item.id,
            Attempt.learner_id == principal.user.id,
        )
    )
    issuer = os.environ.get("TIZA_NEMA_ISSUER", "https://tiza.local")
    payload = {
        "type": "evidence-receipt",
        "protocol": "nema/0.1",
        "receiptId": f"tiza:{event.id}:{event.revision}",
        "issuer": issuer,
        "keyId": os.environ.get("TIZA_NEMA_KEY_ID", "self:" + issuer),
        "issuerKey": public_jwk(key),
        "subject": grant.learner_key_id,
        "activity": {
            "id": exercise.id,
            "version": "1",
            "title": exercise.prompt,
            "contentHash": "sha256:" + sha256(exercise.prompt.encode()).hexdigest(),
        },
        "claims": [{
            "concept": event.concept_id,
            "ability": "apply",
            "evidenceType": "application",
            "result": (
                "partial"
                if event.outcome == "partial" or (event.outcome == "correct" and event.used_hint)
                else "passed" if event.outcome == "correct" else "failed"
            ),
        }],
        "conditions": {
            "attempts": attempts,
            "hintsUsed": 1 if event.used_hint else 0,
            "grader": "deterministic" if objective else "provider-rubric",
            "graderVersion": attempt.verifier_version,
        },
        "issuedAt": issued_at,
    }
    return {"token": sign_token(payload, key), "receipt": payload, "issuerKey": public_jwk(key)}

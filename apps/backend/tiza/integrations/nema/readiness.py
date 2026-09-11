from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import Enrollment, ExerciseVersion, LearningCycle
from ...security import Principal
from .crypto import decode_token
from .models import NemaGrant, NemaReadinessRequest
from .protocol import request_hash, timestamp, verify_assertion

AUDIENCE = "TIZA_NEMA_AUDIENCE"


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def audience() -> str:
    return os.environ.get(AUDIENCE, "https://tiza.local")


def require_learner(principal: Principal) -> None:
    if principal.actor.id != principal.user.id or principal.membership.role != "learner":
        raise HTTPException(403, "This consent action belongs to the learner")


def create_readiness_request(
    db: Session,
    principal: Principal,
    *,
    cycle_id: str,
    requirements: list[dict],
    purpose: str,
    now: datetime | None = None,
) -> NemaReadinessRequest:
    require_learner(principal)
    current = now or datetime.now(timezone.utc)
    cycle = db.get(LearningCycle, cycle_id)
    enrollment = db.scalar(
        select(Enrollment).where(
            Enrollment.classroom_id == (cycle.classroom_id if cycle else ""),
            Enrollment.learner_id == principal.user.id,
            Enrollment.status == "active",
        )
    )
    if not cycle or cycle.organization_id != principal.membership.organization_id or not enrollment:
        raise HTTPException(404, "Learning cycle not found")
    if not cycle.concept_confirmed:
        raise HTTPException(409, "The teacher must confirm the cycle concepts first")
    requested = {(item["concept"], item["ability"]) for item in requirements}
    if len(requested) != len(requirements):
        raise HTTPException(422, "Duplicate readiness requirement")
    if not requested or any(concept not in cycle.concepts for concept, _ in requested):
        raise HTTPException(422, "Readiness scope must stay within this cycle")
    approved = set(
        db.scalars(
            select(ExerciseVersion.concept_id).where(
                ExerciseVersion.concept_id.in_({concept for concept, _ in requested}),
                ExerciseVersion.approved.is_(True),
            )
        )
    )
    if approved != {concept for concept, _ in requested}:
        raise HTTPException(422, "Every requested concept needs an approved exercise")

    request_json = {
        "protocol": "nema/0.1",
        "audience": audience(),
        "purpose": purpose,
        "requirements": requirements,
    }
    record = NemaReadinessRequest(
        organization_id=cycle.organization_id,
        learner_id=principal.user.id,
        cycle_id=cycle.id,
        request_hash=request_hash(request_json),
        request_json=request_json,
        expires_at=current + timedelta(minutes=30),
    )
    db.add(record)
    db.flush()
    return record


def accept_readiness(
    db: Session,
    principal: Principal,
    *,
    token: str,
    confirm_unknown_key: bool,
    now: datetime | None = None,
) -> NemaGrant:
    require_learner(principal)
    current = now or datetime.now(timezone.utc)
    try:
        untrusted, _, _ = decode_token(token)
        record = db.scalar(
            select(NemaReadinessRequest).where(
                NemaReadinessRequest.request_hash == untrusted.get("requestHash"),
                NemaReadinessRequest.learner_id == principal.user.id,
                NemaReadinessRequest.organization_id == principal.membership.organization_id,
                NemaReadinessRequest.consumed_at.is_(None),
            ).order_by(NemaReadinessRequest.created_at.desc())
        )
    except Exception as error:
        raise HTTPException(422, "Invalid readiness assertion") from error
    if not record:
        raise HTTPException(404, "No matching consent request")
    if record.consumed_at or aware(record.expires_at) <= current:
        raise HTTPException(409, "Consent request is expired or already used")
    cycle = db.get(LearningCycle, record.cycle_id)
    enrollment = db.scalar(select(Enrollment).where(Enrollment.classroom_id == cycle.classroom_id,
        Enrollment.learner_id == principal.user.id, Enrollment.status == "active")) if cycle else None
    if not enrollment or cycle.organization_id != principal.membership.organization_id:
        raise HTTPException(403, "Enrollment is no longer active")
    existing = db.scalar(
        select(NemaGrant)
        .where(
            NemaGrant.learner_id == principal.user.id,
            NemaGrant.organization_id == principal.membership.organization_id,
            NemaGrant.revoked_at.is_(None),
            NemaGrant.expires_at > current,
        )
        .order_by(NemaGrant.created_at.desc())
    )
    incoming_key = untrusted.get("vaultKey")
    unknown_key = not existing or existing.vault_key != incoming_key
    if unknown_key and not confirm_unknown_key:
        raise HTTPException(409, "Explicit consent is required to link this vault key")
    try:
        payload = verify_assertion(
            token,
            audience=audience(),
            now=current,
            request=record.request_json,
            expected_key=existing.vault_key if existing and not unknown_key else None,
        )
    except Exception as error:
        raise HTTPException(422, "Readiness assertion failed verification") from error

    grant = NemaGrant(
        organization_id=record.organization_id,
        learner_id=record.learner_id,
        request_id=record.id,
        learner_key_id=payload["learnerKeyId"],
        vault_key=payload["vaultKey"],
        scope=record.request_json["requirements"],
        assertions=payload["assertions"],
        purpose=payload["purpose"],
        expires_at=min(timestamp(payload["expiresAt"]), aware(record.expires_at)),
    )
    record.consumed_at = current
    db.add(grant)
    db.flush()
    return grant


def revoke_grant(db: Session, principal: Principal, grant_id: str) -> NemaGrant:
    require_learner(principal)
    grant = db.get(NemaGrant, grant_id)
    if not grant or grant.learner_id != principal.user.id or grant.organization_id != principal.membership.organization_id:
        raise HTTPException(404, "Grant not found")
    if grant.revoked_at is None:
        grant.revoked_at = datetime.now(timezone.utc)
    return grant

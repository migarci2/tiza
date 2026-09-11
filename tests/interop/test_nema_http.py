from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tiza.db import Base, get_db
from tiza.integrations.nema.crypto import encode, public_jwk, sign_token, verify_token
from tiza.integrations.nema.models import NemaGrant
from tiza.integrations.nema.protocol import request_hash
from tiza.integrations.nema.router import router
from tiza.models import (
    Assignment,
    AssignmentItem,
    Classroom,
    Enrollment,
    EvidenceEvent,
    ExerciseVersion,
    LearningCycle,
    Membership,
    Organization,
    User,
    WebSession,
)
from tiza.security import Principal, require_principal


def iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def assertion(request: dict, key: ec.EllipticCurvePrivateKey, statuses: list[dict]) -> str:
    now = datetime.now(timezone.utc)
    jwk = public_jwk(key)
    payload = {
        "type": "readiness-assertion",
        "protocol": "nema/0.1",
        "audience": request["audience"],
        "purpose": request["purpose"],
        "requestHash": request_hash(request),
        "learnerKeyId": "lk_" + encode(sha256((jwk["x"] + "|" + request["audience"]).encode()).digest())[:16],
        "assertions": statuses,
        "issuedAt": iso(now - timedelta(seconds=1)),
        "expiresAt": iso(now + timedelta(minutes=10)),
        "vaultKey": jwk,
    }
    return sign_token(payload, key)


def test_consent_scope_receipt_and_revocation(monkeypatch, tmp_path) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Demo")
    learner = User(auth_subject="learner", email="l@example.test", display_name="Learner")
    db.add_all([organization, learner])
    db.flush()
    membership = Membership(organization_id=organization.id, user_id=learner.id, role="learner")
    classroom = Classroom(organization_id=organization.id, teacher_id=learner.id, title="Fractions")
    db.add_all([membership, classroom])
    db.flush()
    db.add(Enrollment(classroom_id=classroom.id, learner_id=learner.id))
    cycle = LearningCycle(
        organization_id=organization.id,
        classroom_id=classroom.id,
        objective="Add unlike fractions",
        concepts=["equivalence"],
        concept_confirmed=True,
        closes_at=datetime.now(timezone.utc) + timedelta(days=1),
        budget_minutes=10,
    )
    exercise = ExerciseVersion(
        id="equivalence-v1",
        concept_id="equivalence",
        kind="numeric",
        prompt="Simplify 4/6",
        answer="2/3",
        explanation="Divide by two",
        hint="Use a common factor",
        estimated_minutes=2,
        approved=True,
    )
    short_exercise = ExerciseVersion(
        id="equivalence-explain-v1",
        concept_id="equivalence",
        kind="short_response",
        prompt="Explain equivalence",
        answer=None,
        explanation="Teacher reviewed",
        hint=None,
        estimated_minutes=3,
        approved=True,
    )
    db.add_all([cycle, exercise, short_exercise])
    db.flush()
    assignment = Assignment(
        cycle_id=cycle.id,
        learner_id=learner.id,
        version=1,
        reason="check",
        estimated_minutes=2,
        published=True,
    )
    db.add(assignment)
    db.flush()
    item = AssignmentItem(assignment_id=assignment.id, exercise_id=exercise.id, position=1)
    short_item = AssignmentItem(assignment_id=assignment.id, exercise_id=short_exercise.id, position=2)
    db.add_all([item, short_item])
    db.flush()
    from tiza.models import Attempt
    attempt = Attempt(
        assignment_id=assignment.id,
        item_id=item.id,
        learner_id=learner.id,
        client_key="attempt-key-1",
        response="2/3",
        used_hint=True,
        result="correct",
        score=1,
    )
    db.add(attempt)
    db.flush()
    short_attempt = Attempt(
        assignment_id=assignment.id,
        item_id=short_item.id,
        learner_id=learner.id,
        client_key="attempt-key-2",
        response="Both terms change by the same factor.",
        used_hint=False,
        result="review_needed",
        score=None,
    )
    db.add(short_attempt)
    db.flush()
    event = EvidenceEvent(
        learner_id=learner.id,
        concept_id="equivalence",
        attempt_id=attempt.id,
        outcome="correct",
        evaluator="deterministic",
        used_hint=True,
    )
    db.add(event)
    short_event = EvidenceEvent(
        learner_id=learner.id,
        concept_id="equivalence",
        attempt_id=short_attempt.id,
        outcome="correct",
        evaluator="agent-assessed",
        used_hint=False,
    )
    db.add(short_event)
    db.commit()

    fake_session = WebSession(token_hash="x", csrf_hash="x", user_id=learner.id, expires_at=datetime.now(timezone.utc))
    principal = Principal(actor=learner, user=learner, membership=membership, session=fake_session)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_principal] = lambda: principal
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    created = client.post(
        "/api/integrations/nema/readiness/request",
        json={"cycle_id": cycle.id, "requirements": [{"concept": "equivalence", "ability": "apply"}]},
    )
    assert created.status_code == 200, created.text
    request = created.json()["request"]
    vault_key = ec.generate_private_key(ec.SECP256R1())
    token = assertion(request, vault_key, [{"concept": "equivalence", "ability": "apply", "status": "ready", "confidence": "low"}])
    assert client.post("/api/integrations/nema/readiness", json={"token": token}).status_code == 409
    accepted = client.post(
        "/api/integrations/nema/readiness",
        json={"token": token, "confirm_unknown_key": True},
    )
    assert accepted.status_code == 200, accepted.text

    issuer_key = ec.generate_private_key(ec.SECP256R1())
    key_file = tmp_path / "issuer.pem"
    key_file.write_bytes(
        issuer_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    monkeypatch.setenv("TIZA_NEMA_PRIVATE_KEY_FILE", str(key_file))
    receipt = client.get(f"/api/attempts/{attempt.id}/receipt")
    assert receipt.status_code == 200, receipt.text
    payload = verify_token(receipt.json()["token"], receipt.json()["issuerKey"])
    assert payload["subject"].startswith("lk_")
    assert payload["claims"] == [{"concept": "equivalence", "ability": "apply", "evidenceType": "application", "result": "partial"}]
    assert payload["conditions"]["hintsUsed"] == 1

    assert client.get(f"/api/attempts/{short_attempt.id}/receipt").status_code == 409
    short_event.evaluator = "teacher"
    db.commit()
    reviewed = client.get(f"/api/attempts/{short_attempt.id}/receipt")
    assert reviewed.status_code == 200
    assert reviewed.json()["receipt"]["conditions"]["grader"] == "provider-rubric"

    grant_id = db.scalar(NemaGrant.__table__.select().with_only_columns(NemaGrant.id))
    assert client.delete(f"/api/integrations/nema/grants/{grant_id}").status_code == 200
    assert client.get(f"/api/attempts/{attempt.id}/receipt").status_code == 403


def test_assertion_cannot_exceed_requested_scope() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Demo")
    learner = User(auth_subject="learner-2", email="l2@example.test", display_name="Learner")
    db.add_all([organization, learner])
    db.flush()
    membership = Membership(organization_id=organization.id, user_id=learner.id, role="learner")
    classroom = Classroom(organization_id=organization.id, teacher_id=learner.id, title="Fractions")
    db.add_all([membership, classroom])
    db.flush()
    db.add(Enrollment(classroom_id=classroom.id, learner_id=learner.id))
    cycle = LearningCycle(organization_id=organization.id, classroom_id=classroom.id, objective="Fractions", concepts=["equivalence"], concept_confirmed=True, closes_at=datetime.now(timezone.utc) + timedelta(days=1), budget_minutes=10)
    exercise = ExerciseVersion(concept_id="equivalence", kind="numeric", prompt="Simplify", answer="1/2", explanation="", hint=None, approved=True)
    db.add_all([cycle, exercise])
    db.commit()
    principal = Principal(learner, learner, membership, WebSession(token_hash="y", csrf_hash="y", user_id=learner.id, expires_at=datetime.now(timezone.utc)))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_principal] = lambda: principal
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)
    request = client.post("/api/integrations/nema/readiness/request", json={"cycle_id": cycle.id, "requirements": [{"concept": "equivalence", "ability": "apply"}]}).json()["request"]
    token = assertion(request, ec.generate_private_key(ec.SECP256R1()), [{"concept": "subtraction", "ability": "apply", "status": "ready", "confidence": "high"}])
    response = client.post("/api/integrations/nema/readiness", json={"token": token, "confirm_unknown_key": True})
    assert response.status_code == 422
    assert db.query(NemaGrant).count() == 0

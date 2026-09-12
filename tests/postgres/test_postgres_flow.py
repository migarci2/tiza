"""Run with TIZA_TEST_POSTGRES_URL set to an already migrated disposable database."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from tiza.db import get_db
from tiza.main import app
from tiza.models import Assignment, Attempt, Delivery, EvidenceEvent
from tiza.services import prepare_cycle


def test_full_api_flow_on_postgresql() -> None:
    url = os.environ.get("TIZA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("set TIZA_TEST_POSTGRES_URL to an isolated migrated PostgreSQL database")
    engine = create_engine(url)
    sessions = sessionmaker(engine, expire_on_commit=False)

    private_tables = {
        "organizations", "users", "memberships", "classrooms", "enrollments", "invitations",
        "learning_cycles", "materials", "exercise_versions", "assignments", "assignment_items",
        "approvals", "attempts", "assistance_events", "evidence_events", "deliveries", "jobs",
        "outbox_events", "audit_events", "web_sessions", "nema_readiness_requests", "nema_grants",
        "idempotency_records", "usage_buckets",
    }
    with sessions() as db:
        rls = set(db.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' AND c.relkind='r' AND c.relrowsecurity"
        )).scalars())
        assert private_tables <= rls
        exposed = db.execute(text(
            "SELECT grantee, table_name, privilege_type FROM information_schema.role_table_grants "
            "WHERE table_schema='public' AND grantee IN ('anon','authenticated','PUBLIC')"
        )).all()
        assert exposed == []

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    suffix = uuid4().hex
    try:
        verified = client.post("/api/auth/demo-code", json={"code": "246810"})
        assert verified.status_code == 200, verified.text
        login = verified.json()
        headers = {"X-CSRF-Token": login["csrf_token"]}
        created = client.post(
            "/api/cycles",
            headers={**headers, "Idempotency-Key": "postgres-cycle-" + suffix},
            json={
                "classroom_id": login["classroom_id"],
                "objective": "Add fractions with unlike denominators",
                "concepts": [],
                "closes_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
                "budget_minutes": 10,
            },
        )
        assert created.status_code == 200, created.text
        cycle = created.json()
        replay = client.post(
            "/api/cycles",
            headers={**headers, "Idempotency-Key": "postgres-cycle-" + suffix},
            json={
                "classroom_id": login["classroom_id"],
                "objective": "ignored replay body",
                "concepts": [],
                "closes_at": (datetime.now(timezone.utc) + timedelta(days=3)).isoformat(),
                "budget_minutes": 5,
            },
        )
        assert replay.json()["id"] == cycle["id"]
        confirmed = client.post(
            f"/api/cycles/{cycle['id']}/concepts",
            headers=headers,
            json={"concept_ids": ["equivalence", "add-different-denominator"]},
        )
        assert confirmed.status_code == 200
        queued = client.post(f"/api/cycles/{cycle['id']}/prepare", headers=headers).json()
        with sessions() as db:
            prepare_cycle(db, cycle["id"], queued["job_id"])
            db.commit()
        draft = client.get(f"/api/cycles/{cycle['id']}/draft").json()
        approval = client.post(
            f"/api/cycles/{cycle['id']}/approve",
            headers=headers,
            json={
                "version": 1,
                "assignment_ids": [item["id"] for item in draft["assignments"]],
                "allow_reminder": True,
            },
        )
        assert approval.status_code == 200, approval.text
        published = client.post(
            f"/api/cycles/{cycle['id']}/publish",
            headers=headers,
            json={"approval_id": approval.json()["id"], "version": 1},
        )
        assert published.status_code == 200, published.text

        assignment = draft["assignments"][0]
        learner = client.post(
            "/api/demo/switch",
            headers=headers,
            json={"user_id": assignment["learner"]["id"]},
        ).json()
        learner_headers = {"X-CSRF-Token": learner["csrf_token"]}
        practice = client.get(f"/api/assignments/{assignment['id']}").json()
        item = practice["items"][0]
        body = {"item_id": item["id"], "response": "wrong", "client_key": "postgres-attempt-" + suffix}
        first = client.post(f"/api/assignments/{assignment['id']}/attempts", headers=learner_headers, json=body)
        second = client.post(f"/api/assignments/{assignment['id']}/attempts", headers=learner_headers, json=body)
        assert first.status_code == 200 and second.json()["id"] == first.json()["id"]

        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(EvidenceEvent).where(EvidenceEvent.attempt_id == first.json()["id"])) == 1
            duplicate = Attempt(
                assignment_id=assignment["id"],
                item_id=item["id"],
                learner_id=assignment["learner"]["id"],
                client_key="postgres-attempt-" + suffix,
                response="again",
                result="incorrect",
                score=0,
            )
            db.add(duplicate)
            with pytest.raises(IntegrityError):
                db.commit()
            db.rollback()

        delivery_id = published.json()["deliveries"][0]["id"]
        with sessions() as locked, sessions() as contender:
            held = locked.scalar(select(Delivery).where(Delivery.id == delivery_id).with_for_update())
            skipped = contender.scalar(select(Delivery).where(Delivery.id == delivery_id).with_for_update(skip_locked=True))
            assert held is not None and skipped is None
            locked.rollback()
            contender.rollback()

        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Assignment).where(Assignment.cycle_id == cycle["id"])) == 8
    finally:
        app.dependency_overrides.clear()
        engine.dispose()

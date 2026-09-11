from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tiza.db import Base, get_db
import tiza.main as main_module
import tiza.security as security_module
from tiza.main import app
from tiza.models import AuditEvent, Attempt, Classroom, Enrollment, EvidenceEvent, Invitation, LearningCycle, Membership, Organization, User
from tiza.security import create_session, digest
from tiza.services import prepare_cycle


def demo_login(client: TestClient) -> dict:
    verified = client.post("/api/auth/demo-code", json={"code": "246810"})
    assert verified.status_code == 200
    return verified.json()


def test_demo_requires_access_code_and_has_no_direct_session_shortcut(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        shortcut = client.post("/api/demo/session")
        assert shortcut.status_code == 410
        assert client.get("/api/session").status_code == 401

        assert client.post("/api/auth/demo-code", json={}).status_code == 422
        wrong = client.post("/api/auth/demo-code", json={"code": "000000"})
        assert wrong.status_code == 401
        assert client.get("/api/session").status_code == 401

        login = demo_login(client)
        assert login["role"] == "teacher" and login["demo"] is True
        assert client.get("/api/session").status_code == 200
        assert client.post("/api/auth/request-code", json={"email": "unused@example.test"}).status_code == 400
        assert client.post("/api/auth/verify-code", json={"email": "unused@example.test", "code": "246810"}).status_code == 400
        client.post("/api/auth/logout", headers={"X-CSRF-Token": login["csrf_token"]})
        monkeypatch.setattr(main_module, "get_settings", lambda: SimpleNamespace(demo_mode=False))
        assert client.post("/api/auth/demo-code", json={"code": "246810"}).status_code == 404
        assert client.get("/api/session").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_cycle_permissions_versions_and_idempotent_evidence():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    login = demo_login(client)
    csrf = login["csrf_token"]
    assert client.get("/api/session").json()["csrf_token"] == csrf
    headers = {"X-CSRF-Token": csrf}
    classroom_id = login["classroom_id"]
    teacher_id = login["actor"]["id"]
    assert client.patch(
        "/api/workspace", headers=headers, json={"timezone": "Europe/Madrid"}
    ).json()["timezone"] == "Europe/Madrid"
    assert client.patch(
        "/api/workspace", headers=headers, json={"timezone": "Mars/Olympus"}
    ).status_code == 422

    cycle_body = {
        "classroom_id": classroom_id,
        "objective": "Add fractions with unlike denominators",
        "concepts": [],
        "closes_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        "budget_minutes": 15,
    }
    cycle = client.post(
        "/api/cycles",
        headers={**headers, "Idempotency-Key": "create-cycle-once"},
        json=cycle_body,
    ).json()
    duplicate = client.post(
        "/api/cycles",
        headers={**headers, "Idempotency-Key": "create-cycle-once"},
        json=cycle_body,
    ).json()
    assert duplicate["id"] == cycle["id"]
    assert client.post(f"/api/cycles/{cycle['id']}/prepare", headers=headers).status_code == 409
    material = client.post(
        f"/api/cycles/{cycle['id']}/materials",
        headers=headers,
        files={"file": ("lesson.md", b"Equivalent fractions and common denominators", "text/markdown")},
    )
    assert material.status_code == 200 and material.json()["concept_candidates"]
    assert client.post(
        f"/api/cycles/{cycle['id']}/concepts",
        headers=headers,
        json={"concept_ids": ["equivalence", "common-denominator", "add-different-denominator"]},
    ).status_code == 200
    queued = client.post(f"/api/cycles/{cycle['id']}/prepare", headers=headers)
    assert queued.status_code == 202 and queued.json()["state"] == "queued"
    with Session() as db:
        from tiza.agent.runner import prepare_with_agent
        from tiza.models import Job
        prepare_with_agent(db, db.get(Job, queued.json()["job_id"]))
        db.commit()

    run = client.get(f"/api/cycles/{cycle['id']}/agent-run").json()
    assert run["state"] == "completed" and run["draft_count"] == 8
    assert run["mode"] == "deterministic_demo" and run["model_invoked"] is False
    assert run["tools"] == [] and len(run["operations"]) == 3
    assert "payload" not in run and "actor_id" not in run
    draft = client.get(f"/api/cycles/{cycle['id']}/draft").json()
    assert len(draft["assignments"]) == 8
    assert len({assignment["reason"] for assignment in draft["assignments"]}) > 1
    assert all(
        sum(item["exercise"]["estimated_minutes"] for item in assignment["items"]) <= 15
        for assignment in draft["assignments"]
    )
    recipient_ids = [assignment["id"] for assignment in draft["assignments"]]
    approval = client.post(
        f"/api/cycles/{cycle['id']}/approve",
        headers=headers,
        json={"version": 1, "assignment_ids": recipient_ids, "allow_reminder": True},
    )
    assert approval.status_code == 200
    assert client.post(
        f"/api/cycles/{cycle['id']}/approve",
        headers=headers,
        json={"version": 1, "assignment_ids": recipient_ids, "allow_reminder": False},
    ).status_code == 409

    changed_response = client.patch(
        f"/api/cycles/{cycle['id']}/draft",
        headers=headers,
        json={"version": 1, "assignments": [{"id": recipient_ids[0], "excluded": True}]},
    )
    assert changed_response.status_code == 200, changed_response.text
    changed = changed_response.json()
    stale = client.post(
        f"/api/cycles/{cycle['id']}/publish",
        headers=headers,
        json={"approval_id": approval.json()["id"], "version": 1},
    )
    assert stale.status_code == 409

    budget_change = client.patch(
        f"/api/cycles/{cycle['id']}",
        headers=headers,
        json={"version": 2, "budget_minutes": 20},
    )
    assert budget_change.status_code == 200
    assert budget_change.json()["budget_minutes"] == 20
    changed = client.get(f"/api/cycles/{cycle['id']}/draft").json()

    active = [assignment for assignment in changed["assignments"] if not assignment["excluded"]]
    approval = client.post(
        f"/api/cycles/{cycle['id']}/approve",
        headers=headers,
        json={"version": 3, "assignment_ids": [assignment["id"] for assignment in active]},
    ).json()
    published = client.post(
        f"/api/cycles/{cycle['id']}/publish",
        headers=headers,
        json={"approval_id": approval["id"], "version": 3},
    )
    assert published.status_code == 200
    again = client.post(
        f"/api/cycles/{cycle['id']}/publish",
        headers=headers,
        json={"approval_id": approval["id"], "version": 3},
    ).json()
    assert len(again["deliveries"]) == 7
    with Session() as db:
        stored_cycle = db.get(LearningCycle, cycle["id"])
        original_close = stored_cycle.closes_at
        stored_cycle.closes_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.post(
        f"/api/cycles/{cycle['id']}/publish",
        headers=headers,
        json={"approval_id": approval["id"], "version": 3},
    ).status_code == 409
    with Session() as db:
        db.get(LearningCycle, cycle["id"]).closes_at = original_close
        db.commit()

    learner_id = active[0]["learner"]["id"]
    switched = client.post("/api/demo/switch", headers=headers, json={"user_id": learner_id}).json()
    learner_headers = {"X-CSRF-Token": switched["csrf_token"]}
    assignment_id = active[0]["id"]
    practice = client.get(f"/api/assignments/{assignment_id}")
    assert practice.status_code == 200
    branch = next(entry for entry in active[0]["items"] if entry["branch_after_item_id"])
    assert branch["id"] not in {entry["id"] for entry in practice.json()["items"]}
    hidden = client.post(
        f"/api/assignments/{assignment_id}/attempts",
        headers=learner_headers,
        json={"item_id": branch["id"], "response": "2/3", "client_key": "hidden-branch-key"},
    )
    assert hidden.status_code == 404
    item = practice.json()["items"][0]
    assert "hint" not in item["exercise"] and "explanation" not in item["exercise"]
    hint = client.post(
        f"/api/assignments/{assignment_id}/items/{item['id']}/hint", headers=learner_headers
    )
    assert hint.status_code == 200 and hint.json()["hint"]
    payload = {"item_id": item["id"], "response": "wrong", "client_key": "same-attempt-key"}
    first = client.post(f"/api/assignments/{assignment_id}/attempts", headers=learner_headers, json=payload)
    second = client.post(f"/api/assignments/{assignment_id}/attempts", headers=learner_headers, json=payload)
    assert first.json()["id"] == second.json()["id"] and first.json()["used_hint"] is True
    opened = client.get(f"/api/assignments/{assignment_id}").json()
    assert branch["id"] in {entry["id"] for entry in opened["items"]}
    with Session() as db:
        assert db.scalar(select(func.count()).select_from(EvidenceEvent).where(EvidenceEvent.attempt_id == first.json()["id"])) == 1

    other_assignment_id = active[1]["id"]
    assert client.get(f"/api/assignments/{other_assignment_id}").status_code == 404
    back = client.post("/api/demo/switch", headers=learner_headers, json={"user_id": teacher_id})
    assert back.status_code == 200 and back.json()["role"] == "teacher"
    teacher_headers = {"X-CSRF-Token": back.json()["csrf_token"]}
    with Session() as db:
        db.get(Attempt, first.json()["id"]).result = "review_needed"
        db.commit()
    assert first.json()["id"] in client.get(f"/api/cycles/{cycle['id']}/pending-reviews").json()
    detail = client.get(f"/api/attempts/{first.json()['id']}").json()
    assert detail["learner"] and detail["question"] and detail["response"] == "wrong"
    reviewed = client.post(
        f"/api/attempts/{first.json()['id']}/review",
        headers=teacher_headers,
        json={"outcome": "correct", "feedback": "Accepted after review."},
    )
    assert reviewed.status_code == 200 and reviewed.json()["revision"] == 1
    with Session() as db:
        assert db.scalar(
            select(AuditEvent.id).where(
                AuditEvent.action == "attempt.reviewed", AuditEvent.object_id == first.json()["id"]
            )
        )
    app.dependency_overrides.clear()


def test_organization_scope_is_not_bypassed_by_ids():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    login = demo_login(client)
    private_cycle = client.post("/api/cycles", headers={"X-CSRF-Token": login["csrf_token"]}, json={
        "classroom_id": login["classroom_id"], "objective": "Add fractions", "budget_minutes": 10,
        "closes_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
    }).json()
    with Session() as db:
        foreign_org = Organization(name="Other organization")
        foreign_user = User(auth_subject="other:teacher", email="other@example.test", display_name="Other")
        db.add_all([foreign_org, foreign_user])
        db.flush()
        db.add(Membership(organization_id=foreign_org.id, user_id=foreign_user.id, role="teacher"))
        _, token, csrf = create_session(db, foreign_user)
        db.commit()
    client.cookies.set("tiza_session", token)
    response = client.get(f"/api/classrooms/{login['classroom_id']}")
    assert response.status_code == 404
    assert client.get(f"/api/cycles/{private_cycle['id']}/agent-run").status_code == 404
    app.dependency_overrides.clear()


def test_supabase_identity_binds_one_time_invitation_for_existing_user(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override_db():
        with Session() as db:
            yield db

    settings = SimpleNamespace(
        demo_mode=False,
        supabase_url="https://supabase.test",
        supabase_anon_key="anon",
        session_ttl_hours=24,
        session_secure=False,
        agent_mode="bedrock",
    )
    monkeypatch.setattr(main_module, "get_settings", lambda: settings)
    monkeypatch.setattr(security_module, "get_settings", lambda: settings)

    class FakeSupabase:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, json, **kwargs):
            email = json["email"]
            subjects = {"invited@example.test": "existing-subject"}
            return httpx.Response(
                200,
                json={"user": {"id": subjects.get(email, f"subject-{email}"), "email": email}},
            )

    monkeypatch.setattr(main_module.httpx, "AsyncClient", lambda **kwargs: FakeSupabase())
    with Session() as db:
        organization = Organization(name="Inviting organization")
        teacher = User(auth_subject="inviter", email="teacher@example.test", display_name="Teacher")
        existing = User(
            auth_subject="existing-subject", email="invited@example.test", display_name="Existing"
        )
        db.add_all([organization, teacher, existing])
        db.flush()
        classroom = Classroom(
            organization_id=organization.id, teacher_id=teacher.id, title="Class", language="en"
        )
        db.add(classroom)
        db.flush()
        valid = Invitation(
            classroom_id=classroom.id,
            email="invited@example.test",
            token_hash=digest("valid-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        expired = Invitation(
            classroom_id=classroom.id,
            email="expired@example.test",
            token_hash=digest("expired-token"),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        wrong_email = Invitation(
            classroom_id=classroom.id,
            email="right@example.test",
            token_hash=digest("wrong-email-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        db.add_all([valid, expired, wrong_email])
        db.commit()

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    accepted = client.post(
        "/api/auth/verify-code",
        json={"email": "invited@example.test", "code": "123456", "invite_token": "valid-token"},
    )
    assert accepted.status_code == 200 and accepted.json()["role"] == "learner"
    with Session() as db:
        user = db.scalar(select(User).where(User.auth_subject == "existing-subject"))
        assert db.scalar(select(Enrollment).where(Enrollment.learner_id == user.id))
        assert db.scalar(select(Invitation).where(Invitation.token_hash == digest("valid-token"))).accepted_by == user.id

    assert client.post(
        "/api/auth/verify-code",
        json={"email": "invited@example.test", "code": "123456", "invite_token": "valid-token"},
    ).status_code == 403
    assert client.post(
        "/api/auth/verify-code",
        json={"email": "expired@example.test", "code": "123456", "invite_token": "expired-token"},
    ).status_code == 403
    assert client.post(
        "/api/auth/verify-code",
        json={"email": "wrong@example.test", "code": "123456", "invite_token": "wrong-email-token"},
    ).status_code == 403
    app.dependency_overrides.clear()

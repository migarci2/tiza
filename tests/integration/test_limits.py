from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tiza.config import get_settings
from tiza.db import Base, get_db
from tiza.main import app
from tiza.models import Job, UsageBucket


def test_daily_admission_is_idempotent_and_survives_demo_reset(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    settings = get_settings()
    monkeypatch.setattr(settings, "preparations_per_day", 1)
    monkeypatch.setattr(settings, "materials_per_day", 1)

    def override_db():
        with Session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(app)
        login = client.post("/api/auth/demo-code", json={"code": "246810"}).json()
        headers = {"X-CSRF-Token": login["csrf_token"]}

        def create():
            response = client.post("/api/cycles", headers=headers, json={
                "classroom_id": login["classroom_id"], "objective": "Compare fractions",
                "concepts": [], "closes_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                "budget_minutes": 10,
            })
            assert response.status_code == 200, response.text
            cycle_id = response.json()["id"]
            assert client.post(f"/api/cycles/{cycle_id}/concepts", headers=headers,
                               json={"concept_ids": ["comparison"]}).status_code == 200
            return cycle_id

        first = create()
        upload = lambda: client.post(f"/api/cycles/{first}/materials", headers=headers,
                                    files={"file": ("lesson.md", b"Compare fractions", "text/markdown")})
        assert upload().status_code == 200
        assert upload().status_code == 429
        queued = client.post(f"/api/cycles/{first}/prepare", headers=headers)
        assert queued.status_code == 202
        replay = client.post(f"/api/cycles/{first}/prepare", headers=headers)
        assert replay.status_code == 202 and replay.json()["job_id"] == queued.json()["job_id"]
        with Session() as db:
            job = db.get(Job, queued.json()["job_id"])
            job.state = "running"
            db.commit()
        assert client.post("/api/demo/reset", headers=headers).status_code == 409
        with Session() as db:
            db.get(Job, queued.json()["job_id"]).state = "failed"
            db.commit()
        assert client.post("/api/demo/reset", headers=headers).status_code == 200
        second = create()
        denied = client.post(f"/api/cycles/{second}/prepare", headers=headers)
        assert denied.status_code == 429 and int(denied.headers["Retry-After"]) > 0
        with Session() as db:
            assert list(db.scalars(select(UsageBucket.used))) == [1, 1]
        monkeypatch.setattr(settings, "demo_reset_enabled", False)
        assert client.get("/api/config").json()["demo_reset_enabled"] is False
        assert client.post("/api/demo/reset", headers=headers).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_bedrock_admission_is_global_and_failed_reservation_rolls_back():
    from fastapi import HTTPException
    from tiza.limits import reserve_daily
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine)
    with Session() as db:
        reserve_daily(db, "bedrock-preparations:global", 1)
        db.commit()
    with Session() as db:
        reserve_daily(db, "preparations:another-organization", 10)
        try:
            reserve_daily(db, "bedrock-preparations:global", 1)
        except HTTPException as exc:
            assert exc.status_code == 429
            db.rollback()
        else:
            raise AssertionError("Global quota should refuse a second reservation")
    with Session() as db:
        assert len(list(db.scalars(select(UsageBucket)))) == 1

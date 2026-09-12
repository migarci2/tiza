from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tiza.agent.runner import prepare_with_agent
from tiza.db import Base, get_db
from tiza.main import app
from tiza.models import Assignment, ExerciseVersion, Job


def test_replacing_one_exercise_preserves_branch_graph_and_old_version() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)

    def override_db():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    client = TestClient(app)
    try:
        login = client.post("/api/auth/demo-code", json={"code": "246810"}).json()
        headers = {"X-CSRF-Token": login["csrf_token"]}
        cycle = client.post("/api/cycles", headers={**headers, "Idempotency-Key": "branch-cycle"}, json={
            "classroom_id": login["classroom_id"],
            "objective": "Add fractions with unlike denominators",
            "concepts": ["equivalence", "common-denominator", "add-different-denominator"],
            "closes_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "budget_minutes": 15,
        }).json()
        client.post(f"/api/cycles/{cycle['id']}/concepts", headers=headers, json={
            "concept_ids": ["equivalence", "common-denominator", "add-different-denominator"]})
        queued = client.post(f"/api/cycles/{cycle['id']}/prepare", headers=headers).json()
        with sessions() as db:
            prepare_with_agent(db, db.get(Job, queued["job_id"]))
            db.commit()

        before = client.get(f"/api/cycles/{cycle['id']}/draft").json()
        old = next(assignment for assignment in before["assignments"]
            if any(item["branch_after_item_id"] for item in assignment["items"]))
        old_items = old["items"]
        old_ids = [item["exercise"]["id"] for item in old_items]
        replace_at = next(index for index, item in enumerate(old_items) if item["branch_after_item_id"] is None)
        replaced = old_items[replace_at]["exercise"]
        with sessions() as db:
            alternative = db.scalar(select(ExerciseVersion).where(
                ExerciseVersion.approved.is_(True),
                ExerciseVersion.concept_id == replaced["concept_id"],
                ExerciseVersion.kind == replaced["kind"],
                ExerciseVersion.id.not_in(old_ids),
            ))
            assert alternative is not None
            replacement_ids = [*old_ids]
            replacement_ids[replace_at] = alternative.id

        response = client.patch(f"/api/cycles/{cycle['id']}/draft", headers=headers, json={
            "version": 1, "assignments": [{"id": old["id"], "exercise_ids": replacement_ids}]})
        assert response.status_code == 200, response.text
        after = response.json()
        new = next(assignment for assignment in after["assignments"]
            if assignment["learner"]["id"] == old["learner"]["id"])

        old_parent_positions = {item["id"]: index for index, item in enumerate(old_items)}
        new_positions = {item["id"]: index for index, item in enumerate(new["items"])}
        assert [item["branch_on"] for item in new["items"]] == [item["branch_on"] for item in old_items]
        assert [new_positions.get(item["branch_after_item_id"]) for item in new["items"]] == [
            old_parent_positions.get(item["branch_after_item_id"]) for item in old_items]

        with sessions() as db:
            immutable = db.get(Assignment, old["id"])
            assert immutable.version == 1
            assert [item.exercise_id for item in immutable.items] == old_ids
            assert [item.branch_on for item in immutable.items] == [item["branch_on"] for item in old_items]
    finally:
        app.dependency_overrides.clear()

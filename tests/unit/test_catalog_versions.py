from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from tiza.db import Base
from tiza.exercises.catalog import RETIRED_EXERCISE_IDS, all_exercises, load_catalog
from tiza.learning.policy import build_assignment_plan
from tiza.models import Assignment, AssignmentItem, ExerciseVersion, LearningCycle
from tiza.services import _add_bank, seed_demo


def test_bank_update_preserves_historical_exercise_and_assignment(tmp_path) -> None:
    engine = create_engine("sqlite:///" + str(tmp_path / "versions.db"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    retired_id = "common-denominator-focus-v1"
    original = next(item for item in load_catalog()["exercises"] if item["id"] == retired_id)

    with sessions() as db:
        organization, classroom, _, learners = seed_demo(db)
        old = ExerciseVersion(**original, source="Old reviewed bank", approved=True)
        db.add(old)
        cycle = LearningCycle(organization_id=organization.id, classroom_id=classroom.id,
            objective="Fractions", concepts=["common-denominator"], concept_confirmed=True,
            closes_at=datetime.now(timezone.utc) + timedelta(days=1), budget_minutes=10)
        db.add(cycle); db.flush()
        assignment = Assignment(cycle_id=cycle.id, learner_id=learners[0].id, version=1,
            reason="Historical", estimated_minutes=old.estimated_minutes)
        db.add(assignment); db.flush()
        item = AssignmentItem(assignment_id=assignment.id, exercise_id=old.id, position=1)
        db.add(item); db.commit()

        _add_bank(db)
        db.commit()
        db.expire_all()

        preserved = db.get(ExerciseVersion, retired_id)
        assert (preserved.prompt, preserved.answer, preserved.approved) == (
            original["prompt"], original["answer"], False)
        assert db.get(AssignmentItem, item.id).exercise_id == retired_id
        assert db.get(AssignmentItem, item.id).exercise.prompt == original["prompt"]
        assert db.get(ExerciseVersion, "common-denominator-focus-v2").answer == "8"
        assert db.get(ExerciseVersion, "common-denominator-focus-v3").answer == "15"

        approved_ids = set(db.scalars(select(ExerciseVersion.id).where(ExerciseVersion.approved.is_(True))))
        assert not approved_ids & RETIRED_EXERCISE_IDS
        plan, _ = build_assignment_plan({"target_concepts": ["common-denominator"], "evidence": {}}, 10)
        assert {entry["exercise_id"] for entry in plan} <= {entry["id"] for entry in all_exercises()}

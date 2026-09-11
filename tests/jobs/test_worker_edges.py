from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
import sys

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from tiza.agent import runner
from tiza.db import Base
from tiza.jobs import worker
from tiza.models import (
    Approval,
    Assignment,
    AuditEvent,
    Delivery,
    Enrollment,
    Job,
    LearningCycle,
)
from tiza.services import seed_demo


def _database(tmp_path, name: str):
    engine = create_engine("sqlite:///" + str(tmp_path / name))
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


def _delivery_case(db, at: datetime):
    organization, classroom, teacher, learners = seed_demo(db)
    organization.timezone = "UTC"
    cycle = LearningCycle(
        organization_id=organization.id,
        classroom_id=classroom.id,
        objective="Check",
        concepts=["equivalence"],
        concept_confirmed=True,
        closes_at=at + timedelta(hours=4),
        budget_minutes=10,
        state="active",
    )
    db.add(cycle)
    db.flush()
    assignment = Assignment(
        cycle_id=cycle.id,
        learner_id=learners[0].id,
        version=1,
        reason="Check",
        estimated_minutes=2,
        published=True,
    )
    db.add(assignment)
    db.flush()
    approval = Approval(
        cycle_id=cycle.id,
        actor_id=teacher.id,
        version=1,
        batch_hash="fixture",
        recipient_ids=[learners[0].id],
        permissions=["publish", "reminder"],
    )
    delivery = Delivery(
        assignment_id=assignment.id,
        recipient_id=learners[0].id,
        idempotency_key="fixture-delivery",
    )
    db.add_all([approval, delivery])
    db.flush()
    job = Job(
        id="delivery-" + delivery.id,
        organization_id=organization.id,
        kind="delivery",
        payload={"delivery_id": delivery.id},
        state="running",
        attempts=1,
    )
    db.add(job)
    db.commit()
    return organization, classroom, learners[0], cycle, assignment, delivery, job


def test_quiet_hours_defer_without_network_or_retry_cost(tmp_path, monkeypatch) -> None:
    sessions = _database(tmp_path, "quiet.db")
    at = datetime(2026, 9, 10, 22, tzinfo=timezone.utc)
    monkeypatch.setattr(worker, "utcnow", lambda: at)
    monkeypatch.setattr(worker.httpx, "post", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network")))
    with sessions() as db:
        *_, delivery, job = _delivery_case(db, at)
        worker.deliver(db, job)
        assert delivery.state == "queued" and delivery.first_attempt_at is None
        assert job.state == "queued" and job.attempts == 0
        assert worker._aware(job.available_at) == at + timedelta(minutes=30)


def test_delivery_revalidates_enrollment_and_reminders_are_single(tmp_path, monkeypatch) -> None:
    sessions = _database(tmp_path, "permission.db")
    at = datetime(2026, 9, 10, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(worker, "utcnow", lambda: at)
    with sessions() as db:
        _, classroom, learner, cycle, assignment, delivery, job = _delivery_case(db, at)
        enrollment = db.scalar(select(Enrollment).where(Enrollment.classroom_id == classroom.id, Enrollment.learner_id == learner.id))
        enrollment.status = "removed"
        db.commit()
        worker.deliver(db, job)
        assert delivery.state == "cancelled"

        enrollment.status = "active"
        db.add(AuditEvent(organization_id=cycle.organization_id, actor_id=learner.id, action="reminders.cancelled", object_type="cycle", object_id=cycle.id))
        db.commit()
        worker.schedule_reminders(db)
        worker.schedule_reminders(db)
        assert db.scalar(select(func.count()).select_from(Delivery).where(Delivery.assignment_id == assignment.id, Delivery.channel == "reminder")) == 0


def _fake_strands(monkeypatch, *, alter_items: bool = False) -> None:
    strands = ModuleType("strands")
    hooks = ModuleType("strands.hooks")
    models = ModuleType("strands.models")
    executors = ModuleType("strands.tools.executors")

    class HookProvider:
        pass

    class BeforeModelCallEvent:
        pass

    class Placeholder:
        def __init__(self, *args, **kwargs):
            pass

    class Agent:
        def __init__(self, *, tools, **kwargs):
            self.tools = {function.__name__: function for function in tools}

        def __call__(self, prompt):
            rows = self.tools["select_validated_exercises"]()
            for row in rows:
                ids = [item["id"] for item in row["items"]]
                if alter_items:
                    ids = ids[:-1]
                self.tools["save_assignment_draft"](row["assignment_id"], ids, row["reason"])
            self.tools["request_teacher_review"]()
            return SimpleNamespace(metrics=SimpleNamespace(accumulated_usage={"inputTokens": 1}))

    strands.Agent = Agent
    strands.tool = lambda function: function
    hooks.BeforeModelCallEvent = BeforeModelCallEvent
    hooks.HookProvider = HookProvider
    models.BedrockModel = Placeholder
    executors.SequentialToolExecutor = Placeholder
    monkeypatch.setitem(sys.modules, "strands", strands)
    monkeypatch.setitem(sys.modules, "strands.hooks", hooks)
    monkeypatch.setitem(sys.modules, "strands.models", models)
    monkeypatch.setitem(sys.modules, "strands.tools.executors", executors)


def test_bedrock_agent_mock_can_only_save_the_policy_sequence(tmp_path, monkeypatch) -> None:
    sessions = _database(tmp_path, "agent.db")
    _fake_strands(monkeypatch)
    monkeypatch.setattr(runner, "get_settings", lambda: SimpleNamespace(agent_mode="bedrock", demo_mode=False))
    monkeypatch.setenv("TIZA_BEDROCK_MODEL_ID", "mock-model")
    with sessions() as db:
        organization, classroom, teacher, _ = seed_demo(db)
        cycle = LearningCycle(
            organization_id=organization.id,
            classroom_id=classroom.id,
            objective="Equivalent fractions",
            concepts=["equivalence"],
            concept_confirmed=True,
            closes_at=datetime.now(timezone.utc) + timedelta(days=1),
            budget_minutes=10,
            state="preparing",
        )
        db.add(cycle)
        db.flush()
        job = Job(
            organization_id=organization.id,
            kind="prepare_cycle",
            payload={"cycle_id": cycle.id, "actor_id": teacher.id, "cycle_version": 1},
            state="running",
        )
        db.add(job)
        db.flush()
        runner.prepare_with_agent(db, job)
        assert job.payload["agent"]["model"] == "mock-model"
        assert job.payload["agent"]["tools"][-1] == "request_teacher_review"
        assert db.scalar(select(func.count()).select_from(Assignment).where(Assignment.cycle_id == cycle.id)) == 8


def test_agent_rejects_a_model_that_drops_a_preapproved_branch(tmp_path, monkeypatch) -> None:
    sessions = _database(tmp_path, "agent-reject.db")
    _fake_strands(monkeypatch, alter_items=True)
    monkeypatch.setattr(runner, "get_settings", lambda: SimpleNamespace(agent_mode="bedrock", demo_mode=False))
    monkeypatch.setenv("TIZA_BEDROCK_MODEL_ID", "mock-model")
    with sessions() as db:
        organization, classroom, teacher, _ = seed_demo(db)
        cycle = LearningCycle(organization_id=organization.id, classroom_id=classroom.id, objective="Equivalent fractions", concepts=["equivalence"], concept_confirmed=True, closes_at=datetime.now(timezone.utc) + timedelta(days=1), budget_minutes=10, state="preparing")
        db.add(cycle)
        db.flush()
        job = Job(organization_id=organization.id, kind="prepare_cycle", payload={"cycle_id": cycle.id, "actor_id": teacher.id, "cycle_version": 1}, state="running")
        db.add(job)
        db.flush()
        import pytest
        with pytest.raises(ValueError, match="policy-selected sequence"):
            runner.prepare_with_agent(db, job)

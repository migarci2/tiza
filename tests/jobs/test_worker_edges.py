from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from strands.models.model import Model

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


def _events(tool_calls=None):
    yield {"messageStart": {"role": "assistant"}}
    for index, (name, value) in enumerate(tool_calls or []):
        yield {"contentBlockStart": {"contentBlockIndex": index, "start": {"toolUse": {"toolUseId": str(index), "name": name}}}}
        yield {"contentBlockDelta": {"contentBlockIndex": index, "delta": {"toolUse": {"input": json.dumps(value)}}}}
        yield {"contentBlockStop": {"contentBlockIndex": index}}
    yield {"messageStop": {"stopReason": "tool_use" if tool_calls else "end_turn"}}
    yield {"metadata": {"usage": {"inputTokens": 4, "outputTokens": 2, "totalTokens": 6}, "metrics": {"latencyMs": 1}}}


class ControlledModel(Model):
    """A real Strands Model boundary with deterministic, offline model output."""
    def __init__(self, *, alter_items=False, repeat_reads=False, empty_selection=False):
        self.step = 0
        self.alter_items = alter_items
        self.repeat_reads = repeat_reads
        self.empty_selection = empty_selection

    def get_config(self):
        return {"model_id": "controlled"}

    def update_config(self, **kwargs):
        pass

    async def structured_output(self, *args, **kwargs):
        raise NotImplementedError

    async def stream(self, messages, tool_specs=None, system_prompt=None, **kwargs):
        self.step += 1
        if self.repeat_reads:
            for event in _events([("read_cycle_context", {})]):
                yield event
            return
        if self.step == 1:
            events = _events([("read_cycle_context", {}), ("select_validated_exercises", {})])
        elif self.step == 2:
            content = messages[-1]["content"][1]["toolResult"]["content"][0]
            result = content.get("json") or json.loads(content["text"])
            calls = []
            for row in result:
                ids = [item["id"] for item in row["items"]]
                calls.append(("save_assignment_draft", {"assignment_id": row["assignment_id"],
                    "item_ids": ids[:-1] if self.alter_items else ids, "reason": row["reason"],
                    "exercise_ids": [] if self.empty_selection else
                        [item["candidates"][0]["exercise_id"] for item in row["items"]]}))
            events = _events(calls)
        elif self.step == 3:
            events = _events([("request_teacher_review", {})])
        else:
            events = _events()
        for event in events:
            yield event


def test_real_strands_agent_can_only_save_the_policy_sequence(tmp_path, monkeypatch) -> None:
    sessions = _database(tmp_path, "agent.db")
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
        runner.prepare_with_agent(db, job, model=ControlledModel())
        assert job.payload["agent"]["model"] == "mock-model"
        assert job.payload["agent"]["tools"][-1] == "request_teacher_review"
        assert job.payload["agent"]["tool_events"][-1]["status"] == "completed"
        assert job.payload["agent"]["usage"]["totalTokens"] > 0
        assert db.scalar(select(func.count()).select_from(Assignment).where(Assignment.cycle_id == cycle.id)) == 8


def test_agent_rejects_a_model_that_drops_a_preapproved_branch(tmp_path, monkeypatch) -> None:
    sessions = _database(tmp_path, "agent-reject.db")
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
        with pytest.raises(runner.AgentRunError) as failure:
            runner.prepare_with_agent(db, job, model=ControlledModel(alter_items=True))
        assert any(event["status"] == "failed" for event in failure.value.trace["tool_events"])
        assert "request_teacher_review" not in failure.value.trace["tools"]


def test_agent_rejects_empty_selection_and_reports_only_allowed_model_calls(tmp_path, monkeypatch) -> None:
    sessions = _database(tmp_path, "agent-limits.db")
    monkeypatch.setattr(runner, "get_settings", lambda: SimpleNamespace(agent_mode="bedrock", demo_mode=False))
    monkeypatch.setenv("TIZA_BEDROCK_MODEL_ID", "mock-model")
    with sessions() as db:
        organization, classroom, teacher, _ = seed_demo(db)
        cycle = LearningCycle(organization_id=organization.id, classroom_id=classroom.id,
            objective="Equivalent fractions", concepts=["equivalence"], concept_confirmed=True,
            closes_at=datetime.now(timezone.utc) + timedelta(days=1), budget_minutes=10, state="preparing")
        db.add(cycle); db.flush()
        job = Job(organization_id=organization.id, kind="prepare_cycle",
            payload={"cycle_id": cycle.id, "actor_id": teacher.id, "cycle_version": 1}, state="running")
        db.add(job); db.commit()
        import pytest
        with pytest.raises(runner.AgentRunError) as empty:
            runner.prepare_with_agent(db, job, model=ControlledModel(empty_selection=True))
        assert any(event["status"] == "failed" for event in empty.value.trace["tool_events"])

        db.rollback()
        job = db.get(Job, job.id)
        with pytest.raises(runner.AgentRunError, match="budget exceeded") as over_budget:
            runner.prepare_with_agent(db, job, model=ControlledModel(repeat_reads=True))
        assert over_budget.value.trace["model_calls"] == 12

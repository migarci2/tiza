from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from tiza.db import Base
from tiza.models import Approval, Assignment, Delivery, Job, LearningCycle, OutboxEvent
from tiza.services import seed_demo
from tiza.jobs import worker


def test_replayed_outbox_and_preparation_do_not_duplicate_assignments(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///" + str(tmp_path / "jobs.db"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker, "SessionLocal", sessions)
    with sessions() as db:
        org, classroom, teacher, _ = seed_demo(db)
        cycle = LearningCycle(organization_id=org.id, classroom_id=classroom.id, objective="Equivalent fractions",
            concepts=["equivalence"], concept_confirmed=True, closes_at=worker.utcnow()+timedelta(days=2), budget_minutes=12, state="preparing")
        db.add(cycle)
        db.flush()
        job = Job(organization_id=org.id, kind="prepare_cycle", payload={"cycle_id":cycle.id,"actor_id":teacher.id,"cycle_version":1})
        db.add(job)
        db.flush()
        db.add(OutboxEvent(organization_id=org.id,kind="job.queued",payload={"job_id":job.id,"job_kind":job.kind}))
        db.commit()
        job_id, cycle_id = job.id, cycle.id
    worker.dispatch(inline=True)
    worker.run_job(job_id)
    worker.dispatch(inline=True)
    with sessions() as db:
        assert db.get(Job,job_id).state == "completed"
        assert db.get(Job,job_id).payload["agent"]["model_invoked"] is False
        assert db.scalar(select(func.count(Assignment.id)).where(Assignment.cycle_id==cycle_id)) == 8


def test_delivery_outside_window_is_uncertain_and_reminder_rechecks_completion(tmp_path, monkeypatch):
    engine = create_engine("sqlite:///"+str(tmp_path/"delivery.db"))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(worker,"SessionLocal",sessions)
    at=datetime(2026,9,10,12,tzinfo=timezone.utc)
    monkeypatch.setattr(worker,"utcnow",lambda:at)
    monkeypatch.setenv("TIZA_EMAIL_MODE","resend")
    def no_network(*a,**kw):
        raise AssertionError("Must not send or contact a provider")
    monkeypatch.setattr(worker.httpx,"post",no_network)
    with sessions() as db:
        org,classroom,teacher,learners=seed_demo(db)
        cycle=LearningCycle(organization_id=org.id,classroom_id=classroom.id,objective="Check",concepts=["equivalence"],concept_confirmed=True,closes_at=at+timedelta(hours=4),budget_minutes=12,state="active")
        db.add(cycle); db.flush()
        assignment=Assignment(cycle_id=cycle.id,learner_id=learners[0].id,version=1,reason="Check",estimated_minutes=2,published=True,state="not_started")
        db.add(assignment);db.flush()
        db.add(Approval(cycle_id=cycle.id,actor_id=teacher.id,version=1,batch_hash="test",recipient_ids=[learners[0].id],permissions=["publish","reminder"]))
        delivery=Delivery(assignment_id=assignment.id,recipient_id=learners[0].id,idempotency_key="test",first_attempt_at=at-timedelta(hours=25))
        db.add(delivery);db.flush()
        job=Job(organization_id=org.id,kind="delivery",payload={"delivery_id":delivery.id},state="running")
        db.add(job);db.commit()
        worker.deliver(db,job)
        assert delivery.state=="uncertain"
        worker.schedule_reminders(db);db.commit()
        reminders=list(db.scalars(select(Delivery).where(Delivery.channel=="reminder")))
        assert len(reminders)==1
        assignment.state="completed";db.commit()
        reminder_job=db.get(Job,"delivery-"+reminders[0].id)
        worker.deliver(db,reminder_job)
        assert reminders[0].state=="cancelled"

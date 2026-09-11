"""PostgreSQL owns intent and retries. Redis transports disposable notifications."""
from datetime import datetime, timedelta, timezone
import os
import smtplib
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from celery import Celery
import httpx
from sqlalchemy import select, update

from tiza.config import get_settings
from tiza.db import SessionLocal
from tiza.models import Approval, Assignment, AuditEvent, Delivery, Enrollment, Job, LearningCycle, Membership, Organization, OutboxEvent, User
from tiza.security import _aware
from .clock import organization_now

app = Celery("tiza", broker=get_settings().redis_url)
app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json",
                task_acks_late=True, task_reject_on_worker_lost=True, worker_prefetch_multiplier=1,
                task_soft_time_limit=600, task_time_limit=660,
                beat_schedule={"dispatch-persisted-work": {"task": "tiza.dispatch", "schedule": 5.0}})


def utcnow():
    return datetime.now(timezone.utc)


def dispatch(*, inline=False):
    """Replay-safe outbox publication, stale-job recovery and due work selection."""
    with SessionLocal() as db:
        for event in db.scalars(select(OutboxEvent).where(OutboxEvent.state == "pending").with_for_update(skip_locked=True).limit(100)):
            if event.kind == "delivery.queued":
                job_id = "delivery-" + event.payload["delivery_id"]
                if not db.get(Job, job_id):
                    db.add(Job(id=job_id, organization_id=event.organization_id, kind="delivery",
                               payload={"delivery_id": event.payload["delivery_id"]}))
            elif event.kind != "job.queued":
                continue
            event.state = "published"
        stale = list(db.scalars(select(Job).where(Job.state == "running", Job.started_at < utcnow() - timedelta(minutes=15))))
        for job in stale:
            job.state = "failed" if job.attempts >= 3 else "queued"
            job.last_error = "Worker lease expired"
            if job.state == "failed" and job.kind == "prepare_cycle":
                cycle = db.get(LearningCycle, job.payload["cycle_id"])
                if cycle and cycle.state == "preparing":
                    cycle.state = "failed"
        schedule_reminders(db)
        db.commit()
        ids = list(db.scalars(select(Job.id).where(Job.state == "queued", Job.available_at <= utcnow(), Job.attempts < 3).limit(100)))
    for job_id in ids:
        if inline:
            run_job(job_id)
        else:
            run_job.delay(job_id)


@app.task(name="tiza.dispatch")
def dispatch_task():
    dispatch()


@app.task(name="tiza.run_job")
def run_job(job_id: str):
    with SessionLocal() as db:
        claimed = db.execute(update(Job).where(Job.id == job_id, Job.state == "queued", Job.attempts < 3,
                                              Job.available_at <= utcnow())
                             .values(state="running", started_at=utcnow(), attempts=Job.attempts + 1))
        db.commit()
        if not claimed.rowcount:
            return
    try:
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if job.kind == "prepare_cycle":
                from tiza.agent.runner import prepare_with_agent
                prepare_with_agent(db, job)
            elif job.kind == "delivery":
                deliver(db, job)
            else:
                raise ValueError("Unknown persisted job type")
            if job.state == "running":
                job.state = "completed"
            db.commit()
    except Exception as exc:
        # Never log model input, learner responses, provider bodies or credentials.
        with SessionLocal() as db:
            job = db.get(Job, job_id)
            if not job:
                return
            job.last_error = type(exc).__name__
            job.state = "failed" if job.attempts >= 3 else "queued"
            job.available_at = utcnow() + timedelta(seconds=10 * job.attempts)
            if job.state == "failed" and job.kind == "prepare_cycle":
                cycle = db.get(LearningCycle, job.payload["cycle_id"])
                if cycle and cycle.state == "preparing":
                    cycle.state = "failed"
            db.commit()


def schedule_reminders(db):
    cycles = db.scalars(select(LearningCycle).where(LearningCycle.state == "active"))
    for cycle in cycles:
        at = organization_now(db, cycle.organization_id, base=utcnow())
        if _aware(cycle.closes_at) > at + timedelta(hours=6):
            continue
        if _aware(cycle.closes_at) <= at:
            cycle.state = "closed"
            continue
        approval = db.scalar(select(Approval).where(Approval.cycle_id == cycle.id, Approval.version == cycle.version))
        cancelled = db.scalar(select(AuditEvent.id).where(AuditEvent.object_id == cycle.id, AuditEvent.action == "reminders.cancelled"))
        if not approval or "reminder" not in approval.permissions or cancelled:
            continue
        for assignment in db.scalars(select(Assignment).where(Assignment.cycle_id == cycle.id, Assignment.published.is_(True), Assignment.excluded.is_(False))):
            if assignment.state in {"completed", "submitted", "review_needed"}:
                continue
            delivery_id = "reminder-" + assignment.id
            if db.get(Delivery, delivery_id):
                continue
            db.add(Delivery(id=delivery_id, assignment_id=assignment.id, recipient_id=assignment.learner_id,
                            channel="reminder", idempotency_key=delivery_id))
            db.add(Job(id="delivery-" + delivery_id, organization_id=cycle.organization_id,
                       kind="delivery", payload={"delivery_id": delivery_id}))


def deliver(db, job):
    delivery = db.scalar(select(Delivery).where(Delivery.id == job.payload["delivery_id"]).with_for_update())
    if not delivery or delivery.state in {"provider_accepted", "delivered", "bounced", "failed", "uncertain", "cancelled"}:
        return
    assignment = db.get(Assignment, delivery.assignment_id)
    cycle = db.get(LearningCycle, assignment.cycle_id)
    at = organization_now(db, cycle.organization_id, base=utcnow())
    approval = db.scalar(select(Approval).where(Approval.cycle_id == cycle.id, Approval.version == assignment.version))
    enrollment = db.scalar(select(Enrollment).where(Enrollment.classroom_id == cycle.classroom_id,
                                                   Enrollment.learner_id == delivery.recipient_id, Enrollment.status == "active"))
    teacher = db.scalar(select(Membership).where(Membership.organization_id == job.organization_id,
                                                Membership.user_id == approval.actor_id if approval else False,
                                                Membership.role.in_(["teacher", "owner"])))
    if (cycle.organization_id != job.organization_id or delivery.recipient_id != assignment.learner_id or not approval or not teacher or not enrollment
        or delivery.recipient_id not in approval.recipient_ids or not assignment.published or assignment.excluded
        or cycle.state != "active" or _aware(cycle.closes_at) <= at):
        delivery.state = "cancelled"
        return
    cancelled = db.scalar(select(AuditEvent.id).where(AuditEvent.object_id == cycle.id, AuditEvent.action == "reminders.cancelled"))
    if delivery.channel == "reminder" and (cancelled or "reminder" not in approval.permissions or assignment.state in {"completed", "submitted", "review_needed"}):
        delivery.state = "cancelled"
        return
    org = db.get(Organization, job.organization_id)
    local = at.astimezone(ZoneInfo(org.timezone))
    if not 8 <= local.hour < 21:
        job.state = "queued"
        job.attempts -= 1
        job.available_at = utcnow() + timedelta(minutes=30)
        return
    mode = os.environ.get("TIZA_EMAIL_MODE", "mailpit" if get_settings().demo_mode else "resend")
    if delivery.first_attempt_at and (mode != "resend" or utcnow() - _aware(delivery.first_attempt_at) >= timedelta(hours=23)):
        delivery.state = "uncertain"
        delivery.last_error = "Reconcile with provider before retrying outside safe idempotency window"
        return
    delivery.first_attempt_at = delivery.first_attempt_at or utcnow()
    delivery.attempted_at = utcnow()
    delivery.provider = mode
    # Persist send intent before the network call. A crash can never trigger a blind resend.
    db.commit()
    user = db.get(User, delivery.recipient_id)
    url = os.environ.get("TIZA_PUBLIC_URL", "http://localhost:5173").rstrip("/") + "/practice/" + assignment.id
    payload = {"from": os.environ.get("TIZA_EMAIL_FROM", "Tiza <practice@tiza.example>"), "to": [user.email],
               "subject": "Your practice is ready" if delivery.channel == "email" else "A practice reminder",
               "text": "Sign in to view your practice: " + url}
    try:
        if mode == "mailpit" and get_settings().demo_mode:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = payload["from"], user.email, payload["subject"]
            msg["Message-ID"] = "<" + delivery.id + "@tiza.example>"
            msg.set_content(payload["text"])
            with smtplib.SMTP(os.environ.get("TIZA_SMTP_HOST", "localhost"), int(os.environ.get("TIZA_SMTP_PORT", "1025")), timeout=10) as smtp:
                smtp.send_message(msg)
            delivery.provider_message_id = msg["Message-ID"]
        elif mode == "resend":
            key = os.environ.get("TIZA_RESEND_API_KEY")
            if not key:
                delivery.state, delivery.last_error = "failed", "Email provider is not configured"
                return
            response = httpx.post("https://api.resend.com/emails", json=payload,
                                  headers={"Authorization": "Bearer " + key, "Idempotency-Key": delivery.idempotency_key}, timeout=20)
            if response.status_code == 429 or response.status_code >= 500:
                raise httpx.TransportError("Provider temporary failure")
            if response.status_code >= 400:
                delivery.state, delivery.last_error = "failed", "Provider rejected request"
                return
            delivery.provider_message_id = response.json()["id"]
        else:
            delivery.state, delivery.last_error = "failed", "Unsupported email configuration"
            return
        delivery.state = "provider_accepted"
    except (httpx.TransportError, smtplib.SMTPException, OSError):
        if mode != "resend":
            delivery.state, delivery.last_error = "uncertain", "Local SMTP result uncertain; inspect Mailpit"
        else:
            delivery.last_error = "Provider result uncertain; bounded retry with same idempotency key"
            job.state = "queued" if job.attempts < 3 else "failed"
            job.available_at = utcnow() + timedelta(seconds=30)
            if job.state == "failed":
                delivery.state = "uncertain"


if __name__ == "__main__":
    import time
    # ponytail: one local process; use Celery + Redis for deployment and concurrent workloads.
    while True:
        dispatch(inline=True)
        time.sleep(2)

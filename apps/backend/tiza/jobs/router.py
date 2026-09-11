from datetime import timedelta
import os

from fastapi import APIRouter, Depends, HTTPException
import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from tiza.db import get_db
from tiza.models import Approval, Assignment, AuditEvent, Classroom, Delivery, Job, LearningCycle, Organization
from tiza.security import Principal, require_teacher
from .clock import organization_now

router = APIRouter(prefix="/api")


class AdvanceClock(BaseModel):
    hours: int = Field(ge=1, le=72)


@router.post("/demo/clock/advance")
def advance_clock(body: AdvanceClock, principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)):
    org = db.scalar(select(Organization).where(Organization.id == principal.membership.organization_id).with_for_update())
    if not org or not org.demo or not principal.user.synthetic:
        raise HTTPException(404, "Demo clock unavailable")
    org.demo_offset_seconds += body.hours * 3600
    db.add(AuditEvent(organization_id=org.id, actor_id=principal.user.id, action="demo.clock_advanced", object_type="organization", object_id=org.id))
    db.commit()
    return {"demo_now": organization_now(db, org.id), "simulated": True}


def authorized_cycle(db, principal, cycle_id):
    cycle = db.get(LearningCycle, cycle_id)
    classroom = db.get(Classroom, cycle.classroom_id) if cycle else None
    if not cycle or cycle.organization_id != principal.membership.organization_id or classroom.teacher_id != principal.user.id:
        raise HTTPException(404, "Cycle not found")
    return cycle


@router.get("/cycles/{cycle_id}/deliveries")
def deliveries(cycle_id: str, principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)):
    authorized_cycle(db, principal, cycle_id)
    rows = db.scalars(select(Delivery).join(Assignment).where(Assignment.cycle_id == cycle_id))
    return [{"id": d.id, "assignment_id": d.assignment_id, "channel": d.channel, "provider": d.provider,
             "state": d.state, "last_error": d.last_error} for d in rows]


@router.post("/cycles/{cycle_id}/cancel-reminders")
def cancel_reminders(cycle_id: str, principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)):
    cycle = authorized_cycle(db, principal, cycle_id)
    # Approval is immutable. Cancellation is a separate authorization revocation event.
    existing = db.scalar(select(AuditEvent).where(AuditEvent.object_id == cycle.id, AuditEvent.action == "reminders.cancelled"))
    if not existing:
        db.add(AuditEvent(organization_id=cycle.organization_id, actor_id=principal.user.id, action="reminders.cancelled", object_type="cycle", object_id=cycle.id))
    for delivery in db.scalars(select(Delivery).join(Assignment).where(Assignment.cycle_id == cycle.id, Delivery.channel == "reminder", Delivery.state == "queued")):
        delivery.state = "cancelled"
    db.commit()
    return {"cancelled": True}


@router.post("/deliveries/{delivery_id}/reconcile")
def reconcile(delivery_id: str, principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)):
    delivery = db.get(Delivery, delivery_id)
    assignment = db.get(Assignment, delivery.assignment_id) if delivery else None
    if not assignment:
        raise HTTPException(404, "Delivery not found")
    authorized_cycle(db, principal, assignment.cycle_id)
    key = os.environ.get("TIZA_RESEND_API_KEY")
    if delivery.provider != "resend" or not delivery.provider_message_id or not key:
        raise HTTPException(409, "No provider message ID available; inspect provider records before any retry")
    response = httpx.get("https://api.resend.com/emails/" + delivery.provider_message_id,
                         headers={"Authorization": "Bearer " + key}, timeout=15)
    if response.status_code != 200:
        raise HTTPException(502, "Provider reconciliation is unavailable")
    event = response.json().get("last_event")
    state = {"delivered": "delivered", "bounced": "bounced", "failed": "failed", "sent": "provider_accepted"}.get(event)
    if state:
        delivery.state = state
        db.commit()
    return {"id": delivery.id, "state": delivery.state}

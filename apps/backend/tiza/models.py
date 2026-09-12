from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String)
    timezone: Mapped[str] = mapped_column(String, default="Europe/Madrid")
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    demo_offset_seconds: Mapped[int] = mapped_column(Integer, default=0)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    auth_subject: Mapped[str] = mapped_column(String, unique=True)
    email: Mapped[str] = mapped_column(String)
    display_name: Mapped[str] = mapped_column(String)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("organization_id", "user_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    role: Mapped[str] = mapped_column(String)


class Classroom(Base):
    __tablename__ = "classrooms"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    teacher_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String, default="en")
    practice_minutes: Mapped[int] = mapped_column(Integer, default=15)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("classroom_id", "learner_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="active")


class Invitation(Base):
    __tablename__ = "invitations"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"))
    email: Mapped[str] = mapped_column(String)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    accepted_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"))


class LearningCycle(Base):
    __tablename__ = "learning_cycles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    classroom_id: Mapped[str] = mapped_column(ForeignKey("classrooms.id"), index=True)
    objective: Mapped[str] = mapped_column(Text)
    concepts: Mapped[list] = mapped_column(JSON, default=list)
    concept_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    closes_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    budget_minutes: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String, default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("learning_cycles.id"), index=True)
    filename: Mapped[str] = mapped_column(String)
    content_type: Mapped[str] = mapped_column(String)
    object_path: Mapped[str] = mapped_column(String)
    sha256: Mapped[str] = mapped_column(String)
    extracted_text: Mapped[str] = mapped_column(Text)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String, default="ready")


class ExerciseVersion(Base):
    __tablename__ = "exercise_versions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    concept_id: Mapped[str] = mapped_column(String, index=True)
    kind: Mapped[str] = mapped_column(String)
    prompt: Mapped[str] = mapped_column(Text)
    options: Mapped[list | None] = mapped_column(JSON)
    answer: Mapped[str | None] = mapped_column(String)
    explanation: Mapped[str] = mapped_column(Text)
    hint: Mapped[str | None] = mapped_column(Text)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=3)
    source: Mapped[str] = mapped_column(String, default="Tiza reviewed fractions bank")
    approved: Mapped[bool] = mapped_column(Boolean, default=True)


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("cycle_id", "learner_id", "version"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("learning_cycles.id"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String, default="not_started")
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    excluded: Mapped[bool] = mapped_column(Boolean, default=False)
    items: Mapped[list[AssignmentItem]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", order_by="AssignmentItem.position"
    )


class AssignmentItem(Base):
    __tablename__ = "assignment_items"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercise_versions.id"))
    position: Mapped[int] = mapped_column(Integer)
    branch_after_item_id: Mapped[str | None] = mapped_column(String)
    branch_on: Mapped[str | None] = mapped_column(String)
    assignment: Mapped[Assignment] = relationship(back_populates="items")
    exercise: Mapped[ExerciseVersion] = relationship()


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("cycle_id", "version"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("learning_cycles.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer)
    batch_hash: Mapped[str] = mapped_column(String)
    recipient_ids: Mapped[list] = mapped_column(JSON)
    permissions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Attempt(Base):
    __tablename__ = "attempts"
    __table_args__ = (
        UniqueConstraint("assignment_id", "client_key"),
        UniqueConstraint("assignment_id", "item_id"),
    )
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("assignment_items.id"))
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    client_key: Mapped[str] = mapped_column(String)
    response: Mapped[str] = mapped_column(Text)
    used_hint: Mapped[bool] = mapped_column(Boolean, default=False)
    result: Mapped[str] = mapped_column(String)
    score: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    verifier_version: Mapped[str] = mapped_column(String, default="fractions-v1")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AssistanceEvent(Base):
    __tablename__ = "assistance_events"
    __table_args__ = (UniqueConstraint("assignment_id", "item_id", "learner_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"), index=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("assignment_items.id"))
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String, default="hint")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EvidenceEvent(Base):
    __tablename__ = "evidence_events"
    __table_args__ = (UniqueConstraint("attempt_id", "revision"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    concept_id: Mapped[str] = mapped_column(String, index=True)
    attempt_id: Mapped[str] = mapped_column(ForeignKey("attempts.id"))
    outcome: Mapped[str] = mapped_column(String)
    evaluator: Mapped[str] = mapped_column(String)
    used_hint: Mapped[bool] = mapped_column(Boolean)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("evidence_events.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Delivery(Base):
    __tablename__ = "deliveries"
    __table_args__ = (UniqueConstraint("assignment_id", "channel"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    assignment_id: Mapped[str] = mapped_column(ForeignKey("assignments.id"))
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    channel: Mapped[str] = mapped_column(String, default="email")
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    provider: Mapped[str] = mapped_column(String, default="resend")
    provider_message_id: Mapped[str | None] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default="queued")
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class UsageBucket(Base):
    __tablename__ = "usage_buckets"
    key: Mapped[str] = mapped_column(String, primary_key=True)
    used: Mapped[int] = mapped_column(Integer, default=0)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String)
    object_type: Mapped[str] = mapped_column(String)
    object_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("organization_id", "actor_id", "route", "key"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    route: Mapped[str] = mapped_column(String)
    key: Mapped[str] = mapped_column(String)
    response: Mapped[dict] = mapped_column(JSON)
    status_code: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class WebSession(Base):
    __tablename__ = "web_sessions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String, unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    acting_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

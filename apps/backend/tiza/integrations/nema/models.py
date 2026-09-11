from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ...db import Base
from ...models import now, uid


class NemaReadinessRequest(Base):
    __tablename__ = "nema_readiness_requests"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("learning_cycles.id"), index=True)
    request_hash: Mapped[str] = mapped_column(String, index=True)
    request_json: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class NemaGrant(Base):
    __tablename__ = "nema_grants"
    __table_args__ = (UniqueConstraint("request_id"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("nema_readiness_requests.id"))
    learner_key_id: Mapped[str] = mapped_column(String, index=True)
    vault_key: Mapped[dict] = mapped_column(JSON)
    scope: Mapped[list] = mapped_column(JSON)
    assertions: Mapped[list] = mapped_column(JSON)
    purpose: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

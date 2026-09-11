from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .db import get_db
from .models import Membership, User, WebSession


COOKIE = "tiza_session"


def digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


def csrf_for_session_token(token: str) -> str:
    return digest(f"{token}:csrf")


@dataclass(frozen=True)
class Principal:
    actor: User
    user: User
    membership: Membership
    session: WebSession
    csrf_token: str | None = None


def create_session(db: Session, user: User, acting_user: User | None = None) -> tuple[WebSession, str, str]:
    token = secrets.token_urlsafe(32)
    csrf = csrf_for_session_token(token)
    session = WebSession(
        token_hash=digest(token),
        csrf_hash=digest(csrf),
        user_id=user.id,
        acting_user_id=acting_user.id if acting_user else None,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=get_settings().session_ttl_hours),
    )
    db.add(session)
    db.flush()
    return session, token, csrf


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def require_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    raw = request.cookies.get(COOKIE)
    session = db.scalar(select(WebSession).where(WebSession.token_hash == digest(raw or "")))
    if not session or _aware(session.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(401, "Sign in required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf = request.headers.get("X-CSRF-Token", "")
        if not secrets.compare_digest(session.csrf_hash, digest(csrf)):
            raise HTTPException(403, "Missing or invalid CSRF token")
    actor = db.get(User, session.user_id)
    user = db.get(User, session.acting_user_id or session.user_id)
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if not actor or not user or not membership:
        raise HTTPException(401, "Session identity is no longer active")
    return Principal(actor, user, membership, session)


def set_session_cookie(response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        secure=settings.session_secure,
        samesite="strict",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def require_teacher(principal: Principal = Depends(require_principal)) -> Principal:
    if principal.membership.role not in {"teacher", "owner"}:
        raise HTTPException(403, "Teacher access required")
    return principal

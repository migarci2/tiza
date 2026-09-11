from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import models
from .integrations.nema import models as nema_models  # noqa: F401
from .integrations.nema.router import router as nema_router
from .jobs.router import router as jobs_router
from .jobs.clock import organization_now
from .config import get_settings
from .db import Base, SessionLocal, engine, get_db
from .models import (
    Approval,
    Assignment,
    AssignmentItem,
    AssistanceEvent,
    Attempt,
    AuditEvent,
    Classroom,
    Delivery,
    Enrollment,
    EvidenceEvent,
    ExerciseVersion,
    Invitation,
    IdempotencyRecord,
    Job,
    LearningCycle,
    Material,
    Membership,
    Organization,
    OutboxEvent,
    User,
    WebSession,
)
from .schemas import (
    ApproveRequest,
    AttemptCreate,
    ClassroomCreate,
    ConceptConfirm,
    CycleCreate,
    CycleUpdate,
    DemoAccess,
    DemoSwitch,
    DraftUpdate,
    InvitationCreate,
    PublishRequest,
    RequestCode,
    ReviewCreate,
    VerifyCode,
    WorkspaceUpdate,
)
from .security import COOKIE, Principal, _aware, create_session, csrf_for_session_token, digest, require_principal, require_teacher, set_session_cookie
from .services import (
    CONCEPTS,
    allowed_concepts,
    assignment_batch_hash,
    brief_json,
    classroom_json,
    concept_candidates,
    cycle_json,
    draft_json,
    exercise_json,
    grade,
    refresh_assignment_state,
    seed_demo,
    store_material,
    user_json,
    visible_items,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if get_settings().demo_mode:
        Base.metadata.create_all(engine)
        with SessionLocal() as db:
            seed_demo(db)
    yield


app = FastAPI(title="Tiza API", version="0.1.0", lifespan=lifespan)
app.include_router(nema_router)
app.include_router(jobs_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-CSRF-Token", "Idempotency-Key"],
)


def _role_for(db: Session, user: User) -> Membership:
    membership = db.scalar(select(Membership).where(Membership.user_id == user.id))
    if not membership:
        raise HTTPException(403, "No active organization membership")
    return membership


def _session_json(db: Session, actor: User, effective: User, csrf: str | None = None) -> dict:
    membership = _role_for(db, effective)
    organization = db.get(Organization, membership.organization_id)
    classroom = (
        db.scalar(
            select(Classroom).where(
                Classroom.organization_id == organization.id, Classroom.teacher_id == effective.id
            )
        )
        if membership.role in {"teacher", "owner"}
        else db.scalar(
            select(Classroom)
            .join(Enrollment)
            .where(Enrollment.learner_id == effective.id, Enrollment.status == "active")
        )
    )
    learners = []
    if organization.demo and classroom:
        learners = [
            user_json(user)
            for user in db.scalars(
                select(User)
                .join(Enrollment, Enrollment.learner_id == User.id)
                .where(Enrollment.classroom_id == classroom.id)
                .order_by(User.display_name)
            )
        ]
    return {
        "csrf_token": csrf,
        "actor": user_json(actor),
        "effective_user": user_json(effective),
        "role": membership.role,
        "demo": organization.demo,
        "timezone": organization.timezone,
        "demo_now": datetime.now(timezone.utc) + timedelta(seconds=organization.demo_offset_seconds),
        "agent_mode": get_settings().agent_mode,
        "classroom_id": classroom.id if classroom else None,
        "learners": learners,
    }


def _teacher_classroom(db: Session, principal: Principal, classroom_id: str) -> Classroom:
    classroom = db.get(Classroom, classroom_id)
    if (
        not classroom
        or classroom.organization_id != principal.membership.organization_id
        or classroom.teacher_id != principal.user.id
    ):
        raise HTTPException(404, "Classroom not found")
    return classroom


def _teacher_cycle(db: Session, principal: Principal, cycle_id: str) -> LearningCycle:
    cycle = db.get(LearningCycle, cycle_id)
    classroom = db.get(Classroom, cycle.classroom_id) if cycle else None
    if (
        not cycle
        or cycle.organization_id != principal.membership.organization_id
        or not classroom
        or classroom.teacher_id != principal.user.id
    ):
        raise HTTPException(404, "Cycle not found")
    return cycle


def _provision_verified_identity(
    db: Session, remote: dict, invite_token: str | None = None
) -> User:
    subject, email = remote.get("id"), remote.get("email")
    if not subject or not email:
        raise HTTPException(401, "The identity provider returned an incomplete identity")
    user = db.scalar(select(User).where(User.auth_subject == subject))
    invitation = None
    if invite_token:
        invitation = db.scalar(
            select(Invitation)
            .where(Invitation.token_hash == digest(invite_token))
            .with_for_update()
        )
        if (
            not invitation
            or invitation.accepted_by is not None
            or invitation.email.lower() != email.lower()
            or _aware(invitation.expires_at) <= datetime.now(timezone.utc)
        ):
            raise HTTPException(403, "The classroom invitation is invalid, expired, or already used")
    memberships = list(db.scalars(select(Membership).where(Membership.user_id == user.id))) if user else []
    if not invitation and not memberships:
        pending = db.scalar(
            select(Invitation.id)
            .where(
                func.lower(Invitation.email) == email.lower(),
                Invitation.accepted_by.is_(None),
                Invitation.expires_at > datetime.now(timezone.utc),
            )
            .limit(1)
        )
        if pending:
            raise HTTPException(403, "Use the one-time classroom invitation sent to this email")
    if not user:
        user = User(
            auth_subject=subject,
            email=email,
            display_name=(remote.get("user_metadata") or {}).get("full_name") or email.split("@", 1)[0],
        )
        db.add(user)
        db.flush()
    if invitation:
        classroom = db.get(Classroom, invitation.classroom_id)
        if any(membership.organization_id != classroom.organization_id for membership in memberships):
            raise HTTPException(409, "This identity already belongs to a different organization")
        if any(membership.role in {"teacher", "owner"} for membership in memberships):
            raise HTTPException(409, "A teacher identity cannot be converted into a learner")
        if not memberships:
            db.add(Membership(organization_id=classroom.organization_id, user_id=user.id, role="learner"))
        enrollment = db.scalar(
            select(Enrollment).where(
                Enrollment.classroom_id == classroom.id, Enrollment.learner_id == user.id
            )
        )
        if enrollment:
            enrollment.status = "active"
        else:
            db.add(Enrollment(classroom_id=classroom.id, learner_id=user.id))
        invitation.accepted_by = user.id
    elif not memberships:
        organization = Organization(name=f"{user.display_name}'s workspace")
        db.add(organization)
        db.flush()
        db.add(Membership(organization_id=organization.id, user_id=user.id, role="teacher"))
        db.add(
            Classroom(
                organization_id=organization.id,
                teacher_id=user.id,
                title="My class",
                language="en",
                practice_minutes=15,
            )
        )
    return user


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/config")
def public_config() -> dict:
    settings = get_settings()
    return {"demo_mode": settings.demo_mode, "agent_mode": settings.agent_mode}


@app.post("/api/demo/session", status_code=410)
def demo_session_disabled() -> None:
    """Retained temporarily so older clients fail explicitly instead of gaining a session."""
    raise HTTPException(410, "Enter a demo code to open the workspace")


@app.post("/api/auth/demo-code")
def demo_code(body: DemoAccess, response: Response, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if not settings.demo_mode:
        raise HTTPException(404, "Demo access is unavailable")
    if not secrets.compare_digest(body.code.encode(), settings.demo_access_code.encode()):
        raise HTTPException(401, "Invalid demo code")
    _, _, user, _ = seed_demo(db)
    _, token, csrf = create_session(db, user)
    db.commit()
    set_session_cookie(response, token)
    return _session_json(db, user, user, csrf)


@app.get("/api/session")
def session_info(
    request: Request,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict:
    return _session_json(
        db, principal.actor, principal.user, csrf_for_session_token(request.cookies[COOKIE])
    )


@app.post("/api/demo/switch")
def demo_switch(
    body: DemoSwitch,
    request: Request,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict:
    actor_membership = _role_for(db, principal.actor)
    organization = db.get(Organization, actor_membership.organization_id)
    if not organization.demo or actor_membership.role != "teacher":
        raise HTTPException(403, "Demo switching is only available to the synthetic teacher")
    target = db.get(User, body.user_id)
    target_membership = _role_for(db, target) if target else None
    if not target or not target.synthetic or target_membership.organization_id != organization.id:
        raise HTTPException(404, "Synthetic demo identity not found")
    principal.session.acting_user_id = None if target.id == principal.actor.id else target.id
    csrf = csrf_for_session_token(request.cookies[COOKIE])
    principal.session.csrf_hash = digest(csrf)
    db.commit()
    return _session_json(db, principal.actor, target, csrf)


@app.post("/api/demo/reset")
def demo_reset(
    request: Request,
    principal: Principal = Depends(require_principal), db: Session = Depends(get_db)
) -> dict:
    actor_membership = _role_for(db, principal.actor)
    organization = db.get(Organization, actor_membership.organization_id)
    if not organization.demo or actor_membership.role != "teacher":
        raise HTTPException(403, "Demo reset is only available to the synthetic teacher")
    _, _, teacher, _ = seed_demo(db, reset_cycles=True)
    principal.session.acting_user_id = None
    csrf = csrf_for_session_token(request.cookies[COOKIE])
    principal.session.csrf_hash = digest(csrf)
    db.commit()
    return _session_json(db, teacher, teacher, csrf)


@app.post("/api/auth/request-code")
async def request_code(body: RequestCode) -> dict:
    settings = get_settings()
    if settings.demo_mode:
        raise HTTPException(400, "Enter a demo code; email is not required")
    async with httpx.AsyncClient(timeout=10) as client:
        result = await client.post(
            f"{settings.supabase_url}/auth/v1/otp",
            headers={"apikey": settings.supabase_anon_key},
            json={"email": body.email, "create_user": True},
        )
    if result.status_code >= 400:
        raise HTTPException(400, "The access code could not be sent")
    return {"sent": True, "mode": "email"}


@app.post("/api/auth/verify-code")
async def verify_code(body: VerifyCode, response: Response, db: Session = Depends(get_db)) -> dict:
    settings = get_settings()
    if settings.demo_mode:
        raise HTTPException(400, "Enter a demo code; email is not required")
    else:
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.post(
                f"{settings.supabase_url}/auth/v1/verify",
                headers={"apikey": settings.supabase_anon_key},
                json={"email": body.email, "token": body.code, "type": "email"},
            )
        if result.status_code >= 400:
            raise HTTPException(401, "Invalid or expired access code")
        remote = result.json().get("user") or {}
        user = _provision_verified_identity(db, remote, body.invite_token)
    _, token, csrf = create_session(db, user)
    db.commit()
    set_session_cookie(response, token)
    return _session_json(db, user, user, csrf)


@app.post("/api/auth/logout", status_code=204)
def logout(
    response: Response,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> None:
    db.delete(principal.session)
    db.commit()
    response.delete_cookie(COOKIE, path="/")


@app.get("/api/dashboard")
def dashboard(principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)) -> dict:
    classroom = db.scalar(
        select(Classroom).where(
            Classroom.organization_id == principal.membership.organization_id,
            Classroom.teacher_id == principal.user.id,
        )
    )
    cycles = list(
        db.scalars(
            select(LearningCycle)
            .where(
                LearningCycle.organization_id == principal.membership.organization_id,
                LearningCycle.classroom_id == (classroom.id if classroom else ""),
                LearningCycle.objective.not_like("Baseline fraction check%"),
            )
            .order_by(LearningCycle.created_at.desc())
        )
    )
    pending = [cycle for cycle in cycles if cycle.state == "review_ready"]
    decisions = [
        {"kind": "approval", "label": "Review practice", "cycle_id": cycle.id} for cycle in pending
    ]
    return {
        "classroom": classroom_json(classroom) if classroom else None,
        "active_cycle": cycle_json(cycles[0]) if cycles else None,
        "pending_approval": [cycle_json(cycle) for cycle in pending],
        "decisions": decisions,
    }


@app.get("/api/workspace")
def workspace(
    principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)
) -> dict:
    organization = db.get(Organization, principal.membership.organization_id)
    return {"id": organization.id, "name": organization.name, "timezone": organization.timezone}


@app.patch("/api/workspace")
def update_workspace(
    body: WorkspaceUpdate,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(422, "Use a valid IANA timezone such as Europe/Madrid") from exc
    organization = db.get(Organization, principal.membership.organization_id)
    organization.timezone = body.timezone
    db.commit()
    return {"id": organization.id, "name": organization.name, "timezone": organization.timezone}


@app.get("/api/classrooms")
def classrooms(principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)) -> list[dict]:
    return [
        classroom_json(c)
        for c in db.scalars(
            select(Classroom).where(
                Classroom.organization_id == principal.membership.organization_id,
                Classroom.teacher_id == principal.user.id,
            )
        )
    ]


@app.get("/api/exercises/catalog")
def exercise_catalog(
    principal: Principal = Depends(require_teacher), db: Session = Depends(get_db)
) -> list[dict]:
    exercises = db.scalars(
        select(ExerciseVersion)
        .where(ExerciseVersion.approved.is_(True))
        .order_by(ExerciseVersion.concept_id, ExerciseVersion.kind)
    )
    return [
        {
            **exercise_json(exercise, revealed=True),
            "answer": exercise.answer,
            "hint": exercise.hint,
        }
        for exercise in exercises
    ]


@app.post("/api/classrooms")
def create_classroom(
    body: ClassroomCreate,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    classroom = Classroom(
        organization_id=principal.membership.organization_id,
        teacher_id=principal.user.id,
        **body.model_dump(),
    )
    db.add(classroom)
    db.commit()
    return classroom_json(classroom)


@app.get("/api/classrooms/{classroom_id}")
def classroom_detail(
    classroom_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    classroom = _teacher_classroom(db, principal, classroom_id)
    learners = list(
        db.scalars(select(User).join(Enrollment).where(Enrollment.classroom_id == classroom.id))
    )
    cycles = list(
        db.scalars(
            select(LearningCycle)
            .where(
                LearningCycle.classroom_id == classroom.id,
                LearningCycle.objective.not_like("Baseline fraction check%"),
            )
            .order_by(LearningCycle.created_at.desc())
        )
    )
    return {
        **classroom_json(classroom),
        "learners": [user_json(user) for user in learners],
        "cycles": [cycle_json(cycle) for cycle in cycles],
    }


@app.post("/api/classrooms/{classroom_id}/invitations")
def invite(
    classroom_id: str,
    body: InvitationCreate,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    classroom = _teacher_classroom(db, principal, classroom_id)
    if "@" not in body.email:
        raise HTTPException(422, "Enter a valid email address")
    if db.scalar(
        select(Invitation.id)
        .where(
            Invitation.classroom_id == classroom.id,
            func.lower(Invitation.email) == body.email.lower(),
            Invitation.accepted_by.is_(None),
            Invitation.expires_at > datetime.now(timezone.utc),
        )
        .limit(1)
    ):
        raise HTTPException(409, "An active invitation already exists for this email")
    raw = secrets.token_urlsafe(24)
    invitation = Invitation(
        classroom_id=classroom.id,
        email=body.email,
        token_hash=digest(raw),
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    db.add(invitation)
    db.commit()
    return {"id": invitation.id, "email": invitation.email, "expires_at": invitation.expires_at, "invite_token": raw}


@app.post("/api/cycles")
def create_cycle(
    body: CycleCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    if idempotency_key:
        existing = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.organization_id == principal.membership.organization_id,
                IdempotencyRecord.actor_id == principal.user.id,
                IdempotencyRecord.route == "POST /api/cycles",
                IdempotencyRecord.key == idempotency_key,
            )
        )
        if existing:
            return existing.response
    classroom = _teacher_classroom(db, principal, body.classroom_id)
    if body.closes_at <= organization_now(db, principal.membership.organization_id):
        raise HTTPException(422, "The closing date must be in the future")
    valid = {item[0] for item in CONCEPTS}
    if any(concept not in valid for concept in body.concepts):
        raise HTTPException(422, "The cycle includes an unknown concept")
    cycle = LearningCycle(
        organization_id=classroom.organization_id,
        **body.model_dump(),
    )
    db.add(cycle)
    db.flush()
    result = jsonable_encoder(cycle_json(cycle))
    if idempotency_key:
        db.add(
            IdempotencyRecord(
                organization_id=principal.membership.organization_id,
                actor_id=principal.user.id,
                route="POST /api/cycles",
                key=idempotency_key,
                response=result,
                status_code=200,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        if not idempotency_key:
            raise
        existing = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.organization_id == principal.membership.organization_id,
                IdempotencyRecord.actor_id == principal.user.id,
                IdempotencyRecord.route == "POST /api/cycles",
                IdempotencyRecord.key == idempotency_key,
            )
        )
        if not existing:
            raise
        return existing.response
    return result


@app.post("/api/cycles/{cycle_id}/materials")
async def upload_material(
    cycle_id: str,
    file: UploadFile = File(...),
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    if cycle.state not in {"draft", "failed"}:
        raise HTTPException(409, "Materials cannot be changed after preparation starts")
    raw = await file.read(10 * 1024 * 1024 + 1)
    material = store_material(db, cycle, file.filename or "material", file.content_type or "application/octet-stream", raw)
    db.flush()
    candidates = concept_candidates(material.extracted_text + " " + cycle.objective, material.id)
    db.commit()
    return {
        "id": material.id,
        "filename": material.filename,
        "sha256": material.sha256,
        "page_count": material.page_count,
        "status": material.status,
        "excerpt": material.extracted_text[:300],
        "concept_candidates": candidates,
    }


@app.get("/api/materials/{material_id}")
def download_material(
    material_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> Response:
    material = db.get(Material, material_id)
    if not material:
        raise HTTPException(404, "Material not found")
    _teacher_cycle(db, principal, material.cycle_id)
    settings = get_settings()
    if settings.demo_mode:
        try:
            content = Path(material.object_path).read_bytes()
        except OSError as exc:
            raise HTTPException(404, "Stored material is unavailable") from exc
    else:
        upstream = httpx.get(
            f"{settings.supabase_url}/storage/v1/object/authenticated/{settings.supabase_material_bucket}/{material.object_path}",
            headers={
                "apikey": settings.supabase_service_key,
                "authorization": f"Bearer {settings.supabase_service_key}",
            },
            timeout=30,
        )
        if upstream.status_code != 200:
            raise HTTPException(502, "The private material could not be retrieved")
        content = upstream.content
    return Response(
        content,
        media_type=material.content_type,
        headers={"Content-Disposition": f'attachment; filename="{Path(material.filename).name}"'},
    )


@app.post("/api/cycles/{cycle_id}/concepts")
def confirm_concepts(
    cycle_id: str,
    body: ConceptConfirm,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    if cycle.state not in {"draft", "failed"}:
        raise HTTPException(409, "Concepts cannot be changed after preparation starts")
    valid = {item[0] for item in CONCEPTS}
    if any(concept not in valid for concept in body.concept_ids):
        raise HTTPException(422, "The selection includes an unknown concept")
    cycle.concepts = list(dict.fromkeys(body.concept_ids))
    cycle.concept_confirmed = True
    db.commit()
    return cycle_json(cycle)


@app.post("/api/cycles/{cycle_id}/prepare", status_code=202)
def queue_prepare(
    cycle_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    if not cycle.concept_confirmed:
        raise HTTPException(409, "Confirm the concept match before preparing practice")
    if cycle.state == "preparing":
        existing = next(
            (
                job
                for job in db.scalars(
                    select(Job).where(Job.organization_id == cycle.organization_id, Job.kind == "prepare_cycle")
                )
                if job.payload.get("cycle_id") == cycle.id
            ),
            None,
        )
        if not existing:
            raise HTTPException(409, "Preparation is already in progress")
        return {"job_id": existing.id, "state": existing.state, "cycle_state": cycle.state}
    if cycle.state not in {"draft", "failed"}:
        raise HTTPException(409, "This cycle has already been prepared")
    cycle.state = "preparing"
    job = Job(
        organization_id=cycle.organization_id,
        kind="prepare_cycle",
        payload={"cycle_id": cycle.id, "actor_id": principal.user.id, "cycle_version": cycle.version},
    )
    db.add(job)
    db.flush()
    db.add(
        OutboxEvent(
            organization_id=cycle.organization_id,
            kind="job.queued",
            payload={"job_id": job.id, "job_kind": job.kind},
        )
    )
    db.commit()
    return {"job_id": job.id, "state": job.state, "cycle_state": cycle.state}


@app.get("/api/cycles/{cycle_id}/draft")
def get_draft(
    cycle_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    if cycle.state == "preparing":
        raise HTTPException(409, "Practice is still being prepared")
    if cycle.state not in {"review_ready", "approved", "active", "closed"}:
        raise HTTPException(409, "No practice draft is available")
    return draft_json(db, cycle)


@app.patch("/api/cycles/{cycle_id}/draft")
def update_draft(
    cycle_id: str,
    body: DraftUpdate,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    if cycle.state not in {"review_ready", "approved"} or body.version != cycle.version:
        raise HTTPException(409, "Only a review-ready draft can be edited")
    current = list(db.scalars(select(Assignment).where(Assignment.cycle_id == cycle.id, Assignment.version == cycle.version)))
    changes = {change.id: change for change in body.assignments}
    if set(changes) - {assignment.id for assignment in current}:
        raise HTTPException(422, "A changed assignment is not in this draft")
    valid_exercises = {exercise.id: exercise for exercise in db.scalars(select(ExerciseVersion).where(ExerciseVersion.approved.is_(True)))}
    allowed = allowed_concepts(cycle.concepts)
    changed = any(
        (change.excluded is not None and change.excluded != assignment.excluded)
        or (change.exercise_ids is not None and change.exercise_ids != [item.exercise_id for item in assignment.items])
        for assignment in current
        if (change := changes.get(assignment.id))
    )
    if not changed:
        return draft_json(db, cycle)
    cycle.version += 1
    cycle.state = "review_ready"
    for old in current:
        change = changes.get(old.id)
        exercise_ids = change.exercise_ids if change and change.exercise_ids is not None else [item.exercise_id for item in old.items]
        if (
            not exercise_ids
            or len(exercise_ids) != len(set(exercise_ids))
            or any(exercise_id not in valid_exercises for exercise_id in exercise_ids)
            or any(valid_exercises[exercise_id].concept_id not in allowed for exercise_id in exercise_ids)
            or sum(valid_exercises[exercise_id].estimated_minutes for exercise_id in exercise_ids) > cycle.budget_minutes
        ):
            raise HTTPException(422, "Draft items must use approved exercises")
        replacement = Assignment(
            cycle_id=cycle.id,
            learner_id=old.learner_id,
            version=cycle.version,
            reason=old.reason,
            estimated_minutes=sum(valid_exercises[item].estimated_minutes for item in exercise_ids),
            excluded=change.excluded if change and change.excluded is not None else old.excluded,
        )
        db.add(replacement)
        db.flush()
        same_sequence = exercise_ids == [item.exercise_id for item in old.items]
        item_map = {}
        for position, exercise_id in enumerate(exercise_ids, 1):
            old_item = old.items[position - 1] if same_sequence else None
            item = AssignmentItem(
                assignment_id=replacement.id,
                exercise_id=exercise_id,
                position=position,
                branch_after_item_id=item_map.get(old_item.branch_after_item_id) if old_item else None,
                branch_on=old_item.branch_on if old_item else None,
            )
            db.add(item)
            db.flush()
            if old_item:
                item_map[old_item.id] = item.id
    db.commit()
    return draft_json(db, cycle)


@app.patch("/api/cycles/{cycle_id}")
def update_cycle(
    cycle_id: str,
    body: CycleUpdate,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    if cycle.state not in {"review_ready", "approved"} or body.version != cycle.version:
        raise HTTPException(409, "The cycle changed; reload before updating it")
    if body.closes_at is None and body.budget_minutes is None:
        raise HTTPException(422, "Provide a closing date or practice budget")
    closes_at = body.closes_at or cycle.closes_at
    budget_minutes = body.budget_minutes or cycle.budget_minutes
    if _aware(closes_at) <= organization_now(db, cycle.organization_id):
        raise HTTPException(422, "The closing date must be in the future")
    current = list(db.scalars(select(Assignment).where(Assignment.cycle_id == cycle.id, Assignment.version == cycle.version)))
    if any(not assignment.excluded and assignment.estimated_minutes > budget_minutes for assignment in current):
        raise HTTPException(422, "The practice budget is shorter than an included assignment")
    if closes_at == cycle.closes_at and budget_minutes == cycle.budget_minutes:
        return cycle_json(cycle)
    cycle.version += 1
    cycle.closes_at = closes_at
    cycle.budget_minutes = budget_minutes
    cycle.state = "review_ready"
    for old in current:
        replacement = Assignment(
            cycle_id=cycle.id,
            learner_id=old.learner_id,
            version=cycle.version,
            reason=old.reason,
            estimated_minutes=old.estimated_minutes,
            excluded=old.excluded,
        )
        db.add(replacement)
        db.flush()
        item_map = {}
        for old_item in old.items:
            item = AssignmentItem(
                assignment_id=replacement.id,
                exercise_id=old_item.exercise_id,
                position=old_item.position,
                branch_after_item_id=item_map.get(old_item.branch_after_item_id),
                branch_on=old_item.branch_on,
            )
            db.add(item)
            db.flush()
            item_map[old_item.id] = item.id
    db.commit()
    return cycle_json(cycle)


@app.post("/api/cycles/{cycle_id}/approve")
def approve(
    cycle_id: str,
    body: ApproveRequest,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    if cycle.state not in {"review_ready", "approved"} or body.version != cycle.version:
        raise HTTPException(409, "The draft changed; review its current version before approving")
    assignments = list(
        db.scalars(
            select(Assignment).where(
                Assignment.cycle_id == cycle.id,
                Assignment.version == cycle.version,
                Assignment.id.in_(body.assignment_ids),
                Assignment.excluded.is_(False),
            )
        )
    )
    if len(assignments) != len(set(body.assignment_ids)):
        raise HTTPException(422, "Approval recipients must match active assignments in this draft")
    approval = db.scalar(select(Approval).where(Approval.cycle_id == cycle.id, Approval.version == cycle.version))
    proposed_recipients = sorted(assignment.learner_id for assignment in assignments)
    proposed_permissions = ["publish", *(["reminder"] if body.allow_reminder else [])]
    proposed_hash = assignment_batch_hash(db, cycle, body.assignment_ids)
    if approval and (
        approval.recipient_ids != proposed_recipients
        or approval.permissions != proposed_permissions
        or approval.batch_hash != proposed_hash
    ):
        raise HTTPException(409, "This version already has a different immutable approval")
    if not approval:
        approval = Approval(
            cycle_id=cycle.id,
            actor_id=principal.user.id,
            version=cycle.version,
            batch_hash=proposed_hash,
            recipient_ids=proposed_recipients,
            permissions=proposed_permissions,
        )
        db.add(approval)
        db.flush()
        db.add(
            AuditEvent(
                organization_id=cycle.organization_id,
                actor_id=principal.user.id,
                action="cycle.approved",
                object_type="approval",
                object_id=approval.id,
            )
        )
    cycle.state = "approved"
    db.commit()
    return {
        "id": approval.id,
        "version": approval.version,
        "batch_hash": approval.batch_hash,
        "recipient_ids": approval.recipient_ids,
        "permissions": approval.permissions,
        "created_at": approval.created_at,
    }


@app.post("/api/cycles/{cycle_id}/publish")
def publish(
    cycle_id: str,
    body: PublishRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    approval = db.get(Approval, body.approval_id)
    approver_membership = (
        db.scalar(
            select(Membership).where(
                Membership.user_id == approval.actor_id,
                Membership.organization_id == cycle.organization_id,
                Membership.role.in_(["teacher", "owner"]),
            )
        )
        if approval
        else None
    )
    if (
        cycle.state not in {"approved", "active"}
        or _aware(cycle.closes_at) <= organization_now(db, cycle.organization_id)
        or not approval
        or "publish" not in approval.permissions
        or not approver_membership
        or approval.cycle_id != cycle.id
        or approval.version != body.version
        or cycle.version != body.version
    ):
        raise HTTPException(409, "The approval does not cover the current draft")
    assignments = list(
        db.scalars(
            select(Assignment).where(
                Assignment.cycle_id == cycle.id,
                Assignment.version == cycle.version,
                Assignment.learner_id.in_(approval.recipient_ids),
                Assignment.excluded.is_(False),
            )
        )
    )
    if len(assignments) != len(approval.recipient_ids) or assignment_batch_hash(db, cycle, [a.id for a in assignments]) != approval.batch_hash:
        raise HTTPException(409, "The approved content or recipients changed")
    deliveries = []
    for assignment in assignments:
        assignment.published = True
        existing = db.scalar(select(Delivery).where(Delivery.assignment_id == assignment.id, Delivery.channel == "email"))
        if not existing:
            existing = Delivery(
                assignment_id=assignment.id,
                recipient_id=assignment.learner_id,
                idempotency_key=f"assignment:{assignment.id}:email",
            )
            db.add(existing)
            db.flush()
            db.add(
                OutboxEvent(
                    organization_id=cycle.organization_id,
                    kind="delivery.queued",
                    payload={"delivery_id": existing.id, "request_key": idempotency_key},
                )
            )
        deliveries.append(existing)
    cycle.state = "active"
    if not db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.action == "cycle.published", AuditEvent.object_id == approval.id
        )
    ):
        db.add(
            AuditEvent(
                organization_id=cycle.organization_id,
                actor_id=principal.user.id,
                action="cycle.published",
                object_type="approval",
                object_id=approval.id,
            )
        )
    db.commit()
    return {
        "cycle": cycle_json(cycle),
        "assignments": [
            {"id": a.id, "learner_id": a.learner_id, "state": a.state, "published": a.published}
            for a in assignments
        ],
        "deliveries": [{"id": d.id, "assignment_id": d.assignment_id, "state": d.state} for d in deliveries],
    }


def _authorized_assignment(db: Session, principal: Principal, assignment_id: str, *, published: bool = True) -> Assignment:
    assignment = db.get(Assignment, assignment_id)
    cycle = db.get(LearningCycle, assignment.cycle_id) if assignment else None
    if not assignment or not cycle or cycle.organization_id != principal.membership.organization_id:
        raise HTTPException(404, "Assignment not found")
    if principal.membership.role == "learner":
        enrollment = db.scalar(
            select(Enrollment).where(
                Enrollment.classroom_id == cycle.classroom_id,
                Enrollment.learner_id == principal.user.id,
                Enrollment.status == "active",
            )
        )
        if not enrollment or assignment.learner_id != principal.user.id or (published and not assignment.published):
            raise HTTPException(404, "Assignment not found")
    elif db.get(Classroom, cycle.classroom_id).teacher_id != principal.user.id:
        raise HTTPException(404, "Assignment not found")
    return assignment


@app.get("/api/assignments/{assignment_id}")
def get_assignment(
    assignment_id: str,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict:
    assignment = _authorized_assignment(db, principal, assignment_id)
    cycle = db.get(LearningCycle, assignment.cycle_id)
    attempts = {a.item_id: a for a in db.scalars(select(Attempt).where(Attempt.assignment_id == assignment.id))}
    items = visible_items(db, assignment)
    return {
        "id": assignment.id,
        "cycle": {"id": cycle.id, "objective": cycle.objective, "closes_at": cycle.closes_at},
        "learner": user_json(db.get(User, assignment.learner_id)),
        "state": assignment.state,
        "progress": {"answered": len(attempts), "total": len(items)},
        "items": [
            {
                "id": item.id,
                "position": item.position,
                "branch_after_item_id": item.branch_after_item_id,
                "branch_on": item.branch_on,
                "exercise": exercise_json(item.exercise, revealed=bool(attempts.get(item.id))),
                "attempt": (
                    {
                        "id": attempt.id,
                        "result": attempt.result,
                        "feedback": attempt.feedback,
                        "used_hint": attempt.used_hint,
                    }
                    if (attempt := attempts.get(item.id))
                    else None
                ),
            }
            for item in items
        ],
    }


@app.get("/api/assignments")
def list_assignments(
    principal: Principal = Depends(require_principal), db: Session = Depends(get_db)
) -> list[dict]:
    query = (
        select(Assignment)
        .join(LearningCycle, LearningCycle.id == Assignment.cycle_id)
        .join(Classroom, Classroom.id == LearningCycle.classroom_id)
        .where(
            LearningCycle.organization_id == principal.membership.organization_id,
            Assignment.published.is_(True),
        )
        .order_by(LearningCycle.created_at.desc())
    )
    if principal.membership.role == "learner":
        query = query.join(
            Enrollment,
            (Enrollment.classroom_id == Classroom.id) & (Enrollment.learner_id == principal.user.id),
        ).where(Assignment.learner_id == principal.user.id, Enrollment.status == "active")
    else:
        query = query.where(Classroom.teacher_id == principal.user.id)
    return [
        {
            "id": assignment.id,
            "cycle_id": assignment.cycle_id,
            "learner_id": assignment.learner_id,
            "state": assignment.state,
        }
        for assignment in db.scalars(query)
    ]


@app.post("/api/assignments/{assignment_id}/items/{item_id}/hint")
def request_hint(
    assignment_id: str,
    item_id: str,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict:
    assignment = _authorized_assignment(db, principal, assignment_id)
    if principal.membership.role != "learner":
        raise HTTPException(403, "Only the learner can request help on their assignment")
    cycle = db.get(LearningCycle, assignment.cycle_id)
    if cycle.state != "active" or _aware(cycle.closes_at) <= organization_now(db, cycle.organization_id):
        raise HTTPException(409, "This practice is closed")
    item = db.get(AssignmentItem, item_id)
    if not item or item.assignment_id != assignment.id or item not in visible_items(db, assignment):
        raise HTTPException(404, "Assignment item not found")
    event = db.scalar(
        select(AssistanceEvent).where(
            AssistanceEvent.assignment_id == assignment.id,
            AssistanceEvent.item_id == item.id,
            AssistanceEvent.learner_id == principal.user.id,
        )
    )
    if not event:
        event = AssistanceEvent(assignment_id=assignment.id, item_id=item.id, learner_id=principal.user.id)
        db.add(event)
        db.commit()
    return {"event_id": event.id, "hint": item.exercise.hint}


@app.post("/api/assignments/{assignment_id}/attempts")
def submit_attempt(
    assignment_id: str,
    body: AttemptCreate,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict:
    assignment = _authorized_assignment(db, principal, assignment_id)
    if principal.membership.role != "learner":
        raise HTTPException(403, "Only the assigned learner can submit a response")
    cycle = db.get(LearningCycle, assignment.cycle_id)
    if cycle.state != "active" or _aware(cycle.closes_at) <= organization_now(db, cycle.organization_id):
        raise HTTPException(409, "This practice is closed")
    existing = db.scalar(
        select(Attempt).where(Attempt.assignment_id == assignment.id, Attempt.client_key == body.client_key)
    )
    if existing:
        item = db.get(AssignmentItem, existing.item_id)
        return _attempt_json(existing, item.exercise)
    item = db.get(AssignmentItem, body.item_id)
    if not item or item.assignment_id != assignment.id or item not in visible_items(db, assignment):
        raise HTTPException(404, "Assignment item not found")
    if db.scalar(select(Attempt.id).where(Attempt.assignment_id == assignment.id, Attempt.item_id == item.id)):
        raise HTTPException(409, "This item already has a submitted response")
    assistance = db.scalar(
        select(AssistanceEvent.id).where(
            AssistanceEvent.assignment_id == assignment.id,
            AssistanceEvent.item_id == item.id,
            AssistanceEvent.learner_id == principal.user.id,
        )
    )
    result, score, feedback = grade(item.exercise, body.response, hints_used=int(bool(assistance)))
    attempt = Attempt(
        assignment_id=assignment.id,
        item_id=item.id,
        learner_id=principal.user.id,
        client_key=body.client_key,
        response=body.response,
        used_hint=bool(assistance),
        result=result,
        score=score,
        feedback=feedback,
    )
    db.add(attempt)
    db.flush()
    if result != "review_needed":
        db.add(
            EvidenceEvent(
                learner_id=principal.user.id,
                concept_id=item.exercise.concept_id,
                attempt_id=attempt.id,
                outcome=result,
                evaluator="deterministic",
                used_hint=attempt.used_hint,
            )
        )
    refresh_assignment_state(db, assignment)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(Attempt).where(
                Attempt.assignment_id == assignment_id, Attempt.client_key == body.client_key
            )
        )
        if existing:
            return _attempt_json(existing, db.get(AssignmentItem, existing.item_id).exercise)
        raise HTTPException(409, "This item already has a submitted response")
    return _attempt_json(attempt, item.exercise)


def _attempt_json(attempt: Attempt, exercise: ExerciseVersion) -> dict:
    return {
        "id": attempt.id,
        "item_id": attempt.item_id,
        "result": attempt.result,
        "score": attempt.score,
        "feedback": attempt.feedback,
        "explanation": exercise.explanation,
        "used_hint": attempt.used_hint,
        "submitted_at": attempt.submitted_at,
    }


@app.post("/api/attempts/{attempt_id}/review")
def review_attempt(
    attempt_id: str,
    body: ReviewCreate,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    if body.outcome not in {"correct", "incorrect"}:
        raise HTTPException(422, "Review outcome must be correct or incorrect")
    attempt = db.get(Attempt, attempt_id)
    assignment = db.get(Assignment, attempt.assignment_id) if attempt else None
    cycle = db.get(LearningCycle, assignment.cycle_id) if assignment else None
    if not attempt or not cycle:
        raise HTTPException(404, "Attempt not found")
    _teacher_cycle(db, principal, cycle.id)
    item = db.get(AssignmentItem, attempt.item_id)
    previous = db.scalar(
        select(EvidenceEvent)
        .where(EvidenceEvent.attempt_id == attempt.id)
        .order_by(EvidenceEvent.revision.desc())
    )
    revision = (previous.revision + 1) if previous else 1
    event = EvidenceEvent(
        learner_id=attempt.learner_id,
        concept_id=item.exercise.concept_id,
        attempt_id=attempt.id,
        outcome=body.outcome,
        evaluator="teacher",
        used_hint=attempt.used_hint,
        revision=revision,
        supersedes_id=previous.id if previous else None,
    )
    db.add(event)
    db.add(
        AuditEvent(
            organization_id=cycle.organization_id,
            actor_id=principal.user.id,
            action="attempt.reviewed",
            object_type="attempt",
            object_id=attempt.id,
        )
    )
    attempt.result = body.outcome
    attempt.score = 1 if body.outcome == "correct" else 0
    attempt.feedback = body.feedback
    refresh_assignment_state(db, assignment)
    db.commit()
    return {"attempt_id": attempt.id, "result": attempt.result, "evidence_event_id": event.id, "revision": revision}


@app.get("/api/attempts/{attempt_id}")
def attempt_detail(
    attempt_id: str,
    principal: Principal = Depends(require_principal),
    db: Session = Depends(get_db),
) -> dict:
    attempt = db.get(Attempt, attempt_id)
    if not attempt:
        raise HTTPException(404, "Attempt not found")
    assignment = _authorized_assignment(db, principal, attempt.assignment_id)
    if attempt.learner_id != assignment.learner_id:
        raise HTTPException(404, "Attempt not found")
    item = db.get(AssignmentItem, attempt.item_id)
    revisions = db.scalars(
        select(EvidenceEvent)
        .where(EvidenceEvent.attempt_id == attempt.id)
        .order_by(EvidenceEvent.revision)
    )
    return {
        "id": attempt.id,
        "learner": db.get(User, attempt.learner_id).display_name,
        "question": item.exercise.prompt,
        "response": attempt.response,
        "result": attempt.result,
        "used_hint": attempt.used_hint,
        "submitted_at": attempt.submitted_at,
        "revisions": [
            {
                "id": event.id,
                "outcome": event.outcome,
                "evaluator": event.evaluator,
                "revision": event.revision,
                "created_at": event.created_at,
            }
            for event in revisions
        ],
    }


@app.get("/api/cycles/{cycle_id}/pending-reviews")
def pending_reviews(
    cycle_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> list[str]:
    cycle = _teacher_cycle(db, principal, cycle_id)
    return list(
        db.scalars(
            select(Attempt.id)
            .join(Assignment, Assignment.id == Attempt.assignment_id)
            .where(Assignment.cycle_id == cycle.id, Attempt.result == "review_needed")
            .order_by(Attempt.submitted_at)
        )
    )


@app.get("/api/cycles/{cycle_id}/brief")
def cycle_brief(
    cycle_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    return brief_json(db, _teacher_cycle(db, principal, cycle_id))


@app.get("/api/cycles/{cycle_id}/agent-run")
def cycle_agent_run(
    cycle_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> dict:
    cycle = _teacher_cycle(db, principal, cycle_id)
    job = db.scalar(select(Job).where(
        Job.organization_id == cycle.organization_id,
        Job.kind == "prepare_cycle",
        Job.payload["cycle_id"].as_string() == cycle.id,
    ).order_by(Job.created_at.desc()).limit(1))
    if not job:
        return {"state": "not_started", "cycle_id": cycle.id}
    agent = job.payload.get("agent", {})
    # An explicit allowlist keeps raw payloads, model text and credentials off the client.
    return {
        "id": job.id, "cycle_id": cycle.id, "state": job.state,
        "version": job.payload.get("cycle_version"), "started_at": job.started_at,
        "mode": agent.get("mode", "unreported"),
        "model_invoked": agent.get("model_invoked", False),
        "model": agent.get("model"), "model_calls": agent.get("model_calls", 0),
        "tools": agent.get("tools", []), "operations": agent.get("operations", []),
        "draft_count": agent.get("draft_count", 0),
        "awaiting_approval": cycle.state in {"review_ready", "approved"},
    }


@app.get("/api/runs/{job_id}/events")
def job_events(
    job_id: str,
    principal: Principal = Depends(require_teacher),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    job = db.get(Job, job_id)
    if not job or job.organization_id != principal.membership.organization_id:
        raise HTTPException(404, "Run not found")
    cycle_id = job.payload.get("cycle_id")
    if not cycle_id:
        raise HTTPException(404, "Run not found")
    _teacher_cycle(db, principal, cycle_id)

    def event():
        last_state = None
        for _ in range(60):
            with SessionLocal() as stream_db:
                current = stream_db.get(Job, job_id)
                state = current.state if current else "failed"
            if state != last_state:
                yield f"event: status\ndata: {json.dumps({'state': state})}\n\n"
                last_state = state
            else:
                yield ": keep-alive\n\n"
            if state in {"completed", "failed"}:
                return
            time.sleep(0.5)

    return StreamingResponse(event(), media_type="text/event-stream")

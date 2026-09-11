from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path

import httpx
from fastapi import HTTPException
from pypdf import PdfReader
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .exercises.grading import grade_answer
from .learning.policy import build_assignment_plan
from .learning.nema_needs import apply_implicit_repetition
from .learning.state import derive_state
from .integrations.nema.models import NemaGrant, NemaReadinessRequest

from .config import get_settings
from .exercises.catalog import all_exercises, load_catalog
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
    Job,
    IdempotencyRecord,
    LearningCycle,
    Material,
    Membership,
    Organization,
    OutboxEvent,
    User,
)


CONCEPTS = [
    ("numerator-denominator", "Numerator and denominator", "What is the numerator of 3/5?", "3"),
    ("fraction-quantity", "Fraction as quantity", "Write three quarters as a fraction.", "3/4"),
    ("representation", "Representing fractions", "Which fraction is three of four equal parts?", "3/4"),
    ("equivalence", "Equivalent fractions", "Simplify 4/6.", "2/3"),
    ("simplification", "Simplifying fractions", "Simplify 8/12.", "2/3"),
    ("multiples", "Multiples", "What is the least common multiple of 4 and 6?", "12"),
    ("common-denominator", "Common denominators", "Give a common denominator for 1/4 and 1/6.", "12"),
    ("comparison", "Comparing fractions", "Enter >, <, or =: 3/4 __ 2/3", ">"),
    ("add-same-denominator", "Adding like fractions", "Calculate 1/5 + 2/5.", "3/5"),
    ("add-different-denominator", "Adding unlike fractions", "Calculate 1/2 + 1/3.", "5/6"),
    ("subtraction", "Subtracting fractions", "Calculate 3/4 - 1/4.", "1/2"),
    ("context", "Fraction applications", "Mina ate 1/4 of a pie, then 1/2. How much in total?", "3/4"),
]


def user_json(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "synthetic": user.synthetic,
    }


def classroom_json(classroom: Classroom) -> dict:
    return {
        "id": classroom.id,
        "title": classroom.title,
        "language": classroom.language,
        "practice_minutes": classroom.practice_minutes,
    }


def cycle_json(cycle: LearningCycle) -> dict:
    return {
        "id": cycle.id,
        "classroom_id": cycle.classroom_id,
        "objective": cycle.objective,
        "concepts": cycle.concepts,
        "concept_confirmed": cycle.concept_confirmed,
        "closes_at": cycle.closes_at,
        "budget_minutes": cycle.budget_minutes,
        "state": cycle.state,
        "version": cycle.version,
    }


def exercise_json(exercise: ExerciseVersion, *, revealed: bool = False) -> dict:
    data = {
        "id": exercise.id,
        "concept_id": exercise.concept_id,
        "kind": exercise.kind,
        "prompt": exercise.prompt,
        "options": exercise.options,
        "estimated_minutes": exercise.estimated_minutes,
        "source": exercise.source,
    }
    if revealed:
        data["explanation"] = exercise.explanation
    return data


def _add_bank(db: Session) -> None:
    catalog = all_exercises()
    expected_ids = {item["id"] for item in catalog}
    existing_ids = set(db.scalars(select(ExerciseVersion.id)))
    if existing_ids == expected_ids:
        return
    if existing_ids:
        if db.scalar(select(func.count()).select_from(AssignmentItem)):
            return
        db.execute(delete(ExerciseVersion))
    for item in catalog:
        db.add(ExerciseVersion(**item, source="Tiza reviewed fractions bank", approved=True))
    db.flush()


def seed_demo(db: Session, *, reset_cycles: bool = False) -> tuple[Organization, Classroom, User, list[User]]:
    organization = db.scalar(select(Organization).where(Organization.demo.is_(True)))
    if not organization:
        organization = Organization(name="Tiza Demo", demo=True)
        teacher = User(
            auth_subject="demo:teacher", email="teacher@demo.tiza", display_name="Alex Morgan", synthetic=True
        )
        db.add_all([organization, teacher])
        db.flush()
        db.add(Membership(organization_id=organization.id, user_id=teacher.id, role="teacher"))
        classroom = Classroom(
            organization_id=organization.id,
            teacher_id=teacher.id,
            title="Fraction Workshop",
            language="en",
            practice_minutes=15,
        )
        db.add(classroom)
        db.flush()
        names = ["Maya", "Leo", "Sofia", "Noah", "Ava", "Mateo", "Lina", "Sam"]
        learners = []
        for index, name in enumerate(names, 1):
            learner = User(
                auth_subject=f"demo:learner:{index}",
                email=f"learner{index}@demo.tiza",
                display_name=name,
                synthetic=True,
            )
            db.add(learner)
            db.flush()
            db.add_all(
                [
                    Membership(organization_id=organization.id, user_id=learner.id, role="learner"),
                    Enrollment(classroom_id=classroom.id, learner_id=learner.id),
                ]
            )
            learners.append(learner)
        db.flush()
    else:
        teacher = db.scalar(
            select(User).join(Membership).where(
                Membership.organization_id == organization.id, Membership.role == "teacher"
            )
        )
        classroom = db.scalar(select(Classroom).where(Classroom.organization_id == organization.id))
        learners = list(
            db.scalars(
                select(User)
                .join(Enrollment, Enrollment.learner_id == User.id)
                .where(Enrollment.classroom_id == classroom.id)
                .order_by(User.display_name)
            )
        )
    if reset_cycles:
        organization.demo_offset_seconds = 0
        cycle_ids = list(db.scalars(select(LearningCycle.id).where(LearningCycle.organization_id == organization.id)))
        assignment_ids = list(db.scalars(select(Assignment.id).where(Assignment.cycle_id.in_(cycle_ids)))) if cycle_ids else []
        attempt_ids = list(db.scalars(select(Attempt.id).where(Attempt.assignment_id.in_(assignment_ids)))) if assignment_ids else []
        for model, condition in [
            (NemaGrant, NemaGrant.organization_id == organization.id),
            (NemaReadinessRequest, NemaReadinessRequest.organization_id == organization.id),
            (EvidenceEvent, EvidenceEvent.attempt_id.in_(attempt_ids)),
            (AssistanceEvent, AssistanceEvent.assignment_id.in_(assignment_ids)),
            (Attempt, Attempt.assignment_id.in_(assignment_ids)),
            (Delivery, Delivery.assignment_id.in_(assignment_ids)),
            (AssignmentItem, AssignmentItem.assignment_id.in_(assignment_ids)),
            (Approval, Approval.cycle_id.in_(cycle_ids)),
            (Assignment, Assignment.cycle_id.in_(cycle_ids)),
            (Material, Material.cycle_id.in_(cycle_ids)),
            (LearningCycle, LearningCycle.id.in_(cycle_ids)),
        ]:
            if cycle_ids:
                db.execute(delete(model).where(condition))
        db.execute(delete(ExerciseVersion))
        db.execute(delete(Job).where(Job.organization_id == organization.id))
        db.execute(delete(OutboxEvent).where(OutboxEvent.organization_id == organization.id))
        db.execute(delete(IdempotencyRecord).where(IdempotencyRecord.organization_id == organization.id))
    _add_bank(db)
    db.flush()
    if not db.scalar(select(LearningCycle.id).where(LearningCycle.organization_id == organization.id)):
        _seed_evidence(db, organization, classroom, learners)
    db.commit()
    return organization, classroom, teacher, learners


def _seed_evidence(
    db: Session, organization: Organization, classroom: Classroom, learners: list[User]
) -> None:
    cycle = LearningCycle(
        organization_id=organization.id,
        classroom_id=classroom.id,
        objective="Baseline fraction check (synthetic demo data)",
        concepts=["equivalence", "common-denominator", "add-different-denominator"],
        concept_confirmed=True,
        closes_at=datetime.now(timezone.utc) - timedelta(days=1),
        budget_minutes=5,
        state="closed",
    )
    db.add(cycle)
    db.flush()
    outcomes = ["correct", "incorrect", "incorrect", "correct", None, "incorrect", "correct", "review_needed"]
    concepts = ["equivalence", "common-denominator", "common-denominator", "add-different-denominator",
                "equivalence", "add-same-denominator", "simplification", "context"]
    exercises = {e.concept_id: e for e in db.scalars(select(ExerciseVersion).where(ExerciseVersion.kind == "numeric"))}
    for learner, outcome, concept_id in zip(learners, outcomes, concepts, strict=True):
        assignment = Assignment(
            cycle_id=cycle.id,
            learner_id=learner.id,
            version=1,
            reason="Synthetic baseline evidence",
            estimated_minutes=2,
            state="completed" if outcome == "correct" else "submitted",
            published=True,
        )
        db.add(assignment)
        db.flush()
        item = AssignmentItem(assignment_id=assignment.id, exercise_id=exercises[concept_id].id, position=1)
        db.add(item)
        db.flush()
        if outcome:
            attempt = Attempt(
                assignment_id=assignment.id,
                item_id=item.id,
                learner_id=learner.id,
                client_key=f"seed-{learner.id}",
                response="synthetic",
                used_hint=learner == learners[2],
                result=outcome,
                score=1 if outcome == "correct" else (0 if outcome == "incorrect" else None),
            )
            db.add(attempt)
            db.flush()
            if outcome != "review_needed":
                db.add(
                    EvidenceEvent(
                        learner_id=learner.id,
                        concept_id=concept_id,
                        attempt_id=attempt.id,
                        outcome=outcome,
                        evaluator="deterministic",
                        used_hint=attempt.used_hint,
                    )
                )


def extract_material(filename: str, content_type: str, raw: bytes) -> tuple[str, int]:
    if len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, "Materials must be 10 MB or smaller")
    suffix = Path(filename).suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            return raw.decode("utf-8"), 1
        except UnicodeDecodeError as exc:
            raise HTTPException(422, "Text materials must use UTF-8") from exc
    if suffix != ".pdf" and content_type != "application/pdf":
        raise HTTPException(415, "Upload a text, Markdown, or PDF file")
    try:
        reader = PdfReader(BytesIO(raw))
        if len(reader.pages) > 30:
            raise HTTPException(422, "PDF materials must have at most 30 pages")
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "The PDF could not be read") from exc
    if not text:
        raise HTTPException(422, "This PDF has no text layer; scanned PDFs are not supported yet")
    return text, len(reader.pages)


def store_material(db: Session, cycle: LearningCycle, filename: str, content_type: str, raw: bytes) -> Material:
    text, pages = extract_material(filename, content_type, raw)
    digest = sha256(raw).hexdigest()
    settings = get_settings()
    object_name = f"{cycle.organization_id}/{cycle.id}/{digest}{Path(filename).suffix.lower()}"
    if settings.demo_mode:
        base = settings.material_dir
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"{cycle.id}-{digest[:16]}{Path(filename).suffix.lower()}"
        path.write_bytes(raw)
        object_path = str(path)
    else:
        response = httpx.post(
            f"{settings.supabase_url}/storage/v1/object/{settings.supabase_material_bucket}/{object_name}",
            content=raw,
            headers={
                "apikey": settings.supabase_service_key,
                "authorization": f"Bearer {settings.supabase_service_key}",
                "content-type": content_type,
                "x-upsert": "false",
            },
            timeout=30,
        )
        if response.status_code not in {200, 201}:
            raise HTTPException(502, "The private material could not be stored")
        object_path = object_name
    material = Material(
        cycle_id=cycle.id,
        filename=Path(filename).name,
        content_type=content_type,
        object_path=object_path,
        sha256=digest,
        extracted_text=text,
        page_count=pages,
    )
    db.add(material)
    return material


def concept_candidates(text: str, material_id: str | None = None) -> list[dict]:
    lowered = text.lower()
    matches = []
    for concept_id, title, *_ in CONCEPTS:
        words = title.lower().replace("fractions", "fraction").split()
        if any(word in lowered for word in words if len(word) > 3):
            matches.append(
                {
                    "id": concept_id,
                    "title": title,
                    "reference": f"material:{material_id}" if material_id else "teacher-objective",
                    "quote": text[:160].strip(),
                }
            )
    if not matches:
        matches = [
            {"id": "equivalence", "title": "Equivalent fractions", "reference": "teacher-objective", "quote": text[:160].strip()},
            {"id": "add-different-denominator", "title": "Adding unlike fractions", "reference": "teacher-objective", "quote": text[:160].strip()},
        ]
    return matches[:6]


def allowed_concepts(targets: list[str]) -> set[str]:
    definitions = {item["id"]: item for item in load_catalog()["concepts"]}
    allowed: set[str] = set()

    def add(concept_id: str) -> None:
        for prerequisite in definitions[concept_id]["prerequisites"]:
            add(prerequisite)
        allowed.add(concept_id)

    for target in targets:
        add(target)
    return allowed


def prepare_cycle(db: Session, cycle_id: str, job_id: str) -> None:
    """Worker entrypoint. The transaction owner commits or rolls back this whole operation."""
    cycle = db.get(LearningCycle, cycle_id)
    job = db.get(Job, job_id)
    if not cycle or not job or job.payload.get("cycle_id") != cycle_id:
        raise ValueError("Preparation job does not match its cycle")
    if job.organization_id != cycle.organization_id or job.payload.get("cycle_version") != cycle.version:
        raise ValueError("Preparation job scope or version is stale")
    membership = db.scalar(
        select(Membership).where(
            Membership.user_id == job.payload.get("actor_id"),
            Membership.organization_id == cycle.organization_id,
            Membership.role.in_(["teacher", "owner"]),
        )
    )
    if not membership:
        raise ValueError("Preparation actor is no longer authorized")
    if cycle.state != "preparing" or not cycle.concept_confirmed:
        raise ValueError("Cycle is not ready for preparation")
    enrollments = list(
        db.scalars(
            select(Enrollment).where(
                Enrollment.classroom_id == cycle.classroom_id, Enrollment.status == "active"
            )
        )
    )
    approved = list(db.scalars(select(ExerciseVersion).where(ExerciseVersion.approved.is_(True))))
    approved_by_id = {exercise.id: exercise for exercise in approved}
    target_concepts = cycle.concepts or ["equivalence", "add-different-denominator"]
    for enrollment in enrollments:
        evidence_rows = list(
            db.execute(
                select(EvidenceEvent, Attempt, Assignment, LearningCycle)
                .join(Attempt, Attempt.id == EvidenceEvent.attempt_id)
                .join(Assignment, Assignment.id == Attempt.assignment_id)
                .join(LearningCycle, LearningCycle.id == Assignment.cycle_id)
                .where(
                    EvidenceEvent.learner_id == enrollment.learner_id,
                    Attempt.learner_id == enrollment.learner_id,
                    Assignment.learner_id == enrollment.learner_id,
                    LearningCycle.organization_id == cycle.organization_id,
                    LearningCycle.classroom_id == cycle.classroom_id,
                )
            )
        )
        latest_by_attempt = {}
        for event, attempt, assignment, source_cycle in evidence_rows:
            current = latest_by_attempt.get(attempt.id)
            if current is None or event.revision > current.revision:
                latest_by_attempt[attempt.id] = event
        receipts = [
            {
                "status": "verified",
                "receiptId": event.id,
                "receivedAt": event.created_at.isoformat(),
                "payload": {
                    "issuedAt": event.created_at.isoformat(),
                    "conditions": {"grader": "deterministic" if event.evaluator == "deterministic" else "provider-rubric"},
                    "claims": [
                        {
                            "concept": event.concept_id,
                            "ability": "apply",
                            "result": (
                                "partial"
                                if event.outcome == "correct" and event.used_hint
                                else "passed" if event.outcome == "correct" else "failed"
                            ),
                        }
                    ],
                },
            }
            for event in latest_by_attempt.values()
        ]
        evaluated_at = datetime.now(timezone.utc)
        state = derive_state(receipts, now=evaluated_at)
        nema_concepts = [
            {**item, "prereqs": item.get("prerequisites", [])}
            for item in load_catalog()["concepts"]
        ]
        state = apply_implicit_repetition(state, concepts=nema_concepts, now=evaluated_at)
        plan, reasons = build_assignment_plan(
            {"evidence": state, "target_concepts": target_concepts},
            cycle.budget_minutes,
            approved,
        )
        chosen = [approved_by_id[item["exercise_id"]] for item in plan if item["exercise_id"] in approved_by_id]
        if not chosen or sum(item.estimated_minutes for item in chosen) > cycle.budget_minutes:
            raise ValueError("No approved exercise exists for the confirmed concepts")
        titles = {item["id"]: item["title"] for item in load_catalog()["concepts"]}
        notes = []
        for item in plan:
            if item.get("branch_on"):
                continue
            title = titles[item["concept_id"]].lower()
            why = item["reason"]
            if why == "no_evidence":
                note = f"Check {title}: no recorded evidence yet."
            elif why == "unrepaired_failure":
                note = f"Revisit {title} after an incorrect answer."
            elif why == "goal_ready_for_application":
                note = f"Apply {title} toward the lesson goal."
            else:
                note = f"Practise {title}: evidence is still limited."
            if note not in notes:
                notes.append(note)
        reason = " ".join(notes)
        assignment = Assignment(
            cycle_id=cycle.id,
            learner_id=enrollment.learner_id,
            version=cycle.version,
            reason=reason,
            estimated_minutes=sum(item.estimated_minutes for item in chosen),
        )
        db.add(assignment)
        db.flush()
        created_by_exercise = {}
        for position, (planned, exercise) in enumerate(zip(plan, chosen, strict=True), 1):
            parent_exercise_id = planned.get("branch_after_exercise_id")
            parent = created_by_exercise.get(parent_exercise_id)
            item = AssignmentItem(
                assignment_id=assignment.id,
                exercise_id=exercise.id,
                position=position,
                branch_after_item_id=parent.id if parent else None,
                branch_on=planned.get("branch_on"),
            )
            if parent_exercise_id and not item.branch_after_item_id:
                raise ValueError("Assignment policy produced an invalid branch")
            db.add(item)
            db.flush()
            created_by_exercise[exercise.id] = item
    cycle.state = "review_ready"
    job.state = "completed"
    db.add(
        AuditEvent(
            organization_id=cycle.organization_id,
            actor_id=job.payload["actor_id"],
            action="cycle.prepared",
            object_type="cycle",
            object_id=cycle.id,
        )
    )


def assignment_batch_hash(db: Session, cycle: LearningCycle, assignment_ids: list[str] | None = None) -> str:
    query = select(Assignment).where(Assignment.cycle_id == cycle.id, Assignment.version == cycle.version)
    if assignment_ids is not None:
        query = query.where(Assignment.id.in_(assignment_ids))
    assignments = list(db.scalars(query.order_by(Assignment.id)))
    payload = {
        "cycle": {
            "id": cycle.id,
            "objective": cycle.objective,
            "concepts": cycle.concepts,
            "closes_at": cycle.closes_at.isoformat(),
            "budget_minutes": cycle.budget_minutes,
            "version": cycle.version,
        },
        "assignments": [
            {
                "id": assignment.id,
                "learner_id": assignment.learner_id,
                "excluded": assignment.excluded,
                "items": [
                    {
                        "position": item.position,
                        "branch_after_item_id": item.branch_after_item_id,
                        "branch_on": item.branch_on,
                        "exercise": {
                            "id": item.exercise.id,
                            "concept_id": item.exercise.concept_id,
                            "kind": item.exercise.kind,
                            "prompt": item.exercise.prompt,
                            "options": item.exercise.options,
                            "answer": item.exercise.answer,
                            "explanation": item.exercise.explanation,
                            "hint": item.exercise.hint,
                            "estimated_minutes": item.exercise.estimated_minutes,
                            "source": item.exercise.source,
                        },
                    }
                    for item in assignment.items
                ],
            }
            for assignment in assignments
        ],
    }
    return sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()).hexdigest()


def draft_json(db: Session, cycle: LearningCycle) -> dict:
    assignments = list(
        db.scalars(
            select(Assignment)
            .where(Assignment.cycle_id == cycle.id, Assignment.version == cycle.version)
            .order_by(Assignment.learner_id)
        )
    )
    return {
        "cycle": cycle_json(cycle),
        "assignments": [
            {
                "id": assignment.id,
                "learner": user_json(db.get(User, assignment.learner_id)),
                "version": assignment.version,
                "reason": assignment.reason,
                "estimated_minutes": assignment.estimated_minutes,
                "state": assignment.state,
                "excluded": assignment.excluded,
                "items": [
                    {
                        "id": item.id,
                        "position": item.position,
                        "branch_after_item_id": item.branch_after_item_id,
                        "branch_on": item.branch_on,
                        "exercise": exercise_json(item.exercise),
                    }
                    for item in assignment.items
                ],
            }
            for assignment in assignments
        ],
    }


def grade(exercise: ExerciseVersion, response: str, *, hints_used: int = 0) -> tuple[str, int | None, str]:
    result = grade_answer(exercise, response, hints_used=hints_used)
    return result["result"], result["score"], result["feedback"]


def visible_items(db: Session, assignment: Assignment) -> list[AssignmentItem]:
    attempts = {attempt.item_id: attempt for attempt in db.scalars(select(Attempt).where(Attempt.assignment_id == assignment.id))}
    visible = []
    for item in assignment.items:
        if not item.branch_after_item_id:
            visible.append(item)
        elif (parent := attempts.get(item.branch_after_item_id)) and parent.result == item.branch_on:
            visible.append(item)
    return visible


def refresh_assignment_state(db: Session, assignment: Assignment) -> None:
    attempts = list(db.scalars(select(Attempt).where(Attempt.assignment_id == assignment.id)))
    if any(attempt.result == "review_needed" for attempt in attempts):
        assignment.state = "review_needed"
    elif attempts and len({attempt.item_id for attempt in attempts}) >= len(visible_items(db, assignment)):
        assignment.state = "completed"
    elif attempts:
        assignment.state = "in_progress"


def brief_json(db: Session, cycle: LearningCycle) -> dict:
    assignments = list(db.scalars(select(Assignment).where(Assignment.cycle_id == cycle.id, Assignment.published.is_(True))))
    counts = {key: 0 for key in ["completed", "in_progress", "not_started", "review_needed"]}
    for assignment in assignments:
        state = "in_progress" if assignment.state in {"submitted", "in_progress"} else assignment.state
        counts[state if state in counts else "not_started"] += 1
    incorrect = list(
        db.execute(
            select(Attempt, ExerciseVersion)
            .join(Assignment, Assignment.id == Attempt.assignment_id)
            .join(AssignmentItem, AssignmentItem.id == Attempt.item_id)
            .join(ExerciseVersion, ExerciseVersion.id == AssignmentItem.exercise_id)
            .where(Assignment.cycle_id == cycle.id, Attempt.result == "incorrect")
        )
    )
    patterns = []
    if incorrect:
        concept_counts: dict[str, int] = {}
        for _, exercise in incorrect:
            concept_counts[exercise.concept_id] = concept_counts.get(exercise.concept_id, 0) + 1
        focus = max(concept_counts, key=concept_counts.get)
        patterns.append(
            {
                "text": f"{concept_counts[focus]} submitted response(s) on {focus.replace('-', ' ')} need reinforcement; this is an observed pattern, not a diagnosis.",
                "attempt_ids": [attempt.id for attempt, exercise in incorrect if exercise.concept_id == focus],
            }
        )
    missing = [db.get(User, a.learner_id) for a in assignments if a.state == "not_started"]
    focus = max(concept_counts, key=concept_counts.get) if incorrect else (cycle.concepts[-1] if cycle.concepts else None)
    titles = {concept_id: title for concept_id, title, *_ in CONCEPTS}
    return {
        "cycle_id": cycle.id,
        "completion": {"total": len(assignments), **counts},
        "patterns": patterns,
        "missing_learners": [user_json(user) for user in missing],
        "opening_activity": {
            "title": f"{titles.get(focus, focus.replace('-', ' ') if focus else 'Objective')} check",
            "reason": (
                f"Start with the {focus.replace('-', ' ')} pattern supported by submitted attempts."
                if incorrect
                else "There is no response pattern yet, so begin with a brief objective check."
            ),
        }
        if assignments
        else None,
    }

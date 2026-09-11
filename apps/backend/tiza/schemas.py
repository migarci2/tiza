from datetime import datetime

from pydantic import BaseModel, Field


class RequestCode(BaseModel):
    email: str


class DemoAccess(BaseModel):
    code: str = Field(min_length=6, max_length=64)


class VerifyCode(RequestCode):
    code: str
    invite_token: str | None = None


class DemoSwitch(BaseModel):
    user_id: str


class ClassroomCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    language: str = "en"
    practice_minutes: int = Field(default=15, ge=5, le=60)


class WorkspaceUpdate(BaseModel):
    timezone: str = Field(min_length=1, max_length=64)


class InvitationCreate(BaseModel):
    email: str


class CycleCreate(BaseModel):
    classroom_id: str
    objective: str = Field(min_length=3, max_length=1000)
    concepts: list[str] = []
    closes_at: datetime
    budget_minutes: int = Field(ge=5, le=60)


class ConceptConfirm(BaseModel):
    concept_ids: list[str] = Field(min_length=1, max_length=12)


class DraftChange(BaseModel):
    id: str
    excluded: bool | None = None
    exercise_ids: list[str] | None = None


class DraftUpdate(BaseModel):
    version: int
    assignments: list[DraftChange]


class CycleUpdate(BaseModel):
    version: int
    closes_at: datetime | None = None
    budget_minutes: int | None = Field(default=None, ge=5, le=60)


class ApproveRequest(BaseModel):
    version: int
    assignment_ids: list[str] = Field(min_length=1)
    allow_reminder: bool = False


class PublishRequest(BaseModel):
    approval_id: str
    version: int


class AttemptCreate(BaseModel):
    item_id: str
    response: str = Field(max_length=4000)
    client_key: str = Field(min_length=8, max_length=128)


class ReviewCreate(BaseModel):
    outcome: str
    feedback: str = Field(max_length=2000)

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ...db import get_db
from ...security import Principal, require_principal
from .readiness import accept_readiness, create_readiness_request, revoke_grant
from .receipts import export_receipt

router = APIRouter(tags=["nema"])


class Requirement(BaseModel):
    concept: str = Field(min_length=1, max_length=120)
    ability: Literal["recognize", "retrieve", "explain", "apply", "transfer", "discriminate"]


class RequestCreate(BaseModel):
    cycle_id: str
    purpose: str = Field(default="Plan the next approved practice", min_length=3, max_length=200)
    requirements: list[Requirement] = Field(min_length=1, max_length=12)


class AssertionAccept(BaseModel):
    token: str = Field(min_length=10, max_length=65536)
    confirm_unknown_key: bool = False


@router.post("/api/integrations/nema/readiness/request")
def request_readiness(body: RequestCreate, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    record = create_readiness_request(
        db,
        principal,
        cycle_id=body.cycle_id,
        requirements=[item.model_dump() for item in body.requirements],
        purpose=body.purpose,
    )
    db.commit()
    return {"id": record.id, "request": record.request_json, "request_hash": record.request_hash, "expires_at": record.expires_at}


@router.post("/api/integrations/nema/readiness")
def receive_readiness(body: AssertionAccept, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    grant = accept_readiness(db, principal, token=body.token, confirm_unknown_key=body.confirm_unknown_key)
    db.commit()
    return {"grant_id": grant.id, "scope": grant.scope, "expires_at": grant.expires_at}


@router.delete("/api/integrations/nema/grants/{grant_id}")
def delete_grant(grant_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    grant = revoke_grant(db, principal, grant_id)
    db.commit()
    return {"grant_id": grant.id, "revoked": True}


@router.get("/api/attempts/{attempt_id}/receipt")
def get_receipt(attempt_id: str, principal: Principal = Depends(require_principal), db: Session = Depends(get_db)):
    return export_receipt(db, principal, attempt_id)

"""Atomic daily admission limits; independent of the resettable demo ledger."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from .models import UsageBucket


def reserve_daily(db: Session, scope: str, limit: int) -> None:
    now = datetime.now(timezone.utc)
    key = f"{now.date().isoformat()}:{scope}"
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    db.execute(insert(UsageBucket).values(key=key, used=0).on_conflict_do_nothing())
    reserved = db.execute(update(UsageBucket).where(
        UsageBucket.key == key, UsageBucket.used < limit,
    ).values(used=UsageBucket.used + 1))
    if not reserved.rowcount:
        retry_after = 86400 - (now.hour * 3600 + now.minute * 60 + now.second)
        raise HTTPException(429, "Daily workspace limit reached. Try again tomorrow.",
                            headers={"Retry-After": str(retry_after)})

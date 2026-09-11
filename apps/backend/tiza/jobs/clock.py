from datetime import datetime, timedelta, timezone

from tiza.models import Organization


def organization_now(db, organization_id: str, *, base: datetime | None = None) -> datetime:
    at = base or datetime.now(timezone.utc)
    organization = db.get(Organization, organization_id)
    return at + timedelta(seconds=organization.demo_offset_seconds if organization and organization.demo else 0)

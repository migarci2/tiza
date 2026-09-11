"""Keep classroom data out of Supabase's direct browser Data API."""
from alembic import op
import sqlalchemy as sa

revision = "72a960b13efa"
down_revision = "4f07c8d91a20"
branch_labels = None
depends_on = None

TABLES = (
    "organizations", "users", "memberships", "classrooms", "enrollments", "invitations",
    "learning_cycles", "materials", "exercise_versions", "assignments", "assignment_items",
    "approvals", "attempts", "assistance_events", "evidence_events", "deliveries", "jobs",
    "outbox_events", "audit_events", "web_sessions", "nema_readiness_requests", "nema_grants",
    "idempotency_records",
)


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name != "postgresql":
        return
    roles = set(connection.execute(sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")).scalars())
    for table in TABLES:
        # Table owners/migration roles may bypass RLS; scoped backend authorization is still mandatory.
        connection.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
        connection.execute(sa.text(f'REVOKE ALL ON TABLE "{table}" FROM PUBLIC'))
        for role in roles:
            connection.execute(sa.text(f'REVOKE ALL ON TABLE "{table}" FROM "{role}"'))


def downgrade():
    # Never reopen classroom tables as a side effect of a rollback.
    pass

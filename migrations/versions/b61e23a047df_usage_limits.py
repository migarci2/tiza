"""Persist admission reservations independently of demo resets."""
from alembic import op
import sqlalchemy as sa

revision = "b61e23a047df"
down_revision = "d7c3b922a184"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("usage_buckets", sa.Column("key", sa.String(), primary_key=True),
                    sa.Column("used", sa.Integer(), nullable=False))
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text('ALTER TABLE usage_buckets ENABLE ROW LEVEL SECURITY'))
        connection.execute(sa.text('REVOKE ALL ON TABLE usage_buckets FROM PUBLIC'))
        roles = connection.execute(sa.text("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")).scalars()
        for role in roles:
            connection.execute(sa.text(f'REVOKE ALL ON TABLE usage_buckets FROM "{role}"'))


def downgrade():
    op.drop_table("usage_buckets")

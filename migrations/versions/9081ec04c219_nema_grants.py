"""nema_grants

Revision ID: 9081ec04c219
Revises: c4e42643ed95
Create Date: 2026-09-10 22:54:31.087781
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9081ec04c219'
down_revision: Union[str, Sequence[str], None] = 'c4e42643ed95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nema_readiness_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("learner_id", sa.String(), nullable=False),
        sa.Column("cycle_id", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["learner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["cycle_id"], ["learning_cycles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("organization_id", "learner_id", "cycle_id", "request_hash"):
        op.create_index(f"ix_nema_readiness_requests_{column}", "nema_readiness_requests", [column])
    op.create_table(
        "nema_grants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("learner_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("learner_key_id", sa.String(), nullable=False),
        sa.Column("vault_key", sa.JSON(), nullable=False),
        sa.Column("scope", sa.JSON(), nullable=False),
        sa.Column("assertions", sa.JSON(), nullable=False),
        sa.Column("purpose", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["learner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["nema_readiness_requests.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )
    for column in ("organization_id", "learner_id", "learner_key_id"):
        op.create_index(f"ix_nema_grants_{column}", "nema_grants", [column])


def downgrade() -> None:
    op.drop_table("nema_grants")
    op.drop_table("nema_readiness_requests")

"""Explicit synthetic demo clock.

Revision ID: 4f07c8d91a20
Revises: 03381356fb13
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "4f07c8d91a20"
down_revision: Union[str, Sequence[str], None] = "03381356fb13"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("demo_offset_seconds", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("organizations", "demo_offset_seconds")

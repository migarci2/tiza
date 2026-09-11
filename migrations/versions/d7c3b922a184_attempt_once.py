"""One submitted response per assignment item.

Revision ID: d7c3b922a184
Revises: 72a960b13efa
"""
from typing import Sequence, Union

from alembic import op

revision: str = "d7c3b922a184"
down_revision: Union[str, Sequence[str], None] = "72a960b13efa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("attempts") as batch:
        batch.create_unique_constraint("uq_attempt_assignment_item", ["assignment_id", "item_id"])


def downgrade() -> None:
    with op.batch_alter_table("attempts") as batch:
        batch.drop_constraint("uq_attempt_assignment_item", type_="unique")

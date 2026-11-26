"""Deleting inactive accounts (users.inactivity_warned_at); deleted accounts lose their e-mail address

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-26 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("inactivity_warned_at", sa.DateTime(), nullable=True))
    # Up to 0.9, deleting an account kept its e-mail address; remove it from those accounts
    op.execute("UPDATE users SET email = NULL WHERE deleted_at IS NOT NULL")


def downgrade() -> None:
    # The removed addresses do not come back
    with op.batch_alter_table("users") as batch:
        batch.drop_column("inactivity_warned_at")

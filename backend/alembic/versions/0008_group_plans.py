"""Hosting: a plan per group (plan, plan_until, plan_note)

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-26 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("groups") as batch:
        batch.add_column(sa.Column("plan", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("plan_until", sa.Date(), nullable=True))
        batch.add_column(sa.Column("plan_note", sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("groups") as batch:
        batch.drop_column("plan_note")
        batch.drop_column("plan_until")
        batch.drop_column("plan")

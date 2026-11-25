"""Reservations of cars

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-26 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("car_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint("ends_at > starts_at", name="ck_reservation_period"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["car_id"], ["cars.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_reservations_group_id", "reservations", ["group_id"], unique=False)
    op.create_index("ix_reservations_user_id", "reservations", ["user_id"], unique=False)
    op.create_index("ix_reservations_car_start", "reservations", ["car_id", "starts_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reservations_car_start", table_name="reservations")
    op.drop_index("ix_reservations_user_id", table_name="reservations")
    op.drop_index("ix_reservations_group_id", table_name="reservations")
    op.drop_table("reservations")

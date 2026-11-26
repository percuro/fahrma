"""Receipt photos (receipts) attached to fuel entries and expenses

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-26 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("fuel_id", sa.Integer(), nullable=True),
        sa.Column("expense_id", sa.Integer(), nullable=True),
        sa.Column("file", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=20), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.CheckConstraint("(fuel_id IS NULL) != (expense_id IS NULL)", name="ck_receipt_owner"),
        sa.CheckConstraint("bytes > 0", name="ck_receipt_bytes"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["fuel_id"], ["fuel_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file"),
    )
    op.create_index("ix_receipts_group_id", "receipts", ["group_id"])
    op.create_index("ix_receipts_fuel_id", "receipts", ["fuel_id"])
    op.create_index("ix_receipts_expense_id", "receipts", ["expense_id"])


def downgrade() -> None:
    # The photo files stay in the receipts directory; without the table nothing points to them
    op.drop_index("ix_receipts_expense_id", table_name="receipts")
    op.drop_index("ix_receipts_fuel_id", table_name="receipts")
    op.drop_index("ix_receipts_group_id", table_name="receipts")
    op.drop_table("receipts")

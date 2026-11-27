"""Security log: logins and changes to accounts

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-27 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "security_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("event", sa.String(length=48), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_username", sa.String(length=80), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("target_username", sa.String(length=80), nullable=True),
        sa.Column("ip_prefix", sa.String(length=64), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_security_events_created_at", "security_events", ["created_at"])
    op.create_index("ix_security_events_event", "security_events", ["event"])
    op.create_index("ix_security_events_actor_user_id", "security_events", ["actor_user_id"])
    op.create_index("ix_security_events_target_user_id", "security_events", ["target_user_id"])


def downgrade() -> None:
    op.drop_index("ix_security_events_target_user_id", table_name="security_events")
    op.drop_index("ix_security_events_actor_user_id", table_name="security_events")
    op.drop_index("ix_security_events_event", table_name="security_events")
    op.drop_index("ix_security_events_created_at", table_name="security_events")
    op.drop_table("security_events")

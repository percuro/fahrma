"""Accounts: instance roles, device list, anonymous deletion, admin invitations

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-25 08:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("role", sa.String(length=16), server_default="user", nullable=False))
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(), nullable=True))
    # The oldest active account administers the instance (normally the one from the setup)
    op.execute(
        "UPDATE users SET role = 'admin' WHERE id = "
        "(SELECT id FROM users WHERE is_active = 1 ORDER BY created_at, id LIMIT 1)"
    )
    with op.batch_alter_table("user_sessions") as batch:
        batch.add_column(sa.Column("last_seen_at", sa.DateTime(), nullable=True))
        batch.add_column(sa.Column("user_agent", sa.String(length=255), nullable=True))
    op.create_table(
        "invitations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=True),
        sa.Column("target_user_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(length=80), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("used_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["used_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("invitations") as batch:
        batch.create_index("ix_invitations_token_hash", ["token_hash"], unique=True)
        batch.create_index("ix_invitations_target_user_id", ["target_user_id"], unique=False)
        batch.create_index("ix_invitations_created_by_user_id", ["created_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("invitations")
    with op.batch_alter_table("user_sessions") as batch:
        batch.drop_column("user_agent")
        batch.drop_column("last_seen_at")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("deleted_at")
        batch.drop_column("last_seen_at")
        batch.drop_column("role")

"""Login via OpenID Connect: linked identities, started logins, how a session was started

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-27 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oidc_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("preferred_username", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("issuer", "subject", name="uq_oidc_identities_issuer_subject"),
    )
    op.create_index("ix_oidc_identities_user_id", "oidc_identities", ["user_id"], unique=True)
    op.create_table(
        "oidc_login_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("invitation_id", sa.Integer(), nullable=True),
        sa.Column("invite_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("return_to", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["user_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invitation_id"], ["invitations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["invite_id"], ["invites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_oidc_login_states_state_hash", "oidc_login_states", ["state_hash"], unique=True)
    op.create_index("ix_oidc_login_states_expires_at", "oidc_login_states", ["expires_at"])
    with op.batch_alter_table("user_sessions") as batch:
        batch.add_column(sa.Column("auth_method", sa.String(length=16), server_default="password", nullable=False))
        batch.add_column(sa.Column("authenticated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Accounts that only log in through the provider keep "!" as password and need a reset link
    with op.batch_alter_table("user_sessions") as batch:
        batch.drop_column("authenticated_at")
        batch.drop_column("auth_method")
    op.drop_index("ix_oidc_login_states_expires_at", table_name="oidc_login_states")
    op.drop_index("ix_oidc_login_states_state_hash", table_name="oidc_login_states")
    op.drop_table("oidc_login_states")
    op.drop_index("ix_oidc_identities_user_id", table_name="oidc_identities")
    op.drop_table("oidc_identities")

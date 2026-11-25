"""Group import and e-mail: placeholder members, personal group links, e-mail addresses

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-25 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch.add_column(sa.Column("placeholder", sa.Boolean(), server_default="0", nullable=False))
        batch.create_index("ix_users_email", ["email"], unique=True)
    with op.batch_alter_table("invites") as batch:
        batch.add_column(sa.Column("placeholder_user_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch.create_index("ix_invites_placeholder_user_id", ["placeholder_user_id"], unique=False)
        batch.create_foreign_key(
            "fk_invites_placeholder_user_id_users", "users", ["placeholder_user_id"], ["id"], ondelete="CASCADE"
        )
    with op.batch_alter_table("invitations") as batch:
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=True))
        batch.add_column(sa.Column("username", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("display_name", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("locale", sa.String(length=5), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("invitations") as batch:
        batch.drop_column("locale")
        batch.drop_column("password_hash")
        batch.drop_column("display_name")
        batch.drop_column("username")
        batch.drop_column("email")
    with op.batch_alter_table("invites") as batch:
        batch.drop_constraint("fk_invites_placeholder_user_id_users", type_="foreignkey")
        batch.drop_index("ix_invites_placeholder_user_id")
        batch.drop_column("email")
        batch.drop_column("placeholder_user_id")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_email")
        batch.drop_column("placeholder")
        batch.drop_column("email")

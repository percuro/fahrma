"""Language per user, time zone per group, energy unit per car

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-24 23:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("locale", sa.String(length=5), nullable=True))
    with op.batch_alter_table("groups") as batch:
        batch.add_column(sa.Column("timezone", sa.String(length=64), nullable=True))
    with op.batch_alter_table("cars") as batch:
        batch.add_column(sa.Column("energy_unit", sa.String(length=8), server_default="l", nullable=False))
        batch.create_check_constraint("ck_car_energy_unit", "energy_unit IN ('l', 'kWh')")
    # Fuel entries of electric cars hold watt hours, so the column is no longer "litres"
    with op.batch_alter_table("fuel_entries") as batch:
        batch.alter_column("liters_ml", new_column_name="quantity_milli")


def downgrade() -> None:
    with op.batch_alter_table("fuel_entries") as batch:
        batch.alter_column("quantity_milli", new_column_name="liters_ml")
    with op.batch_alter_table("cars") as batch:
        batch.drop_constraint("ck_car_energy_unit", type_="check")
        batch.drop_column("energy_unit")
    with op.batch_alter_table("groups") as batch:
        batch.drop_column("timezone")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("locale")

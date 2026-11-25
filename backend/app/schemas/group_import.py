"""The format "fahrma-group/1" as read by the import (written by app/services/group_export.py).

Unknown fields are ignored, so later 0.x versions can add fields without breaking older
importers. Lengths and ranges follow the database columns.
"""

import datetime as dt
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.expense import ALLOCATIONS, CATEGORIES

FORMAT = "fahrma-group/1"

CategoryLiteral = Literal[CATEGORIES]  # type: ignore[valid-type]
AllocationLiteral = Literal[ALLOCATIONS]  # type: ignore[valid-type]


class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ImportGroup(_Row):
    name: str = Field(min_length=1, max_length=80)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    timezone: str | None = Field(default=None, max_length=64)
    created_at: dt.datetime | None = None


class ImportMember(_Row):
    user_id: int
    display_name: str = Field(min_length=1, max_length=80)
    role: Literal["admin", "member"]
    active: bool
    deleted: bool = False
    joined_at: dt.datetime | None = None


class ImportCar(_Row):
    id: int
    name: str = Field(min_length=1, max_length=80)
    plate: str | None = Field(default=None, max_length=20)
    start_odometer_km: int = Field(ge=0)
    energy_unit: Literal["l", "kWh"] = "l"
    archived: bool = False
    created_at: dt.datetime | None = None


class ImportTrip(_Row):
    id: int
    car_id: int
    date: dt.date
    start_km: int = Field(ge=0)
    end_km: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=200)
    created_by: int
    settlement_id: int | None = None
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None


class ImportTripShare(_Row):
    trip_id: int
    user_id: int
    weight: int = Field(ge=1)


class ImportExternalPayment(_Row):
    trip_id: int
    payer_name: str = Field(min_length=1, max_length=80)
    amount_cents: int = Field(gt=0)
    received_by_user_id: int


class ImportFuel(_Row):
    id: int
    car_id: int
    date: dt.date
    odometer_km: int | None = Field(default=None, ge=0)
    quantity_milli: int | None = Field(default=None, ge=0)
    amount_cents: int = Field(gt=0)
    paid_by_user_id: int
    full_tank: bool = True
    note: str | None = Field(default=None, max_length=200)
    created_by: int
    settlement_id: int | None = None
    created_at: dt.datetime | None = None


class ImportExpense(_Row):
    id: int
    car_id: int | None = None
    trip_id: int | None = None
    date: dt.date
    category: CategoryLiteral
    description: str | None = Field(default=None, max_length=200)
    amount_cents: int = Field(gt=0)
    paid_by_user_id: int
    allocation: AllocationLiteral
    allocated_user_id: int | None = None
    created_by: int
    settlement_id: int | None = None
    created_at: dt.datetime | None = None


class ImportSettlement(_Row):
    id: int
    period_start: dt.date | None = None
    period_end: dt.date
    created_by: int
    snapshot: dict[str, Any]
    created_at: dt.datetime | None = None


class ImportTransfer(_Row):
    id: int | None = None
    settlement_id: int
    from_user_id: int
    to_user_id: int
    amount_cents: int = Field(gt=0)
    paid_at: dt.datetime | None = None
    confirmed_by: int | None = None


class ImportReservation(_Row):
    """Since 0.7; times in naive UTC like every timestamp of the file."""

    id: int
    car_id: int
    user_id: int
    starts_at: dt.datetime
    ends_at: dt.datetime
    note: str | None = Field(default=None, max_length=200)
    created_by: int
    created_at: dt.datetime | None = None
    updated_at: dt.datetime | None = None


class ImportAuditEntry(_Row):
    user_id: int
    entity: str = Field(min_length=1, max_length=20)
    entity_id: int
    action: str = Field(min_length=1, max_length=20)
    diff: Any = None
    created_at: dt.datetime | None = None


class GroupExportFile(_Row):
    format: str
    app_version: str | None = Field(default=None, max_length=40)
    exported_at: dt.datetime | None = None
    group: ImportGroup
    members: list[ImportMember] = Field(min_length=1)
    cars: list[ImportCar] = []
    trips: list[ImportTrip] = []
    trip_shares: list[ImportTripShare] = []
    trip_external_payments: list[ImportExternalPayment] = []
    fuel: list[ImportFuel] = []
    expenses: list[ImportExpense] = []
    settlements: list[ImportSettlement] = []
    settlement_transfers: list[ImportTransfer] = []
    reservations: list[ImportReservation] = []
    audit_log: list[ImportAuditEntry] = []


class ImportMemberPreview(BaseModel):
    user_id: int
    display_name: str
    role: str
    active: bool
    deleted: bool


class ImportCounts(BaseModel):
    cars: int
    trips: int
    fuel: int
    expenses: int
    settlements: int
    reservations: int = 0


class ImportPreview(BaseModel):
    """What the file contains, shown before importing; the person picks themselves among the members."""

    app_version: str | None
    exported_at: dt.datetime | None
    name: str
    currency: str
    timezone: str | None
    members: list[ImportMemberPreview]
    counts: ImportCounts
    first_date: dt.date | None
    last_date: dt.date | None

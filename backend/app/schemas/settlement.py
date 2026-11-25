import datetime as dt

from pydantic import BaseModel


class Warning(BaseModel):
    code: str  # km_gap | carried_fuel | carried_expense | open_trip
    message: str  # English fallback; clients translate code + params
    params: dict = {}
    car_id: int | None = None
    from_km: int | None = None
    to_km: int | None = None
    blocking: bool = False


class CarBalance(BaseModel):
    car_id: int
    name: str
    km: int
    fuel_cents: int
    rate_cents_per_km: float | None
    last_rate_cents_per_km: float | None
    carried_fuel_cents: int


class MemberBalance(BaseModel):
    user_id: int
    display_name: str
    km: float
    paid_cents: int
    trip_cost_cents: int
    external_credit_cents: int
    external_held_cents: int
    expense_cost_cents: int
    balance_cents: int


class TransferRead(BaseModel):
    id: int | None = None
    from_user_id: int
    to_user_id: int
    amount_cents: int
    paid_at: dt.datetime | None = None
    settlement_id: int | None = None


class BalanceRead(BaseModel):
    period_start: dt.date | None
    period_end: dt.date
    cars: list[CarBalance]
    members: list[MemberBalance]
    transfers: list[TransferRead]
    warnings: list[Warning]
    trip_count: int
    fuel_count: int
    expense_count: int
    total_cost_cents: int


class SettlementCreate(BaseModel):
    period_end: dt.date
    accept_warnings: bool = False


class SettlementRead(BaseModel):
    id: int
    period_start: dt.date | None
    period_end: dt.date
    created_by: int
    created_at: dt.datetime
    result: BalanceRead
    transfers: list[TransferRead]
    is_latest: bool


class SettlementBrief(BaseModel):
    id: int
    period_start: dt.date | None
    period_end: dt.date
    created_at: dt.datetime
    total_cost_cents: int
    open_transfers: int

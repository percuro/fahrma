import datetime as dt

from pydantic import BaseModel, Field, field_validator

MAX_CENTS = 10_000_000  # 100,000 in the group's currency
MAX_KM = 5_000_000


class ShareIn(BaseModel):
    user_id: int
    weight: int = Field(default=1, ge=1, le=100)


class ExternalIn(BaseModel):
    payer_name: str = Field(min_length=1, max_length=80)
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    received_by_user_id: int


class TripWrite(BaseModel):
    car_id: int
    date: dt.date
    start_km: int = Field(ge=0, le=MAX_KM)
    end_km: int | None = Field(default=None, ge=0, le=MAX_KM)
    note: str | None = Field(default=None, max_length=200)
    shares: list[ShareIn] = Field(min_length=1, max_length=50)
    external: list[ExternalIn] = Field(default_factory=list, max_length=20)

    @field_validator("shares")
    @classmethod
    def unique_users(cls, shares: list[ShareIn]) -> list[ShareIn]:
        if len({share.user_id for share in shares}) != len(shares):
            raise ValueError("Each person may appear only once")
        return shares


class TripFinish(BaseModel):
    end_km: int = Field(ge=0, le=MAX_KM)


class ShareRead(BaseModel):
    user_id: int
    weight: int


class ExternalRead(BaseModel):
    id: int
    payer_name: str
    amount_cents: int
    received_by_user_id: int


class TripRead(BaseModel):
    id: int
    car_id: int
    date: dt.date
    start_km: int
    end_km: int | None
    km: int | None
    note: str | None
    shares: list[ShareRead]
    external: list[ExternalRead]
    created_by: int
    settlement_id: int | None
    cost_cents: int | None  # final once settled, otherwise estimated with the current rate
    cost_is_estimate: bool


class FuelWrite(BaseModel):
    car_id: int
    date: dt.date
    odometer_km: int | None = Field(default=None, ge=0, le=MAX_KM)
    # thousandths of the car's energy unit (ml or Wh)
    quantity_milli: int | None = Field(default=None, gt=0, le=10_000_000)
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    paid_by_user_id: int
    full_tank: bool = True
    note: str | None = Field(default=None, max_length=200)


class FuelRead(FuelWrite):
    id: int
    created_by: int
    settlement_id: int | None


class ExpenseWrite(BaseModel):
    car_id: int | None = None
    trip_id: int | None = None
    date: dt.date
    category: str = Field(pattern=r"^(insurance|tax|service|repair|inspection|tires|vignette|parking|toll|wash|other)$")
    description: str | None = Field(default=None, max_length=200)
    amount_cents: int = Field(gt=0, le=MAX_CENTS)
    paid_by_user_id: int
    allocation: str = Field(pattern=r"^(by_km|equal|single|trip)$")
    allocated_user_id: int | None = None


class ExpenseRead(ExpenseWrite):
    id: int
    created_by: int
    settlement_id: int | None

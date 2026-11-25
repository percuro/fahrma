from pydantic import BaseModel


class Consumption(BaseModel):
    """Sums over the intervals between two full tanks (or full charges) that end in the period."""

    milli: int  # thousandths of the car's energy unit (ml or Wh)
    km: int
    cents: int
    intervals: int


class CategoryCost(BaseModel):
    category: str
    cents: int


class MemberKm(BaseModel):
    user_id: int
    km: int


class PeriodStats(BaseModel):
    period: str  # "2026-03" within a year, "2026" for all years
    km: int
    fuel_cents: int
    expense_cents: int


class CarStats(BaseModel):
    car_id: int
    energy_unit: str
    year: int | None
    years: list[int]
    km: int
    trips: int
    fuel_cents: int
    fuel_entries: int
    # entries with a quantity, for the average price per litre or kWh
    priced_milli: int
    priced_cents: int
    consumption: Consumption | None
    expense_cents: int
    categories: list[CategoryCost]
    members: list[MemberKm]
    periods: list[PeriodStats]

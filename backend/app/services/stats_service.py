"""Statistics per car: distance, consumption and costs, by year and month.

Only for looking at: the settlement never uses these numbers. Ratios (litres per 100 km,
cost per km) are left to the interface, the API returns exact sums.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from fractions import Fraction

from sqlalchemy.orm import selectinload

from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.trip import Trip
from app.schemas.stats import CarStats, CategoryCost, Consumption, MemberKm, PeriodStats
from app.services.access import GroupContext
from app.services.car_service import get_car


@dataclass(frozen=True)
class Interval:
    end: date
    km: int
    milli: int
    cents: int


def consumption_intervals(entries: list[FuelEntry]) -> list[Interval]:
    """Full-to-full: what was put in after one full tank up to and including the next full tank,
    divided by the km between their odometer readings.

    An interval only counts when every entry in it is known: all entries between the two
    readings have a quantity, and no entry without an odometer reading lies in its date range
    (it could belong to the interval, or not).
    """
    with_km = sorted((e for e in entries if e.odometer_km is not None), key=lambda e: (e.odometer_km, e.date, e.id))
    without_km = [e for e in entries if e.odometer_km is None]
    anchors = [e for e in with_km if e.full_tank]
    intervals = []
    for previous, current in zip(anchors, anchors[1:], strict=False):
        km = current.odometer_km - previous.odometer_km
        if km <= 0 or current.date < previous.date:
            continue
        inside = [e for e in with_km if previous.odometer_km < e.odometer_km <= current.odometer_km]
        if any(e.quantity_milli is None for e in inside):
            continue
        if any(previous.date <= e.date <= current.date for e in without_km):
            continue
        intervals.append(
            Interval(
                end=current.date,
                km=km,
                milli=sum(e.quantity_milli for e in inside),
                cents=sum(e.amount_cents for e in inside),
            )
        )
    return intervals


def split_km(trips: list[Trip]) -> dict[int, int]:
    """Km per person, shared trips split by weight; whole km by largest remainder, so they add up."""
    exact: dict[int, Fraction] = defaultdict(Fraction)
    for trip in trips:
        total = sum(s.weight for s in trip.shares)
        for share in trip.shares:
            exact[share.user_id] += Fraction(trip.km * share.weight, total)
    floors = {uid: value.numerator // value.denominator for uid, value in exact.items()}
    missing = sum(t.km for t in trips) - sum(floors.values())
    for uid in sorted(exact, key=lambda uid: (-(exact[uid] - floors[uid]), uid))[:missing]:
        floors[uid] += 1
    return floors


def car_stats(ctx: GroupContext, car_id: int, year: int | None) -> CarStats:
    car = get_car(ctx, car_id)
    all_trips = (
        ctx.db.query(Trip)
        .options(selectinload(Trip.shares))
        .filter(Trip.group_id == ctx.group.id, Trip.car_id == car.id, Trip.end_km.is_not(None))
        .all()
    )
    all_fuel = ctx.db.query(FuelEntry).filter(FuelEntry.group_id == ctx.group.id, FuelEntry.car_id == car.id).all()
    all_expenses = ctx.db.query(Expense).filter(Expense.group_id == ctx.group.id, Expense.car_id == car.id).all()

    years = sorted({item.date.year for item in (*all_trips, *all_fuel, *all_expenses)})

    def in_period(day: date) -> bool:
        return year is None or day.year == year

    trips = [t for t in all_trips if in_period(t.date)]
    fuel = [e for e in all_fuel if in_period(e.date)]
    expenses = [e for e in all_expenses if in_period(e.date)]
    intervals = [i for i in consumption_intervals(all_fuel) if in_period(i.end)]

    def period_of(day: date) -> str:
        return f"{day.year:04d}-{day.month:02d}" if year is not None else f"{day.year:04d}"

    labels = [f"{year:04d}-{month:02d}" for month in range(1, 13)] if year is not None else [str(y) for y in years]
    periods = {label: {"km": 0, "fuel_cents": 0, "expense_cents": 0} for label in labels}
    for trip in trips:
        periods[period_of(trip.date)]["km"] += trip.km
    for entry in fuel:
        periods[period_of(entry.date)]["fuel_cents"] += entry.amount_cents
    for entry in expenses:
        periods[period_of(entry.date)]["expense_cents"] += entry.amount_cents

    categories: dict[str, int] = defaultdict(int)
    for entry in expenses:
        categories[entry.category] += entry.amount_cents
    priced = [e for e in fuel if e.quantity_milli is not None]
    members = split_km(trips)

    return CarStats(
        car_id=car.id,
        energy_unit=car.energy_unit,
        year=year,
        years=years,
        km=sum(t.km for t in trips),
        trips=len(trips),
        fuel_cents=sum(e.amount_cents for e in fuel),
        fuel_entries=len(fuel),
        priced_milli=sum(e.quantity_milli for e in priced),
        priced_cents=sum(e.amount_cents for e in priced),
        consumption=Consumption(
            milli=sum(i.milli for i in intervals),
            km=sum(i.km for i in intervals),
            cents=sum(i.cents for i in intervals),
            intervals=len(intervals),
        )
        if intervals
        else None,
        expense_cents=sum(e.amount_cents for e in expenses),
        categories=[
            CategoryCost(category=c, cents=cents)
            for c, cents in sorted(categories.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        members=[MemberKm(user_id=uid, km=km) for uid, km in sorted(members.items(), key=lambda kv: (-kv[1], kv[0]))],
        periods=[PeriodStats(period=label, **values) for label, values in periods.items()],
    )

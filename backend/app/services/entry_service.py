"""Create, change and delete trips, fuel entries and other expenses."""

from fastapi import status
from sqlalchemy.orm import selectinload

from app.errors import AppError
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.trip import Trip, TripExternalPayment, TripShare
from app.schemas.entries import ExpenseWrite, FuelWrite, TripWrite
from app.services import idempotency, receipt_store
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.car_service import get_car

INF = float("inf")


def not_settled(item) -> None:
    if item.settlement_id is not None:
        raise AppError(
            status.HTTP_409_CONFLICT,
            "already_settled",
            "Already settled; can only be changed after undoing the latest settlement",
        )


# ---------- Trips ----------


def get_trip(ctx: GroupContext, trip_id: int) -> Trip:
    trip = (
        ctx.db.query(Trip)
        .options(selectinload(Trip.shares), selectinload(Trip.external_payments))
        .filter(Trip.id == trip_id, Trip.group_id == ctx.group.id)
        .first()
    )
    if trip is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "trip_not_found", "Trip not found")
    return trip


def _check_km(ctx: GroupContext, car_id: int, start: int, end: int | None, trip_id: int | None) -> None:
    car = get_car(ctx, car_id)
    if start < car.start_odometer_km:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "start_before_car_start",
            f"Start km is below the car's initial odometer reading ({car.start_odometer_km} km)",
            km=car.start_odometer_km,
        )
    if end is not None and end < start:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "end_before_start", "End km is below start km")
    new_end = INF if end is None else end
    others = ctx.db.query(Trip).filter(Trip.car_id == car_id)
    if trip_id is not None:
        others = others.filter(Trip.id != trip_id)
    for other in others:
        other_end = INF if other.end_km is None else other.end_km
        # Half-open ranges [start, end): adjoining trips are allowed
        if start < other_end and other.start_km < new_end and start != new_end and other.start_km != other_end:
            if other.end_km is None:
                raise AppError(
                    status.HTTP_409_CONFLICT,
                    "trip_running",
                    f"A trip from km {other.start_km} is still running; finish it first",
                    start_km=other.start_km,
                )
            raise AppError(
                status.HTTP_409_CONFLICT,
                "trip_overlap",
                f"Overlaps the trip km {other.start_km}-{other.end_km} on {other.date.isoformat()}",
                start_km=other.start_km,
                end_km=other.end_km,
                date=other.date.isoformat(),
            )


def _apply_trip(ctx: GroupContext, trip: Trip, data: TripWrite) -> None:
    ctx.require_members(*(s.user_id for s in data.shares), *(e.received_by_user_id for e in data.external))
    trip.car_id = data.car_id
    trip.date = data.date
    trip.start_km = data.start_km
    trip.end_km = data.end_km
    trip.note = data.note
    if trip.id is not None:
        # Delete the old shares first, otherwise (trip_id, user_id) collides on insert
        trip.shares.clear()
        trip.external_payments.clear()
        ctx.db.flush()
    trip.shares = [TripShare(user_id=s.user_id, weight=s.weight) for s in data.shares]
    trip.external_payments = [
        TripExternalPayment(
            payer_name=e.payer_name.strip(),
            amount_cents=e.amount_cents,
            received_by_user_id=e.received_by_user_id,
        )
        for e in data.external
    ]


def create_trip(ctx: GroupContext, data: TripWrite, key: str | None = None) -> Trip:
    if (earlier := idempotency.previous(ctx, key, "trip")) is not None:
        return idempotency.load(ctx, earlier, get_trip)
    _check_km(ctx, data.car_id, data.start_km, data.end_km, None)
    trip = Trip(group_id=ctx.group.id, created_by=ctx.user.id)
    _apply_trip(ctx, trip, data)
    ctx.db.add(trip)
    ctx.db.flush()
    record(ctx, "trip", trip.id, "create", data.model_dump())
    return get_trip(ctx, idempotency.commit(ctx, key, "trip", trip.id))


def update_trip(ctx: GroupContext, trip_id: int, data: TripWrite) -> Trip:
    trip = get_trip(ctx, trip_id)
    not_settled(trip)
    _check_km(ctx, data.car_id, data.start_km, data.end_km, trip.id)
    _apply_trip(ctx, trip, data)
    record(ctx, "trip", trip.id, "update", data.model_dump())
    ctx.db.commit()
    return get_trip(ctx, trip.id)


def finish_trip(ctx: GroupContext, trip_id: int, end_km: int, key: str | None = None) -> Trip:
    if (earlier := idempotency.previous(ctx, key, "finish")) is not None:
        return idempotency.load(ctx, earlier, get_trip)
    trip = get_trip(ctx, trip_id)
    not_settled(trip)
    if trip.end_km is not None:
        raise AppError(status.HTTP_409_CONFLICT, "trip_already_finished", "Trip is already finished")
    _check_km(ctx, trip.car_id, trip.start_km, end_km, trip.id)
    trip.end_km = end_km
    record(ctx, "trip", trip.id, "finish", {"end_km": end_km})
    return get_trip(ctx, idempotency.commit(ctx, key, "finish", trip.id))


def delete_trip(ctx: GroupContext, trip_id: int) -> None:
    trip = get_trip(ctx, trip_id)
    not_settled(trip)
    if ctx.db.query(Expense.id).filter(Expense.trip_id == trip.id).first():
        raise AppError(status.HTTP_409_CONFLICT, "trip_has_expenses", "Expenses are linked to this trip")
    record(ctx, "trip", trip.id, "delete", {"start_km": trip.start_km, "end_km": trip.end_km})
    ctx.db.delete(trip)
    ctx.db.commit()


def list_trips(ctx: GroupContext, car_id: int | None = None, limit: int = 200) -> list[Trip]:
    query = (
        ctx.db.query(Trip)
        .options(selectinload(Trip.shares), selectinload(Trip.external_payments))
        .filter(Trip.group_id == ctx.group.id)
    )
    if car_id is not None:
        query = query.filter(Trip.car_id == car_id)
    return query.order_by(Trip.date.desc(), Trip.start_km.desc()).limit(limit).all()


# ---------- Fuel ----------


def get_fuel(ctx: GroupContext, fuel_id: int) -> FuelEntry:
    entry = ctx.db.query(FuelEntry).filter(FuelEntry.id == fuel_id, FuelEntry.group_id == ctx.group.id).first()
    if entry is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "fuel_not_found", "Fuel entry not found")
    return entry


def _apply_fuel(ctx: GroupContext, entry: FuelEntry, data: FuelWrite) -> None:
    get_car(ctx, data.car_id)
    ctx.require_members(data.paid_by_user_id)
    for key, value in data.model_dump().items():
        setattr(entry, key, value)


def create_fuel(ctx: GroupContext, data: FuelWrite, key: str | None = None) -> FuelEntry:
    if (earlier := idempotency.previous(ctx, key, "fuel")) is not None:
        return idempotency.load(ctx, earlier, get_fuel)
    entry = FuelEntry(group_id=ctx.group.id, created_by=ctx.user.id)
    _apply_fuel(ctx, entry, data)
    ctx.db.add(entry)
    ctx.db.flush()
    record(ctx, "fuel", entry.id, "create", data.model_dump())
    return get_fuel(ctx, idempotency.commit(ctx, key, "fuel", entry.id))


def update_fuel(ctx: GroupContext, fuel_id: int, data: FuelWrite) -> FuelEntry:
    entry = get_fuel(ctx, fuel_id)
    not_settled(entry)
    _apply_fuel(ctx, entry, data)
    record(ctx, "fuel", entry.id, "update", data.model_dump())
    ctx.db.commit()
    return entry


def delete_fuel(ctx: GroupContext, fuel_id: int) -> None:
    entry = get_fuel(ctx, fuel_id)
    not_settled(entry)
    record(ctx, "fuel", entry.id, "delete", {"amount_cents": entry.amount_cents})
    receipt_store.remove_after_commit(ctx.db, [(r.group_id, r.file) for r in entry.receipts])
    ctx.db.delete(entry)
    ctx.db.commit()


def list_fuel(ctx: GroupContext, limit: int = 200) -> list[FuelEntry]:
    return (
        ctx.db.query(FuelEntry)
        .filter(FuelEntry.group_id == ctx.group.id)
        .order_by(FuelEntry.date.desc(), FuelEntry.id.desc())
        .limit(limit)
        .all()
    )


# ---------- Other expenses ----------


def get_expense(ctx: GroupContext, expense_id: int) -> Expense:
    entry = ctx.db.query(Expense).filter(Expense.id == expense_id, Expense.group_id == ctx.group.id).first()
    if entry is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "expense_not_found", "Expense not found")
    return entry


def _apply_expense(ctx: GroupContext, entry: Expense, data: ExpenseWrite) -> None:
    if data.car_id is not None:
        get_car(ctx, data.car_id)
    ctx.require_members(data.paid_by_user_id, data.allocated_user_id)
    if data.allocation == "single" and data.allocated_user_id is None:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "expense_person_missing", "Choose the person who bears the cost"
        )
    if data.allocation == "trip":
        if data.trip_id is None:
            raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "expense_trip_missing", "Choose the trip")
        trip = get_trip(ctx, data.trip_id)
        if trip.end_km is None:
            raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "expense_trip_running", "The trip is still running")
    values = data.model_dump()
    if data.allocation != "single":
        values["allocated_user_id"] = None
    if data.allocation != "trip":
        values["trip_id"] = None
    for key, value in values.items():
        setattr(entry, key, value)


def create_expense(ctx: GroupContext, data: ExpenseWrite, key: str | None = None) -> Expense:
    if (earlier := idempotency.previous(ctx, key, "expense")) is not None:
        return idempotency.load(ctx, earlier, get_expense)
    entry = Expense(group_id=ctx.group.id, created_by=ctx.user.id)
    _apply_expense(ctx, entry, data)
    ctx.db.add(entry)
    ctx.db.flush()
    record(ctx, "expense", entry.id, "create", data.model_dump())
    return get_expense(ctx, idempotency.commit(ctx, key, "expense", entry.id))


def update_expense(ctx: GroupContext, expense_id: int, data: ExpenseWrite) -> Expense:
    entry = get_expense(ctx, expense_id)
    not_settled(entry)
    _apply_expense(ctx, entry, data)
    record(ctx, "expense", entry.id, "update", data.model_dump())
    ctx.db.commit()
    return entry


def delete_expense(ctx: GroupContext, expense_id: int) -> None:
    entry = get_expense(ctx, expense_id)
    not_settled(entry)
    record(ctx, "expense", entry.id, "delete", {"amount_cents": entry.amount_cents})
    receipt_store.remove_after_commit(ctx.db, [(r.group_id, r.file) for r in entry.receipts])
    ctx.db.delete(entry)
    ctx.db.commit()


def list_expenses(ctx: GroupContext, limit: int = 200) -> list[Expense]:
    return (
        ctx.db.query(Expense)
        .filter(Expense.group_id == ctx.group.id)
        .order_by(Expense.date.desc(), Expense.id.desc())
        .limit(limit)
        .all()
    )

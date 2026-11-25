"""Preview (balance as of now), settling, undoing a settlement, marking transfers as paid."""

import json
from datetime import date

from fastapi import status
from sqlalchemy import func
from sqlalchemy.orm import selectinload

from app.errors import AppError
from app.models.car import Car
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import Membership
from app.models.settlement import Settlement, SettlementTransfer
from app.models.trip import Trip, TripShare
from app.models.user import User
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.auth_service import utcnow
from app.services.settlement_engine import (
    CarResult,
    EngineError,
    EngineResult,
    ExpenseInput,
    FuelInput,
    TripInput,
    calculate,
    to_cents,
)


def _unsettled_until(ctx: GroupContext, model, period_end: date):
    return ctx.db.query(model).filter(
        model.group_id == ctx.group.id, model.settlement_id.is_(None), model.date <= period_end
    )


def _last_rates(ctx: GroupContext) -> dict[int, float]:
    latest = ctx.db.query(Settlement).filter(Settlement.group_id == ctx.group.id).order_by(Settlement.id.desc()).first()
    if latest is None:
        return {}
    snapshot = json.loads(latest.snapshot_json)
    return {
        car["car_id"]: car["rate_cents_per_km"]
        for car in snapshot.get("cars", [])
        if car.get("rate_cents_per_km") is not None
    }


def km_gaps(ctx: GroupContext, period_end: date) -> list[dict]:
    """Gaps between consecutive trips of a car (km not assigned to anyone)."""
    warnings = []
    for car in ctx.db.query(Car).filter(Car.group_id == ctx.group.id):
        trips = ctx.db.query(Trip).filter(Trip.car_id == car.id, Trip.end_km.isnot(None)).order_by(Trip.start_km).all()
        previous_end = car.start_odometer_km
        for trip in trips:
            if trip.start_km > previous_end and trip.settlement_id is None and trip.date <= period_end:
                warnings.append(
                    {
                        "code": "km_gap",
                        "message": f"{car.name}: km {previous_end}-{trip.start_km} is not assigned to a trip",
                        "params": {"car": car.name, "from_km": previous_end, "to_km": trip.start_km},
                        "car_id": car.id,
                        "from_km": previous_end,
                        "to_km": trip.start_km,
                    }
                )
            previous_end = max(previous_end, trip.end_km)
    return warnings


def _compute(ctx: GroupContext, period_end: date):
    trips = (
        _unsettled_until(ctx, Trip, period_end)
        .options(selectinload(Trip.shares), selectinload(Trip.external_payments))
        .order_by(Trip.date, Trip.id)
        .all()
    )
    open_trips = [trip for trip in trips if trip.end_km is None]
    finished = [trip for trip in trips if trip.end_km is not None]
    fuel = _unsettled_until(ctx, FuelEntry, period_end).order_by(FuelEntry.date, FuelEntry.id).all()
    expenses = _unsettled_until(ctx, Expense, period_end).order_by(Expense.date, Expense.id).all()

    trip_share_cache: dict[int, dict[int, int]] = {}

    def shares_of(trip_id: int) -> dict[int, int]:
        if trip_id not in trip_share_cache:
            rows = ctx.db.query(TripShare).filter(TripShare.trip_id == trip_id).all()
            trip_share_cache[trip_id] = {row.user_id: row.weight for row in rows}
        return trip_share_cache[trip_id]

    try:
        result = calculate(
            active_members=sorted(ctx.member_ids(active_only=True)),
            trips=[
                TripInput(
                    id=trip.id,
                    car_id=trip.car_id,
                    km=trip.end_km - trip.start_km,
                    shares={share.user_id: share.weight for share in trip.shares},
                    external=tuple((e.received_by_user_id, e.amount_cents) for e in trip.external_payments),
                )
                for trip in finished
            ],
            fuel=[FuelInput(f.id, f.car_id, f.amount_cents, f.paid_by_user_id) for f in fuel],
            expenses=[
                ExpenseInput(
                    id=e.id,
                    amount_cents=e.amount_cents,
                    paid_by=e.paid_by_user_id,
                    allocation=e.allocation,
                    car_id=e.car_id,
                    allocated_user_id=e.allocated_user_id,
                    trip_shares=shares_of(e.trip_id) if e.trip_id is not None else None,
                )
                for e in expenses
            ],
        )
    except EngineError as exc:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "calculation_failed", str(exc)) from exc

    items_dates = [x.date for x in finished] + [x.date for x in fuel] + [x.date for x in expenses]
    return result, open_trips, finished, fuel, expenses, items_dates


def _serialize(ctx: GroupContext, result: EngineResult, period_start, period_end, warnings) -> dict:
    cars = {car.id: car for car in ctx.db.query(Car).filter(Car.group_id == ctx.group.id)}
    # Show active cars without trips in the period too (last rate as an estimate)
    for car_id, car in cars.items():
        if not car.archived and car_id not in result.cars:
            result.cars[car_id] = CarResult(car_id)
    names = dict(
        ctx.db.query(User.id, User.display_name)
        .join(Membership, Membership.user_id == User.id)
        .filter(Membership.group_id == ctx.group.id)
        .all()
    )
    last_rates = _last_rates(ctx)
    total_cost = sum(c.fuel_cents for c in result.cars.values())
    included_expense_ids = set(result.included_expense_ids)
    if included_expense_ids:
        total_cost += (
            ctx.db.query(func.coalesce(func.sum(Expense.amount_cents), 0))
            .filter(Expense.id.in_(included_expense_ids))
            .scalar()
        )
    return {
        "period_start": period_start,
        "period_end": period_end,
        "cars": [
            {
                "car_id": car_id,
                "name": cars[car_id].name if car_id in cars else "?",
                "km": car.km,
                "fuel_cents": car.fuel_cents,
                "rate_cents_per_km": car.rate_cents_per_km,
                "last_rate_cents_per_km": last_rates.get(car_id),
                "carried_fuel_cents": car.carried_fuel_cents,
            }
            for car_id, car in sorted(result.cars.items())
        ],
        "members": [
            {
                "user_id": uid,
                "display_name": names.get(uid, "?"),
                "km": float(m.km),
                "paid_cents": m.paid_cents,
                "trip_cost_cents": to_cents(m.trip_cost),
                "external_credit_cents": to_cents(m.external_credit),
                "external_held_cents": to_cents(m.external_held),
                "expense_cost_cents": to_cents(m.expense_cost),
                "balance_cents": m.balance_cents,
            }
            for uid, m in sorted(result.members.items(), key=lambda item: names.get(item[0], ""))
        ],
        "transfers": [
            {"from_user_id": t.from_user_id, "to_user_id": t.to_user_id, "amount_cents": t.amount_cents}
            for t in result.transfers
        ],
        "warnings": warnings,
        "trip_count": len(result.included_trip_ids),
        "fuel_count": len(result.included_fuel_ids),
        "expense_count": len(result.included_expense_ids),
        "total_cost_cents": total_cost,
        "trip_costs": {str(tid): to_cents(cost) for tid, cost in result.trip_costs.items()},
    }


def _previous_end(ctx: GroupContext) -> date | None:
    return ctx.db.query(func.max(Settlement.period_end)).filter(Settlement.group_id == ctx.group.id).scalar()


def preview(ctx: GroupContext, period_end: date) -> dict:
    result, open_trips, _finished, _fuel, _expenses, dates = _compute(ctx, period_end)
    warnings = km_gaps(ctx, period_end)
    for trip in open_trips:
        warnings.append(
            {
                "code": "open_trip",
                "message": f"Trip on {trip.date.isoformat()} from km {trip.start_km} is still running",
                "params": {"date": trip.date.isoformat(), "start_km": trip.start_km},
                "car_id": trip.car_id,
                "from_km": trip.start_km,
                "blocking": True,
            }
        )
    car_names = {car.id: car.name for car in ctx.db.query(Car).filter(Car.group_id == ctx.group.id)}
    for car in result.cars.values():
        if car.carried_fuel_cents:
            warnings.append(
                {
                    "code": "carried_fuel",
                    "message": f"{car_names.get(car.car_id, '?')}: fuel costs without driven km; "
                    "carried over to the next settlement",
                    "params": {"car": car_names.get(car.car_id, "?")},
                    "car_id": car.car_id,
                }
            )
    if result.carried_expense_ids:
        warnings.append(
            {
                "code": "carried_expense",
                "message": "Expenses split by km without driven km; carried over to the next settlement",
            }
        )
    previous = _previous_end(ctx)
    period_start = min(dates) if dates else None
    if previous is not None and (period_start is None or period_start > previous):
        period_start = date.fromordinal(previous.toordinal() + 1)
    return _serialize(ctx, result, period_start, period_end, warnings)


def trip_costs(ctx: GroupContext, trips: list[Trip], today: date) -> dict[int, tuple[int | None, bool]]:
    """Cost per trip: from the snapshot when settled, otherwise estimated with the current rate."""
    out: dict[int, tuple[int | None, bool]] = {}
    snapshots: dict[int, dict] = {}
    estimate: dict | None = None
    for trip in trips:
        if trip.end_km is None:
            out[trip.id] = (None, True)
        elif trip.settlement_id is not None:
            if trip.settlement_id not in snapshots:
                settlement = ctx.db.get(Settlement, trip.settlement_id)
                snapshots[trip.settlement_id] = json.loads(settlement.snapshot_json) if settlement else {}
            cost = snapshots[trip.settlement_id].get("trip_costs", {}).get(str(trip.id))
            out[trip.id] = (cost, False)
        else:
            if estimate is None:
                estimate = preview(ctx, max(today, trip.date))
            cost = estimate["trip_costs"].get(str(trip.id))
            if cost is None:
                rates = {c["car_id"]: c["rate_cents_per_km"] or c["last_rate_cents_per_km"] for c in estimate["cars"]}
                rate = rates.get(trip.car_id)
                cost = round(rate * (trip.end_km - trip.start_km)) if rate is not None else None
            out[trip.id] = (cost, True)
    return out


def create_settlement(ctx: GroupContext, period_end: date, today: date, accept_warnings: bool) -> Settlement:
    if period_end > today:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "period_end_future", "The end date is in the future")
    previous = _previous_end(ctx)
    if previous is not None and period_end < previous:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "period_end_before_previous",
            "The end date is before the latest settlement",
            previous=previous.isoformat(),
        )
    data = preview(ctx, period_end)
    if any(w.get("blocking") for w in data["warnings"]):
        raise AppError(status.HTTP_409_CONFLICT, "open_trips", "Trips are still running; finish them first")
    if any(w["code"] == "km_gap" for w in data["warnings"]) and not accept_warnings:
        raise AppError(status.HTTP_409_CONFLICT, "km_gap_unconfirmed", "There are unassigned km; please confirm")
    if data["trip_count"] + data["fuel_count"] + data["expense_count"] == 0:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "nothing_to_settle", "Nothing to settle")

    result, _open, finished, fuel, expenses, _dates = _compute(ctx, period_end)
    settlement = Settlement(
        group_id=ctx.group.id,
        period_start=data["period_start"],
        period_end=period_end,
        created_by=ctx.user.id,
        snapshot_json=json.dumps(data, default=str, ensure_ascii=False),
    )
    ctx.db.add(settlement)
    ctx.db.flush()
    fuel_ids = set(result.included_fuel_ids)
    expense_ids = set(result.included_expense_ids)
    for trip in finished:
        trip.settlement_id = settlement.id
    for entry in fuel:
        if entry.id in fuel_ids:
            entry.settlement_id = settlement.id
    for entry in expenses:
        if entry.id in expense_ids:
            entry.settlement_id = settlement.id
    for transfer in result.transfers:
        ctx.db.add(
            SettlementTransfer(
                settlement_id=settlement.id,
                from_user_id=transfer.from_user_id,
                to_user_id=transfer.to_user_id,
                amount_cents=transfer.amount_cents,
            )
        )
    record(
        ctx,
        "settlement",
        settlement.id,
        "create",
        {"period_end": period_end, "total_cost_cents": data["total_cost_cents"]},
    )
    ctx.db.commit()
    ctx.db.refresh(settlement)
    return settlement


def get_settlement(ctx: GroupContext, settlement_id: int) -> Settlement:
    settlement = (
        ctx.db.query(Settlement)
        .options(selectinload(Settlement.transfers))
        .filter(Settlement.id == settlement_id, Settlement.group_id == ctx.group.id)
        .first()
    )
    if settlement is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "settlement_not_found", "Settlement not found")
    return settlement


def _latest_id(ctx: GroupContext) -> int | None:
    return ctx.db.query(func.max(Settlement.id)).filter(Settlement.group_id == ctx.group.id).scalar()


def _transfer_read(t: SettlementTransfer) -> dict:
    return {
        "id": t.id,
        "from_user_id": t.from_user_id,
        "to_user_id": t.to_user_id,
        "amount_cents": t.amount_cents,
        "paid_at": t.paid_at,
        "settlement_id": t.settlement_id,
    }


def settlement_read(ctx: GroupContext, settlement: Settlement) -> dict:
    return {
        "id": settlement.id,
        "period_start": settlement.period_start,
        "period_end": settlement.period_end,
        "created_by": settlement.created_by,
        "created_at": settlement.created_at,
        "result": json.loads(settlement.snapshot_json),
        "transfers": [_transfer_read(t) for t in settlement.transfers],
        "is_latest": settlement.id == _latest_id(ctx),
    }


def list_settlements(ctx: GroupContext) -> list[dict]:
    settlements = (
        ctx.db.query(Settlement)
        .options(selectinload(Settlement.transfers))
        .filter(Settlement.group_id == ctx.group.id)
        .order_by(Settlement.id.desc())
        .all()
    )
    return [
        {
            "id": s.id,
            "period_start": s.period_start,
            "period_end": s.period_end,
            "created_at": s.created_at,
            "total_cost_cents": json.loads(s.snapshot_json).get("total_cost_cents", 0),
            "open_transfers": sum(1 for t in s.transfers if t.paid_at is None),
        }
        for s in settlements
    ]


def open_transfers(ctx: GroupContext) -> list[dict]:
    rows = (
        ctx.db.query(SettlementTransfer)
        .join(Settlement, Settlement.id == SettlementTransfer.settlement_id)
        .filter(Settlement.group_id == ctx.group.id, SettlementTransfer.paid_at.is_(None))
        .order_by(SettlementTransfer.id)
        .all()
    )
    return [_transfer_read(t) for t in rows]


def delete_latest_settlement(ctx: GroupContext, settlement_id: int) -> None:
    ctx.require_admin()
    settlement = get_settlement(ctx, settlement_id)
    if settlement.id != _latest_id(ctx):
        raise AppError(status.HTTP_409_CONFLICT, "settlement_not_latest", "Only the latest settlement can be undone")
    for model in (Trip, FuelEntry, Expense):
        ctx.db.query(model).filter(model.settlement_id == settlement.id).update(
            {model.settlement_id: None}, synchronize_session=False
        )
    record(ctx, "settlement", settlement.id, "delete", {"period_end": settlement.period_end})
    ctx.db.delete(settlement)
    ctx.db.commit()


def set_transfer_paid(ctx: GroupContext, transfer_id: int, paid: bool) -> dict:
    transfer = (
        ctx.db.query(SettlementTransfer)
        .join(Settlement, Settlement.id == SettlementTransfer.settlement_id)
        .filter(SettlementTransfer.id == transfer_id, Settlement.group_id == ctx.group.id)
        .first()
    )
    if transfer is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "transfer_not_found", "Transfer not found")
    if ctx.user.id not in (transfer.from_user_id, transfer.to_user_id) and not ctx.is_admin:
        raise AppError(status.HTTP_403_FORBIDDEN, "transfer_not_involved", "Only the people involved can mark this")
    transfer.paid_at = utcnow() if paid else None
    transfer.confirmed_by = ctx.user.id if paid else None
    record(ctx, "transfer", transfer.id, "paid" if paid else "unpaid", {"amount_cents": transfer.amount_cents})
    ctx.db.commit()
    return _transfer_read(transfer)

from datetime import date

from fastapi import APIRouter, Depends, Query, status

from app.api.dependencies.clock import get_group_today
from app.api.dependencies.group import require_member
from app.models.trip import Trip
from app.schemas.entries import (
    ExpenseRead,
    ExpenseWrite,
    FuelRead,
    FuelWrite,
    TripFinish,
    TripRead,
    TripWrite,
)
from app.services import balance_service, entry_service
from app.services.access import GroupContext
from app.services.idempotency import idempotency_key

trips_router = APIRouter()
fuel_router = APIRouter()
expenses_router = APIRouter()


def _trip_reads(ctx: GroupContext, trips: list[Trip], today: date) -> list[TripRead]:
    costs = balance_service.trip_costs(ctx, trips, today)
    return [
        TripRead(
            id=t.id,
            car_id=t.car_id,
            date=t.date,
            start_km=t.start_km,
            end_km=t.end_km,
            km=t.km,
            note=t.note,
            shares=[{"user_id": s.user_id, "weight": s.weight} for s in t.shares],
            external=[
                {
                    "id": e.id,
                    "payer_name": e.payer_name,
                    "amount_cents": e.amount_cents,
                    "received_by_user_id": e.received_by_user_id,
                }
                for e in t.external_payments
            ],
            created_by=t.created_by,
            settlement_id=t.settlement_id,
            cost_cents=costs[t.id][0],
            cost_is_estimate=costs[t.id][1],
        )
        for t in trips
    ]


@trips_router.get("", response_model=list[TripRead])
def list_trips(
    car_id: int | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    ctx: GroupContext = Depends(require_member),
    today: date = Depends(get_group_today),
):
    return _trip_reads(ctx, entry_service.list_trips(ctx, car_id, limit), today)


@trips_router.get("/{trip_id}", response_model=TripRead)
def read_trip(trip_id: int, ctx: GroupContext = Depends(require_member), today: date = Depends(get_group_today)):
    return _trip_reads(ctx, [entry_service.get_trip(ctx, trip_id)], today)[0]


@trips_router.post("", response_model=TripRead, status_code=status.HTTP_201_CREATED)
def create_trip(
    data: TripWrite,
    ctx: GroupContext = Depends(require_member),
    today: date = Depends(get_group_today),
    key: str | None = Depends(idempotency_key),
):
    return _trip_reads(ctx, [entry_service.create_trip(ctx, data, key)], today)[0]


@trips_router.put("/{trip_id}", response_model=TripRead)
def update_trip(
    trip_id: int, data: TripWrite, ctx: GroupContext = Depends(require_member), today: date = Depends(get_group_today)
):
    return _trip_reads(ctx, [entry_service.update_trip(ctx, trip_id, data)], today)[0]


@trips_router.post("/{trip_id}/finish", response_model=TripRead)
def finish_trip(
    trip_id: int,
    data: TripFinish,
    ctx: GroupContext = Depends(require_member),
    today: date = Depends(get_group_today),
    key: str | None = Depends(idempotency_key),
):
    return _trip_reads(ctx, [entry_service.finish_trip(ctx, trip_id, data.end_km, key)], today)[0]


@trips_router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trip(trip_id: int, ctx: GroupContext = Depends(require_member)):
    entry_service.delete_trip(ctx, trip_id)


def _fuel_read(entry) -> FuelRead:
    return FuelRead.model_validate(entry, from_attributes=True)


@fuel_router.get("", response_model=list[FuelRead])
def list_fuel(limit: int = Query(default=200, ge=1, le=1000), ctx: GroupContext = Depends(require_member)):
    return [_fuel_read(e) for e in entry_service.list_fuel(ctx, limit)]


@fuel_router.get("/{fuel_id}", response_model=FuelRead)
def read_fuel(fuel_id: int, ctx: GroupContext = Depends(require_member)):
    return _fuel_read(entry_service.get_fuel(ctx, fuel_id))


@fuel_router.post("", response_model=FuelRead, status_code=status.HTTP_201_CREATED)
def create_fuel(
    data: FuelWrite, ctx: GroupContext = Depends(require_member), key: str | None = Depends(idempotency_key)
):
    return _fuel_read(entry_service.create_fuel(ctx, data, key))


@fuel_router.put("/{fuel_id}", response_model=FuelRead)
def update_fuel(fuel_id: int, data: FuelWrite, ctx: GroupContext = Depends(require_member)):
    return _fuel_read(entry_service.update_fuel(ctx, fuel_id, data))


@fuel_router.delete("/{fuel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_fuel(fuel_id: int, ctx: GroupContext = Depends(require_member)):
    entry_service.delete_fuel(ctx, fuel_id)


def _expense_read(entry) -> ExpenseRead:
    return ExpenseRead.model_validate(entry, from_attributes=True)


@expenses_router.get("", response_model=list[ExpenseRead])
def list_expenses(limit: int = Query(default=200, ge=1, le=1000), ctx: GroupContext = Depends(require_member)):
    return [_expense_read(e) for e in entry_service.list_expenses(ctx, limit)]


@expenses_router.get("/{expense_id}", response_model=ExpenseRead)
def read_expense(expense_id: int, ctx: GroupContext = Depends(require_member)):
    return _expense_read(entry_service.get_expense(ctx, expense_id))


@expenses_router.post("", response_model=ExpenseRead, status_code=status.HTTP_201_CREATED)
def create_expense(
    data: ExpenseWrite, ctx: GroupContext = Depends(require_member), key: str | None = Depends(idempotency_key)
):
    return _expense_read(entry_service.create_expense(ctx, data, key))


@expenses_router.put("/{expense_id}", response_model=ExpenseRead)
def update_expense(expense_id: int, data: ExpenseWrite, ctx: GroupContext = Depends(require_member)):
    return _expense_read(entry_service.update_expense(ctx, expense_id, data))


@expenses_router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expense(expense_id: int, ctx: GroupContext = Depends(require_member)):
    entry_service.delete_expense(ctx, expense_id)

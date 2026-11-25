from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.dependencies.clock import Clock, get_clock, get_group_today
from app.api.dependencies.group import require_member
from app.schemas.reservation import ReservationRead, ReservationWrite
from app.services import reservation_service
from app.services.access import GroupContext

router = APIRouter()


@router.get("", response_model=list[ReservationRead])
def list_reservations(
    first: date | None = Query(default=None, alias="from"),
    last: date | None = Query(default=None, alias="to"),
    car_id: int | None = None,
    ctx: GroupContext = Depends(require_member),
    today: date = Depends(get_group_today),
):
    """Reservations overlapping the local days from..to (default: today and the next 13 days)."""
    first = first or today
    last = last or first + timedelta(days=13)
    return reservation_service.list_reservations(ctx, first, last, car_id)


@router.post("", response_model=ReservationRead, status_code=status.HTTP_201_CREATED)
def create_reservation(
    data: ReservationWrite, ctx: GroupContext = Depends(require_member), clock: Clock = Depends(get_clock)
):
    reservation = reservation_service.create_reservation(ctx, data, clock.now())
    return reservation_service.reservation_read(reservation, reservation_service.group_zone(ctx))


@router.get("/{reservation_id}", response_model=ReservationRead)
def read_reservation(reservation_id: int, ctx: GroupContext = Depends(require_member)):
    return reservation_service.read_reservation(ctx, reservation_id)


@router.put("/{reservation_id}", response_model=ReservationRead)
def update_reservation(
    reservation_id: int,
    data: ReservationWrite,
    ctx: GroupContext = Depends(require_member),
    clock: Clock = Depends(get_clock),
):
    reservation = reservation_service.update_reservation(ctx, reservation_id, data, clock.now())
    return reservation_service.reservation_read(reservation, reservation_service.group_zone(ctx))


@router.delete("/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservation(
    reservation_id: int, ctx: GroupContext = Depends(require_member), clock: Clock = Depends(get_clock)
):
    reservation_service.delete_reservation(ctx, reservation_id, clock.now())
    return Response(status_code=status.HTTP_204_NO_CONTENT)

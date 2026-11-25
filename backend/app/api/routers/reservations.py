from datetime import date, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response, status

from app.api.dependencies.clock import Clock, get_clock, get_group_today
from app.api.dependencies.group import require_member
from app.schemas.reservation import ReservationRead, ReservationWrite
from app.services import notification_service, reservation_service
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
    data: ReservationWrite,
    background: BackgroundTasks,
    ctx: GroupContext = Depends(require_member),
    clock: Clock = Depends(get_clock),
):
    reservation = reservation_service.create_reservation(ctx, data, clock.now())
    items = notification_service.reservation_items(ctx, reservation, "create", clock.now())
    notification_service.deliver_later(background, ctx.db, items)
    return reservation_service.reservation_read(reservation, reservation_service.group_zone(ctx))


@router.get("/{reservation_id}", response_model=ReservationRead)
def read_reservation(reservation_id: int, ctx: GroupContext = Depends(require_member)):
    return reservation_service.read_reservation(ctx, reservation_id)


@router.put("/{reservation_id}", response_model=ReservationRead)
def update_reservation(
    reservation_id: int,
    data: ReservationWrite,
    background: BackgroundTasks,
    ctx: GroupContext = Depends(require_member),
    clock: Clock = Depends(get_clock),
):
    previous_user_id = reservation_service.get_reservation(ctx, reservation_id).user_id
    reservation = reservation_service.update_reservation(ctx, reservation_id, data, clock.now())
    items = notification_service.reservation_items(ctx, reservation, "update", clock.now(), previous_user_id)
    notification_service.deliver_later(background, ctx.db, items)
    return reservation_service.reservation_read(reservation, reservation_service.group_zone(ctx))


@router.delete("/{reservation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reservation(
    reservation_id: int,
    background: BackgroundTasks,
    ctx: GroupContext = Depends(require_member),
    clock: Clock = Depends(get_clock),
):
    # The message is prepared before the row is gone; it only goes out if deleting worked
    reservation = reservation_service.get_reservation(ctx, reservation_id)
    reservation_service.check_changeable(ctx, reservation, clock.now())
    items = notification_service.reservation_items(ctx, reservation, "delete", clock.now())
    reservation_service.delete_reservation(ctx, reservation_id, clock.now())
    notification_service.deliver_later(background, ctx.db, items)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

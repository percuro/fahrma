"""Reservations: who has which car when.

The API speaks wall-clock times in the group's time zone; the database stores naive UTC.
Converting here, with zoneinfo, keeps daylight saving time in one place: a time that does
not exist (the hour skipped in spring) is refused, an ambiguous one (the hour repeated in
autumn) means its first occurrence.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_default_timezone_name, get_zone
from app.errors import AppError
from app.models.reservation import Reservation
from app.schemas.reservation import ReservationWrite
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.car_service import get_car

MAX_DAYS = 31
MAX_RANGE_DAYS = 62


def group_zone(ctx: GroupContext) -> ZoneInfo:
    return get_zone(ctx.group.timezone or get_default_timezone_name())


def to_utc(value: datetime, zone: ZoneInfo) -> datetime:
    """Naive UTC for a local wall-clock time (or for a moment with an offset), to the minute."""
    value = value.replace(second=0, microsecond=0)
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    moment = value.replace(tzinfo=zone, fold=0).astimezone(UTC)
    if moment.astimezone(zone).replace(tzinfo=None) != value:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_local_time",
            "This time does not exist in the group's time zone (clocks change)",
            time=value.isoformat(timespec="minutes"),
        )
    return moment.replace(tzinfo=None)


def to_local(value: datetime, zone: ZoneInfo) -> datetime:
    return value.replace(tzinfo=UTC).astimezone(zone).replace(tzinfo=None)


def naive_utc(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now


def reservation_read(reservation: Reservation, zone: ZoneInfo) -> dict:
    return {
        "id": reservation.id,
        "car_id": reservation.car_id,
        "user_id": reservation.user_id,
        "starts_at": to_local(reservation.starts_at, zone),
        "ends_at": to_local(reservation.ends_at, zone),
        "starts_at_utc": reservation.starts_at.replace(tzinfo=UTC),
        "ends_at_utc": reservation.ends_at.replace(tzinfo=UTC),
        "note": reservation.note,
        "created_by": reservation.created_by,
    }


def _minutes(value: datetime) -> str:
    return value.isoformat(timespec="minutes")


def get_reservation(ctx: GroupContext, reservation_id: int) -> Reservation:
    reservation = ctx.db.scalar(
        select(Reservation).where(Reservation.id == reservation_id, Reservation.group_id == ctx.group.id)
    )
    if reservation is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "reservation_not_found", "Reservation not found")
    return reservation


def read_reservation(ctx: GroupContext, reservation_id: int) -> dict:
    return reservation_read(get_reservation(ctx, reservation_id), group_zone(ctx))


def list_reservations(ctx: GroupContext, first: date, last: date, car_id: int | None = None) -> list[dict]:
    """Reservations that overlap the local days first..last (both included)."""
    if last < first:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_range", "The range ends before it starts")
    if (last - first).days >= MAX_RANGE_DAYS:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "range_too_long", "Range too long", max_days=MAX_RANGE_DAYS
        )
    zone = group_zone(ctx)
    begin = datetime.combine(first, datetime.min.time(), zone).astimezone(UTC).replace(tzinfo=None)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), zone).astimezone(UTC).replace(tzinfo=None)
    query = select(Reservation).where(
        Reservation.group_id == ctx.group.id, Reservation.starts_at < end, Reservation.ends_at > begin
    )
    if car_id is not None:
        query = query.where(Reservation.car_id == car_id)
    rows = ctx.db.scalars(query.order_by(Reservation.starts_at, Reservation.id))
    return [reservation_read(row, zone) for row in rows]


def _check(ctx: GroupContext, data: ReservationWrite, now: datetime, reservation_id: int | None) -> tuple:
    zone = group_zone(ctx)
    car = get_car(ctx, data.car_id)
    if car.archived:
        raise AppError(status.HTTP_409_CONFLICT, "car_archived", "This car is archived")
    if data.user_id not in ctx.member_ids(active_only=True):
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "not_a_member", "Person is not a member of the group")
    starts_at, ends_at = to_utc(data.starts_at, zone), to_utc(data.ends_at, zone)
    if ends_at <= starts_at:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "reservation_end_before_start", "The end is before the start"
        )
    if ends_at <= naive_utc(now):
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "reservation_in_past", "The reservation is over already")
    if ends_at - starts_at > timedelta(days=MAX_DAYS):
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "reservation_too_long", "Reservation too long", max_days=MAX_DAYS
        )
    query = select(Reservation).where(
        Reservation.car_id == car.id, Reservation.starts_at < ends_at, Reservation.ends_at > starts_at
    )
    if reservation_id is not None:
        query = query.where(Reservation.id != reservation_id)
    other = ctx.db.scalar(query.order_by(Reservation.starts_at).limit(1))
    if other is not None:
        raise AppError(
            status.HTTP_409_CONFLICT,
            "reservation_overlap",
            "The car is reserved at that time",
            user_id=other.user_id,
            starts_at=_minutes(to_local(other.starts_at, zone)),
            ends_at=_minutes(to_local(other.ends_at, zone)),
        )
    return starts_at, ends_at


def _audit_data(data: ReservationWrite, zone: ZoneInfo, starts_at: datetime, ends_at: datetime) -> dict:
    return {
        "car_id": data.car_id,
        "user_id": data.user_id,
        "starts_at": _minutes(to_local(starts_at, zone)),
        "ends_at": _minutes(to_local(ends_at, zone)),
        "note": data.note,
    }


def _require_changeable(ctx: GroupContext, reservation: Reservation, now: datetime) -> None:
    if not ctx.is_admin and ctx.user.id not in (reservation.created_by, reservation.user_id):
        raise AppError(
            status.HTTP_403_FORBIDDEN,
            "reservation_not_yours",
            "Only the person it is for, whoever entered it and group admins can change it",
        )
    if reservation.ends_at <= naive_utc(now):
        raise AppError(status.HTTP_409_CONFLICT, "reservation_ended", "This reservation is over")


def create_reservation(ctx: GroupContext, data: ReservationWrite, now: datetime) -> Reservation:
    starts_at, ends_at = _check(ctx, data, now, None)
    reservation = Reservation(
        group_id=ctx.group.id,
        car_id=data.car_id,
        user_id=data.user_id,
        starts_at=starts_at,
        ends_at=ends_at,
        note=(data.note or "").strip() or None,
        created_by=ctx.user.id,
    )
    ctx.db.add(reservation)
    ctx.db.flush()
    record(ctx, "reservation", reservation.id, "create", _audit_data(data, group_zone(ctx), starts_at, ends_at))
    ctx.db.commit()
    return reservation


def update_reservation(ctx: GroupContext, reservation_id: int, data: ReservationWrite, now: datetime) -> Reservation:
    reservation = get_reservation(ctx, reservation_id)
    _require_changeable(ctx, reservation, now)
    previous_user = reservation.user_id
    starts_at, ends_at = _check(ctx, data, now, reservation.id)
    reservation.car_id = data.car_id
    reservation.user_id = data.user_id
    reservation.starts_at = starts_at
    reservation.ends_at = ends_at
    reservation.note = (data.note or "").strip() or None
    changes = _audit_data(data, group_zone(ctx), starts_at, ends_at)
    if previous_user != data.user_id:
        changes["previous_user_id"] = previous_user
    record(ctx, "reservation", reservation.id, "update", changes)
    ctx.db.commit()
    return reservation


def delete_reservation(ctx: GroupContext, reservation_id: int, now: datetime) -> Reservation:
    """Delete and return the (detached) reservation, e.g. for a notice to the person it was for."""
    reservation = get_reservation(ctx, reservation_id)
    _require_changeable(ctx, reservation, now)
    zone = group_zone(ctx)
    record(
        ctx,
        "reservation",
        reservation.id,
        "delete",
        {
            "car_id": reservation.car_id,
            "user_id": reservation.user_id,
            "starts_at": _minutes(to_local(reservation.starts_at, zone)),
            "ends_at": _minutes(to_local(reservation.ends_at, zone)),
        },
    )
    ctx.db.delete(reservation)
    ctx.db.commit()
    return reservation


def delete_upcoming(db: Session, user_id: int, now: datetime, group_id: int | None = None) -> None:
    """Remove the reservations of someone who leaves (a group, or every group) that are not over yet.

    Past reservations stay as history. The caller commits.
    """
    query = delete(Reservation).where(Reservation.user_id == user_id, Reservation.ends_at > naive_utc(now))
    if group_id is not None:
        query = query.where(Reservation.group_id == group_id)
    db.execute(query)

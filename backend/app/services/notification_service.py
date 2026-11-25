"""Which push notifications go to whom, and when.

Events someone causes (a reservation for somebody else, a settlement) go out right after the
response. Reminders come from a loop in the app (see app/web.py) that calls ``run_due`` once
a minute; ``sent_notifications`` remembers what went out, so a restart never repeats one.
Notifications name people, cars and times, never amounts of money.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import BackgroundTasks
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_default_timezone_name, get_push_settings, get_zone
from app.db.database import SessionLocal
from app.models.car import Car
from app.models.group import Group, Membership
from app.models.push import PushSubscription, SentNotification
from app.models.reservation import Reservation
from app.models.settlement import Settlement
from app.models.trip import Trip
from app.models.user import User, UserSession
from app.schemas.notifications import NotifySettings
from app.services import push
from app.services.access import GroupContext
from app.services.mail_texts import pick_locale
from app.services.push import Message, Target

logger = logging.getLogger(__name__)

# A trip still running after this long gets a reminder
OPEN_TRIP_AFTER = timedelta(hours=12)
KEEP_SENT = timedelta(days=60)

WEEKDAYS = {"de": ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"), "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}


def settings_of(user: User) -> NotifySettings:
    if not user.notify:
        return NotifySettings()
    try:
        return NotifySettings.model_validate_json(user.notify)
    except ValueError:
        return NotifySettings()


def store_settings(db: Session, user: User, settings: NotifySettings) -> None:
    user.notify = settings.model_dump_json()
    db.commit()


def naive_utc(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(tzinfo=None) if now.tzinfo else now


# --- Texts --------------------------------------------------------------------


def _day(value: datetime, locale: str) -> str:
    names = WEEKDAYS[locale]
    if locale == "de":
        return f"{names[value.weekday()]} {value:%d.%m.}"
    return f"{names[value.weekday()]} {value:%d/%m}"


def period(starts_at: datetime, ends_at: datetime, zone_name: str, locale: str) -> str:
    """A reservation's period in the group's time zone, e.g. "Di 01.12., 08:00–10:30"."""
    zone = get_zone(zone_name)
    start = starts_at.replace(tzinfo=UTC).astimezone(zone)
    end = ends_at.replace(tzinfo=UTC).astimezone(zone)
    if start.date() == end.date():
        return f"{_day(start, locale)}, {start:%H:%M}–{end:%H:%M}"
    return f"{_day(start, locale)}, {start:%H:%M} – {_day(end, locale)}, {end:%H:%M}"


def _reservation_text(action: str, locale: str, actor: str, car: str, when: str) -> tuple[str, str]:
    if locale == "de":
        return {
            "create": ("Reservierung für dich", f"{actor} hat {car} für dich reserviert: {when}."),
            "update": ("Reservierung geändert", f"{actor} hat deine Reservierung von {car} geändert: {when}."),
            "delete": ("Reservierung gelöscht", f"{actor} hat deine Reservierung von {car} gelöscht ({when})."),
            "reminder": ("Deine Reservierung beginnt bald", f"{car} ist für dich reserviert: {when}."),
        }[action]
    return {
        "create": ("Reserved for you", f"{actor} reserved {car} for you: {when}."),
        "update": ("Reservation changed", f"{actor} changed your reservation of {car}: {when}."),
        "delete": ("Reservation cancelled", f"{actor} cancelled your reservation of {car} ({when})."),
        "reminder": ("Your reservation starts soon", f"{car} is reserved for you: {when}."),
    }[action]


def _open_trip_text(locale: str, car: str, km: int) -> tuple[str, str]:
    if locale == "de":
        return "Fahrt läuft noch", f"{car}: Fahrt ab {f'{km:,}'.replace(',', '.')} km ist noch offen – bitte beenden."
    return "Trip still running", f"{car}: the trip from {km:,} km is still open – please finish it."


def _settlement_text(locale: str, actor: str, group: str) -> tuple[str, str]:
    if locale == "de":
        return "Neue Abrechnung", f"{actor} hat in „{group}“ abgerechnet."
    return "New settlement", f"{actor} settled up in “{group}”."


def _test_text(locale: str) -> tuple[str, str]:
    if locale == "de":
        return "Benachrichtigungen funktionieren", "So sehen Erinnerungen auf diesem Gerät aus."
    return "Notifications work", "This is how reminders look on this device."


# --- Recipients ---------------------------------------------------------------


def _subscriptions(db: Session, user_ids: list[int], now: datetime) -> dict[int, list[PushSubscription]]:
    """Subscriptions of logins that are still valid."""
    if not user_ids:
        return {}
    rows = db.scalars(
        select(PushSubscription)
        .join(UserSession, UserSession.id == PushSubscription.session_id)
        .where(PushSubscription.user_id.in_(user_ids), UserSession.expires_at > naive_utc(now))
    )
    found: dict[int, list[PushSubscription]] = {}
    for row in rows:
        found.setdefault(row.user_id, []).append(row)
    return found


def _member(db: Session, group_id: int, user_id: int) -> User | None:
    """The account if it can receive anything for this group: active, in the group, not a placeholder."""
    user = db.scalar(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            User.id == user_id,
            Membership.group_id == group_id,
            Membership.active.is_(True),
            User.is_active.is_(True),
            User.placeholder.is_(False),
            User.deleted_at.is_(None),
        )
    )
    return user


def _messages(
    db: Session, users: list[User], now: datetime, build: Callable[[str], Message]
) -> list[tuple[Target, Message]]:
    subscriptions = _subscriptions(db, [u.id for u in users], now)
    items = []
    for user in users:
        for subscription in subscriptions.get(user.id, []):
            items.append((push.target_of(subscription), build(pick_locale(user.locale, subscription.locale))))
    return items


def deliver_later(background: BackgroundTasks, db: Session, items: list[tuple[Target, Message]]) -> None:
    if not items:
        return
    bind = db.get_bind()

    def run() -> None:
        with Session(bind=bind) as session:
            push.deliver(session, items)

    background.add_task(run)


def _zone_name(group: Group) -> str:
    return group.timezone or get_default_timezone_name()


# --- Events -------------------------------------------------------------------


def reservation_items(
    ctx: GroupContext, reservation: Reservation, action: str, now: datetime, previous_user_id: int | None = None
) -> list[tuple[Target, Message]]:
    """For the person a reservation is for, when someone else created, changed or deleted it."""
    if get_push_settings() is None:
        return []
    car = ctx.db.get(Car, reservation.car_id)
    zone = _zone_name(ctx.group)
    gid = ctx.group.id
    recipients: list[tuple[int, str]] = [(reservation.user_id, action)]
    if previous_user_id is not None and previous_user_id != reservation.user_id:
        # Moved to someone else: for the previous person it is gone
        recipients = [(reservation.user_id, "create"), (previous_user_id, "delete")]
    items = []
    for user_id, kind in recipients:
        if user_id == ctx.user.id:
            continue
        user = _member(ctx.db, gid, user_id)
        if user is None or not settings_of(user).reservation_changes:
            continue

        def build(locale: str, kind: str = kind) -> Message:
            when = period(reservation.starts_at, reservation.ends_at, zone, locale)
            title, body = _reservation_text(kind, locale, ctx.user.display_name, car.name, when)
            url = f"/g/{gid}/calendar" if kind == "delete" else f"/g/{gid}/reservation/{reservation.id}"
            return Message(title=title, body=body, url=url, tag=f"reservation-{reservation.id}")

        items += _messages(ctx.db, [user], now, build)
    return items


def settlement_items(ctx: GroupContext, settlement: Settlement, now: datetime) -> list[tuple[Target, Message]]:
    """For every other member with an account who wants to know."""
    if get_push_settings() is None:
        return []
    users = ctx.db.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.group_id == ctx.group.id,
            Membership.active.is_(True),
            User.id != ctx.user.id,
            User.is_active.is_(True),
            User.placeholder.is_(False),
            User.deleted_at.is_(None),
        )
    ).all()
    users = [u for u in users if settings_of(u).settlements]

    def build(locale: str) -> Message:
        title, body = _settlement_text(locale, ctx.user.display_name, ctx.group.name)
        return Message(title, body, f"/g/{ctx.group.id}/settlement/{settlement.id}", f"settlement-{settlement.id}")

    return _messages(ctx.db, users, now, build)


def push_test_items(db: Session, user: User, session_id: int, now: datetime) -> list[tuple[Target, Message]]:
    """A test message to this device only."""
    subscriptions = [s for s in _subscriptions(db, [user.id], now).get(user.id, []) if s.session_id == session_id]
    items = []
    for subscription in subscriptions:
        title, body = _test_text(pick_locale(user.locale, subscription.locale))
        items.append((push.target_of(subscription), Message(title, body, "/profile", "test")))
    return items


# --- Reminders ----------------------------------------------------------------


def _claim(db: Session, user_id: int, kind: str, ref_id: int) -> bool:
    """Mark a reminder as sent; False if it was sent before."""
    exists = db.scalar(
        select(SentNotification.id).where(
            SentNotification.user_id == user_id, SentNotification.kind == kind, SentNotification.ref_id == ref_id
        )
    )
    if exists is not None:
        return False
    db.add(SentNotification(user_id=user_id, kind=kind, ref_id=ref_id))
    return True


def run_due(db: Session, now: datetime) -> list[tuple[Target, Message]]:
    """Reminders that are due now; claims them (commits) and returns what to send."""
    if get_push_settings() is None:
        return []
    now = naive_utc(now)
    items: list[tuple[Target, Message]] = []
    longest = timedelta(minutes=180)

    for reservation in db.scalars(
        select(Reservation).where(Reservation.starts_at > now, Reservation.starts_at <= now + longest)
    ):
        user = _member(db, reservation.group_id, reservation.user_id)
        if user is None:
            continue
        wanted = settings_of(user)
        lead = timedelta(minutes=wanted.lead_minutes)
        if not wanted.reservation_reminder or reservation.starts_at - lead > now:
            continue
        # Entered by the person within the lead time: they know already
        if reservation.created_by == user.id and reservation.created_at >= reservation.starts_at - lead:
            continue
        group = db.get(Group, reservation.group_id)
        car = db.get(Car, reservation.car_id)

        def build(locale: str, r: Reservation = reservation, group: Group = group, car: Car = car) -> Message:
            title, body = _reservation_text(
                "reminder", locale, "", car.name, period(r.starts_at, r.ends_at, _zone_name(group), locale)
            )
            return Message(title, body, f"/g/{group.id}/reservation/{r.id}", f"reservation-{r.id}")

        found = _messages(db, [user], now, build)
        if found and _claim(db, user.id, "reminder", reservation.id):
            items += found

    for trip in db.scalars(select(Trip).where(Trip.end_km.is_(None))):
        user = _member(db, trip.group_id, trip.created_by)
        if user is None or not settings_of(user).open_trip:
            continue
        reservation_over = db.scalar(
            select(Reservation.id).where(
                Reservation.user_id == user.id,
                Reservation.car_id == trip.car_id,
                Reservation.ends_at <= now,
                Reservation.ends_at > trip.created_at,
            )
        )
        if trip.created_at > now - OPEN_TRIP_AFTER and reservation_over is None:
            continue
        car = db.get(Car, trip.car_id)

        def build_trip(locale: str, t: Trip = trip, car: Car = car) -> Message:
            title, body = _open_trip_text(locale, car.name, t.start_km)
            return Message(title, body, f"/g/{t.group_id}", f"trip-{t.id}")

        found = _messages(db, [user], now, build_trip)
        if found and _claim(db, user.id, "open_trip", trip.id):
            items += found

    db.execute(delete(SentNotification).where(SentNotification.created_at < now - KEEP_SENT))
    db.commit()
    return items


def run_scheduled() -> None:
    """One round of the reminder loop, with its own database session."""
    with SessionLocal() as db:
        items = run_due(db, datetime.now(UTC))
        if items:
            push.deliver(db, items)


def export_rows(db: Session, user: User) -> dict:
    """For "my data": the settings and which devices receive notifications."""
    rows = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user.id))
    return {
        "settings": json.loads(settings_of(user).model_dump_json()),
        "devices": [
            {
                "created_at": row.created_at.isoformat(),
                "last_success_at": row.last_success_at.isoformat() if row.last_success_at else None,
                "push_service": row.endpoint.split("/")[2],
            }
            for row in rows
        ],
    }

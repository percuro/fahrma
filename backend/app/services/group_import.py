"""Import of a group from a "fahrma-group/1" file, e.g. when moving to another instance.

Everything gets new IDs; the file's IDs are only used to connect its rows. The importing
person picks which member of the file they are and becomes admin of the new group. Every
other member becomes a placeholder (a person without an account) whom the admins can
invite with a personal link later. Deleted accounts stay anonymous. The numbers – entries,
frozen settlements, paid transfers – stay exactly as they were.
"""

import json
from datetime import UTC, date, datetime

from fastapi import status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_limit, is_valid_timezone
from app.errors import AppError
from app.models.audit import AuditEntry
from app.models.car import Car
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import ROLE_ADMIN, Group, Membership
from app.models.reservation import Reservation
from app.models.settlement import Settlement, SettlementTransfer
from app.models.trip import Trip, TripExternalPayment, TripShare
from app.models.user import User
from app.schemas.group_import import (
    FORMAT,
    GroupExportFile,
    ImportCounts,
    ImportMemberPreview,
    ImportPreview,
)
from app.services.auth_service import utcnow
from app.services.limits import check_new_group
from app.services.placeholders import new_deleted_user, new_placeholder
from app.services.snapshots import SnapshotError, dumps, remap_snapshot

# Plenty for years of a busy group (an entry is a few hundred bytes)
MAX_IMPORT_BYTES = 20 * 1024 * 1024


def invalid(where: str, message: str = "The file is not a valid fahrma group export") -> AppError:
    return AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "import_invalid", f"{message} ({where})", where=where)


def parse(raw: bytes) -> GroupExportFile:
    """Read and check the structure of an export file (references are checked in import_group)."""
    try:
        data = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise invalid("json", "The file is not JSON") from exc
    if not isinstance(data, dict):
        raise invalid("json")
    found = data.get("format")
    if found != FORMAT:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "import_format",
            f"Expected a file in the format {FORMAT}",
            expected=FORMAT,
            found=found if isinstance(found, str) else None,
        )
    try:
        return GroupExportFile.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise invalid(".".join(str(part) for part in first["loc"]) or "file") from exc


def _dates(data: GroupExportFile) -> list[date]:
    return [row.date for rows in (data.trips, data.fuel, data.expenses) for row in rows]


def preview(data: GroupExportFile) -> ImportPreview:
    _check_references(data)
    dates = _dates(data)
    return ImportPreview(
        app_version=data.app_version,
        exported_at=data.exported_at,
        name=data.group.name,
        currency=data.group.currency,
        timezone=data.group.timezone,
        members=[
            ImportMemberPreview(
                user_id=m.user_id, display_name=m.display_name, role=m.role, active=m.active, deleted=m.deleted
            )
            for m in data.members
        ],
        counts=ImportCounts(
            cars=len(data.cars),
            trips=len(data.trips),
            fuel=len(data.fuel),
            expenses=len(data.expenses),
            settlements=len(data.settlements),
            reservations=len(data.reservations),
        ),
        first_date=min(dates) if dates else None,
        last_date=max(dates) if dates else None,
    )


def _unique_ids(rows, name: str, key: str = "id") -> set[int]:
    ids: set[int] = set()
    for index, row in enumerate(rows):
        value = getattr(row, key)
        if value in ids:
            raise invalid(f"{name}[{index}].{key}")
        ids.add(value)
    return ids


def _check_references(data: GroupExportFile) -> None:
    """Every ID a row refers to must belong to the file; nothing may point elsewhere."""
    members = _unique_ids(data.members, "members", "user_id")
    cars = _unique_ids(data.cars, "cars")
    trips = _unique_ids(data.trips, "trips")
    _unique_ids(data.fuel, "fuel")
    _unique_ids(data.expenses, "expenses")
    settlements = _unique_ids(data.settlements, "settlements")

    def need(value, known: set[int], where: str, optional: bool = False) -> None:
        if value is None and optional:
            return
        if value not in known:
            raise invalid(where)

    for i, trip in enumerate(data.trips):
        need(trip.car_id, cars, f"trips[{i}].car_id")
        need(trip.created_by, members, f"trips[{i}].created_by")
        need(trip.settlement_id, settlements, f"trips[{i}].settlement_id", optional=True)
        if trip.end_km is not None and trip.end_km < trip.start_km:
            raise invalid(f"trips[{i}].end_km")
    seen_shares: set[tuple[int, int]] = set()
    for i, share in enumerate(data.trip_shares):
        need(share.trip_id, trips, f"trip_shares[{i}].trip_id")
        need(share.user_id, members, f"trip_shares[{i}].user_id")
        if (share.trip_id, share.user_id) in seen_shares:
            raise invalid(f"trip_shares[{i}]")
        seen_shares.add((share.trip_id, share.user_id))
    for i, payment in enumerate(data.trip_external_payments):
        need(payment.trip_id, trips, f"trip_external_payments[{i}].trip_id")
        need(payment.received_by_user_id, members, f"trip_external_payments[{i}].received_by_user_id")
    for i, entry in enumerate(data.fuel):
        need(entry.car_id, cars, f"fuel[{i}].car_id")
        need(entry.paid_by_user_id, members, f"fuel[{i}].paid_by_user_id")
        need(entry.created_by, members, f"fuel[{i}].created_by")
        need(entry.settlement_id, settlements, f"fuel[{i}].settlement_id", optional=True)
    for i, entry in enumerate(data.expenses):
        need(entry.car_id, cars, f"expenses[{i}].car_id", optional=True)
        need(entry.trip_id, trips, f"expenses[{i}].trip_id", optional=True)
        need(entry.paid_by_user_id, members, f"expenses[{i}].paid_by_user_id")
        need(entry.allocated_user_id, members, f"expenses[{i}].allocated_user_id", optional=True)
        need(entry.created_by, members, f"expenses[{i}].created_by")
        need(entry.settlement_id, settlements, f"expenses[{i}].settlement_id", optional=True)
        if entry.allocation == "single" and entry.allocated_user_id is None:
            raise invalid(f"expenses[{i}].allocated_user_id")
        if entry.allocation == "trip" and entry.trip_id is None:
            raise invalid(f"expenses[{i}].trip_id")
    for i, settlement in enumerate(data.settlements):
        need(settlement.created_by, members, f"settlements[{i}].created_by")
        try:
            remap_snapshot(
                settlement.snapshot,
                {m: m for m in members},
                cars={c: c for c in cars},
                trips={t: t for t in trips},
            )
        except SnapshotError as exc:
            raise invalid(f"settlements[{i}].snapshot.{exc}") from exc
    for i, transfer in enumerate(data.settlement_transfers):
        need(transfer.settlement_id, settlements, f"settlement_transfers[{i}].settlement_id")
        need(transfer.from_user_id, members, f"settlement_transfers[{i}].from_user_id")
        need(transfer.to_user_id, members, f"settlement_transfers[{i}].to_user_id")
        need(transfer.confirmed_by, members, f"settlement_transfers[{i}].confirmed_by", optional=True)
    _unique_ids(data.reservations, "reservations")
    by_car: dict[int, list[tuple[datetime, datetime, int]]] = {}
    for i, reservation in enumerate(data.reservations):
        need(reservation.car_id, cars, f"reservations[{i}].car_id")
        need(reservation.user_id, members, f"reservations[{i}].user_id")
        need(reservation.created_by, members, f"reservations[{i}].created_by")
        starts_at, ends_at = _naive_utc(reservation.starts_at), _naive_utc(reservation.ends_at)
        if ends_at <= starts_at:
            raise invalid(f"reservations[{i}].ends_at")
        by_car.setdefault(reservation.car_id, []).append((starts_at, ends_at, i))
    for periods in by_car.values():
        periods.sort()
        for earlier, later in zip(periods, periods[1:], strict=False):
            if later[0] < earlier[1]:
                raise invalid(f"reservations[{later[2]}].starts_at")
    for i, entry in enumerate(data.audit_log):
        need(entry.user_id, members, f"audit_log[{i}].user_id")


def _check_limits(data: GroupExportFile) -> None:
    for limit_name, env_name, count in (
        ("members_per_group", "MAX_MEMBERS_PER_GROUP", sum(1 for m in data.members if m.active and not m.deleted)),
        ("cars_per_group", "MAX_CARS_PER_GROUP", sum(1 for c in data.cars if not c.archived)),
    ):
        maximum = get_limit(env_name)
        if maximum is not None and count > maximum:
            raise AppError(
                status.HTTP_409_CONFLICT,
                "limit_reached",
                f"Limit reached: at most {maximum}",
                limit=limit_name,
                max=maximum,
            )


def import_group(db: Session, user: User, data: GroupExportFile, member_id: int) -> Group:
    """Create the group of the file; ``member_id`` is the member of the file who imports it."""
    _check_references(data)
    me = next((m for m in data.members if m.user_id == member_id), None)
    if me is None or me.deleted or not me.active:
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "import_member_invalid",
            "Pick an active member of the file as yourself",
        )
    check_new_group(db, user.id)
    _check_limits(data)
    try:
        group = _create(db, user, data, member_id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise invalid("constraint") from exc
    db.refresh(group)
    return group


def _create(db: Session, user: User, data: GroupExportFile, member_id: int) -> Group:
    timezone = data.group.timezone if data.group.timezone and is_valid_timezone(data.group.timezone) else None
    group = Group(name=data.group.name.strip(), currency=data.group.currency, timezone=timezone)
    if data.group.created_at:
        group.created_at = data.group.created_at
    db.add(group)
    db.flush()

    users: dict[int, int] = {}
    for member in data.members:
        if member.user_id == member_id:
            users[member.user_id] = user.id
            role, active = ROLE_ADMIN, True
        else:
            person = new_deleted_user(db) if member.deleted else new_placeholder(db, member.display_name)
            users[member.user_id] = person.id
            role, active = member.role, member.active and not member.deleted
        membership = Membership(group_id=group.id, user_id=users[member.user_id], role=role, active=active)
        if member.joined_at:
            membership.created_at = member.joined_at
        db.add(membership)

    cars: dict[int, int] = {}
    for row in data.cars:
        car = Car(
            group_id=group.id,
            name=row.name,
            plate=row.plate,
            start_odometer_km=row.start_odometer_km,
            energy_unit=row.energy_unit,
            archived=row.archived,
        )
        _created_at(car, row.created_at)
        db.add(car)
        db.flush()
        cars[row.id] = car.id

    # Settlements before the entries that point to them; the snapshot follows once trips have IDs
    settlements: dict[int, Settlement] = {}
    for row in sorted(data.settlements, key=lambda s: s.id):
        settlement = Settlement(
            group_id=group.id,
            period_start=row.period_start,
            period_end=row.period_end,
            created_by=users[row.created_by],
            snapshot_json="{}",
        )
        _created_at(settlement, row.created_at)
        db.add(settlement)
        db.flush()
        settlements[row.id] = settlement

    def settlement_id(old: int | None) -> int | None:
        return settlements[old].id if old is not None else None

    trips: dict[int, int] = {}
    for row in sorted(data.trips, key=lambda t: t.id):
        trip = Trip(
            group_id=group.id,
            car_id=cars[row.car_id],
            date=row.date,
            start_km=row.start_km,
            end_km=row.end_km,
            note=row.note,
            created_by=users[row.created_by],
            settlement_id=settlement_id(row.settlement_id),
        )
        _created_at(trip, row.created_at)
        trip.updated_at = row.updated_at or row.created_at or utcnow()
        db.add(trip)
        db.flush()
        trips[row.id] = trip.id
    for row in data.trip_shares:
        db.add(TripShare(trip_id=trips[row.trip_id], user_id=users[row.user_id], weight=row.weight))
    for row in data.trip_external_payments:
        db.add(
            TripExternalPayment(
                trip_id=trips[row.trip_id],
                payer_name=row.payer_name,
                amount_cents=row.amount_cents,
                received_by_user_id=users[row.received_by_user_id],
            )
        )

    fuel: dict[int, int] = {}
    for row in sorted(data.fuel, key=lambda f: f.id):
        entry = FuelEntry(
            group_id=group.id,
            car_id=cars[row.car_id],
            date=row.date,
            odometer_km=row.odometer_km,
            quantity_milli=row.quantity_milli,
            amount_cents=row.amount_cents,
            paid_by_user_id=users[row.paid_by_user_id],
            full_tank=row.full_tank,
            note=row.note,
            created_by=users[row.created_by],
            settlement_id=settlement_id(row.settlement_id),
        )
        _created_at(entry, row.created_at)
        db.add(entry)
        db.flush()
        fuel[row.id] = entry.id

    expenses: dict[int, int] = {}
    for row in sorted(data.expenses, key=lambda e: e.id):
        expense = Expense(
            group_id=group.id,
            car_id=cars[row.car_id] if row.car_id is not None else None,
            trip_id=trips[row.trip_id] if row.trip_id is not None else None,
            date=row.date,
            category=row.category,
            description=row.description,
            amount_cents=row.amount_cents,
            paid_by_user_id=users[row.paid_by_user_id],
            allocation=row.allocation,
            allocated_user_id=users[row.allocated_user_id] if row.allocated_user_id is not None else None,
            created_by=users[row.created_by],
            settlement_id=settlement_id(row.settlement_id),
        )
        _created_at(expense, row.created_at)
        db.add(expense)
        db.flush()
        expenses[row.id] = expense.id

    for row in data.settlements:
        snapshot = remap_snapshot(row.snapshot, users, cars=cars, trips=trips)
        settlements[row.id].snapshot_json = dumps(snapshot)

    transfers: dict[int, int] = {}
    for row in data.settlement_transfers:
        transfer = SettlementTransfer(
            settlement_id=settlements[row.settlement_id].id,
            from_user_id=users[row.from_user_id],
            to_user_id=users[row.to_user_id],
            amount_cents=row.amount_cents,
            paid_at=row.paid_at,
            confirmed_by=users[row.confirmed_by] if row.confirmed_by is not None else None,
        )
        db.add(transfer)
        db.flush()
        if row.id is not None:
            transfers[row.id] = transfer.id

    reservations: dict[int, int] = {}
    for row in sorted(data.reservations, key=lambda r: r.id):
        reservation = Reservation(
            group_id=group.id,
            car_id=cars[row.car_id],
            user_id=users[row.user_id],
            starts_at=_naive_utc(row.starts_at),
            ends_at=_naive_utc(row.ends_at),
            note=row.note,
            created_by=users[row.created_by],
        )
        _created_at(reservation, row.created_at)
        reservation.updated_at = row.updated_at or row.created_at or utcnow()
        db.add(reservation)
        db.flush()
        reservations[row.id] = reservation.id

    entity_ids = {
        "car": cars,
        "reservation": reservations,
        "trip": trips,
        "fuel": fuel,
        "expense": expenses,
        "settlement": {old: s.id for old, s in settlements.items()},
        "transfer": transfers,
        "member": users,
    }
    for row in data.audit_log:
        if row.entity == "group":
            entity_id = group.id
        else:
            # Deleted entries and invitations do not exist in the new group: 0
            entity_id = entity_ids.get(row.entity, {}).get(row.entity_id, 0)
        entry = AuditEntry(
            group_id=group.id,
            user_id=users[row.user_id],
            entity=row.entity,
            entity_id=entity_id,
            action=row.action,
            diff_json=json.dumps(row.diff, ensure_ascii=False) if row.diff is not None else None,
        )
        _created_at(entry, row.created_at)
        db.add(entry)
    db.add(
        AuditEntry(
            group_id=group.id,
            user_id=user.id,
            entity="group",
            entity_id=group.id,
            action="import",
            diff_json=json.dumps(
                {
                    "app_version": data.app_version,
                    "exported_at": data.exported_at.isoformat() if data.exported_at else None,
                }
            ),
        )
    )
    db.flush()
    return group


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None) if value.tzinfo else value


def _created_at(row, value) -> None:
    if value is not None:
        row.created_at = value

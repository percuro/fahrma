"""People without an account in a group: placeholders.

A placeholder is a row in ``users`` that cannot log in and belongs to exactly one group.
It comes from an imported group (every member except the importing person) or is added by
a group admin for someone who does not want an account. Others enter trips and payments
for them like for any member.

With a personal link (an Invite with placeholder_user_id) the person takes the place over:
a new account simply becomes the placeholder row; an existing account takes over its
bookings in that group and the placeholder row disappears.
"""

import json
import secrets

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models.audit import AuditEntry
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import Invite, Membership
from app.models.reservation import Reservation
from app.models.settlement import Settlement, SettlementTransfer
from app.models.trip import Trip, TripExternalPayment, TripShare
from app.models.user import User
from app.services.auth_service import utcnow
from app.services.snapshots import dumps, remap_snapshot

# Matches no password hash, so nobody can log in with it
NO_PASSWORD = "!"


def _anonymous_name(user_id: int) -> str:
    # Same as account_service.anonymous_name (not imported to avoid an import cycle)
    return f"Person {user_id}"


def _new_user(db: Session, display_name: str, **fields) -> User:
    # "~" is not allowed in chosen usernames, so internal names never collide with real ones
    user = User(
        username=f"~new-{secrets.token_hex(8)}",
        display_name=display_name,
        password_hash=NO_PASSWORD,
        is_active=False,
        **fields,
    )
    db.add(user)
    db.flush()
    return user


def new_placeholder(db: Session, display_name: str) -> User:
    user = _new_user(db, display_name.strip(), placeholder=True)
    user.username = f"~placeholder-{user.id}"
    return user


def new_deleted_user(db: Session) -> User:
    """An anonymous former member (the account was deleted before the export)."""
    user = _new_user(db, "Person", deleted_at=utcnow())
    user.username = f"~deleted-{user.id}"
    user.display_name = _anonymous_name(user.id)
    return user


def reassign(db: Session, group_id: int, old_user_id: int, new_user_id: int) -> None:
    """Move everything of one person in a group to another account (the caller commits).

    The other account must not be in the group yet; the frozen settlement snapshots get the
    new ID as well, so their numbers stay attached to the same person.
    """
    trip_ids = select(Trip.id).where(Trip.group_id == group_id)
    settlement_ids = select(Settlement.id).where(Settlement.group_id == group_id)
    for model, column, scope in (
        (Membership, Membership.user_id, Membership.group_id == group_id),
        (Trip, Trip.created_by, Trip.group_id == group_id),
        (TripShare, TripShare.user_id, TripShare.trip_id.in_(trip_ids)),
        (
            TripExternalPayment,
            TripExternalPayment.received_by_user_id,
            TripExternalPayment.trip_id.in_(trip_ids),
        ),
        (FuelEntry, FuelEntry.paid_by_user_id, FuelEntry.group_id == group_id),
        (FuelEntry, FuelEntry.created_by, FuelEntry.group_id == group_id),
        (Expense, Expense.paid_by_user_id, Expense.group_id == group_id),
        (Expense, Expense.allocated_user_id, Expense.group_id == group_id),
        (Expense, Expense.created_by, Expense.group_id == group_id),
        (Settlement, Settlement.created_by, Settlement.group_id == group_id),
        (SettlementTransfer, SettlementTransfer.from_user_id, SettlementTransfer.settlement_id.in_(settlement_ids)),
        (SettlementTransfer, SettlementTransfer.to_user_id, SettlementTransfer.settlement_id.in_(settlement_ids)),
        (SettlementTransfer, SettlementTransfer.confirmed_by, SettlementTransfer.settlement_id.in_(settlement_ids)),
        (AuditEntry, AuditEntry.user_id, AuditEntry.group_id == group_id),
        (Invite, Invite.created_by, Invite.group_id == group_id),
        (Reservation, Reservation.user_id, Reservation.group_id == group_id),
        (Reservation, Reservation.created_by, Reservation.group_id == group_id),
    ):
        db.execute(update(model).where(scope, column == old_user_id).values({column: new_user_id}))
    db.execute(
        update(AuditEntry)
        .where(AuditEntry.group_id == group_id, AuditEntry.entity == "member", AuditEntry.entity_id == old_user_id)
        .values(entity_id=new_user_id)
    )
    for settlement in db.scalars(select(Settlement).where(Settlement.group_id == group_id)):
        settlement.snapshot_json = dumps(
            remap_snapshot(json.loads(settlement.snapshot_json), {old_user_id: new_user_id})
        )


def delete_orphans(db: Session, user_ids: list[int]) -> None:
    """Remove placeholders and deleted accounts that are no longer in any group."""
    if not user_ids:
        return
    still_member = select(Membership.user_id).where(Membership.user_id.in_(user_ids))
    db.execute(
        delete(User).where(
            User.id.in_(user_ids),
            User.id.not_in(still_member),
            (User.placeholder.is_(True)) | (User.deleted_at.is_not(None)),
        )
    )

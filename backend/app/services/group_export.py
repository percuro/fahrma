"""Complete JSON export of a group in a versioned format.

The format "fahrma-group/1" contains every row of the group, with the database IDs, so a
later version can import it into another instance (moving between self-hosting and a
hosted service; see group_import.py). Account data is limited to what the group sees:
ID and display name.
"""

import json

from sqlalchemy import select

from app import __version__
from app.models.audit import AuditEntry
from app.models.car import Car
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import Membership
from app.models.reservation import Reservation
from app.models.settlement import Settlement, SettlementTransfer
from app.models.trip import Trip, TripExternalPayment, TripShare
from app.models.user import User
from app.schemas.group_import import FORMAT
from app.services.access import GroupContext
from app.services.auth_service import utcnow
from app.services.rows import row_dict

# The plan belongs to the instance, not to the group's data: it does not move along, and
# the operator's note is never shown to the group
INSTANCE_ONLY_COLUMNS = frozenset({"plan", "plan_until", "plan_note"})


def export_group(ctx: GroupContext) -> dict:
    db, group_id = ctx.db, ctx.group.id
    trip_ids = select(Trip.id).where(Trip.group_id == group_id)
    settlement_ids = select(Settlement.id).where(Settlement.group_id == group_id)

    def rows(query) -> list[dict]:
        return [row_dict(row) for row in db.scalars(query)]

    members = db.execute(
        select(Membership, User).join(User, User.id == Membership.user_id).where(Membership.group_id == group_id)
    ).all()
    settlements = []
    for settlement in db.scalars(select(Settlement).where(Settlement.group_id == group_id).order_by(Settlement.id)):
        data = row_dict(settlement)
        data["snapshot"] = json.loads(data.pop("snapshot_json"))
        settlements.append(data)
    audit = []
    for entry in db.scalars(select(AuditEntry).where(AuditEntry.group_id == group_id).order_by(AuditEntry.id)):
        data = row_dict(entry)
        diff = data.pop("diff_json")
        data["diff"] = json.loads(diff) if diff else None
        audit.append(data)
    return {
        "format": FORMAT,
        "app_version": __version__,
        "exported_at": utcnow().isoformat(),
        "group": row_dict(ctx.group, exclude=INSTANCE_ONLY_COLUMNS),
        "members": [
            {
                "user_id": user.id,
                "display_name": user.display_name,
                "role": membership.role,
                "active": membership.active,
                "deleted": user.is_deleted,
                "placeholder": user.placeholder,
                "joined_at": membership.created_at.isoformat(),
            }
            for membership, user in members
        ],
        "cars": rows(select(Car).where(Car.group_id == group_id).order_by(Car.id)),
        "trips": rows(select(Trip).where(Trip.group_id == group_id).order_by(Trip.id)),
        "trip_shares": rows(select(TripShare).where(TripShare.trip_id.in_(trip_ids)).order_by(TripShare.id)),
        "trip_external_payments": rows(
            select(TripExternalPayment)
            .where(TripExternalPayment.trip_id.in_(trip_ids))
            .order_by(TripExternalPayment.id)
        ),
        "fuel": rows(select(FuelEntry).where(FuelEntry.group_id == group_id).order_by(FuelEntry.id)),
        "expenses": rows(select(Expense).where(Expense.group_id == group_id).order_by(Expense.id)),
        "settlements": settlements,
        "settlement_transfers": rows(
            select(SettlementTransfer)
            .where(SettlementTransfer.settlement_id.in_(settlement_ids))
            .order_by(SettlementTransfer.id)
        ),
        "reservations": rows(select(Reservation).where(Reservation.group_id == group_id).order_by(Reservation.id)),
        "audit_log": audit,
    }

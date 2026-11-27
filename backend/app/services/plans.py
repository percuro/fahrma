"""Plans per group (hosting): which limits apply to a group, and changing a group's plan.

Without PLANS_FILE every group has the one implicit plan with the MAX_* limits, so nothing
changes for self-hosting. A group's own plan applies until its last day (plan_until, in the
group's time zone); afterwards, or if the plan was removed from the file, the default plan
applies again. Nothing is ever locked or deleted when a plan ends: only adding cars or
members beyond the limits of the plan now in force is refused.
"""

from datetime import UTC, date, datetime

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Plan, get_default_timezone_name, get_plans, get_zone
from app.errors import AppError
from app.models.audit import AuditEntry
from app.models.car import Car
from app.models.group import ROLE_ADMIN, Group, Membership
from app.models.receipt import Receipt
from app.models.user import User
from app.services import security_log


def group_today(group: Group) -> date:
    """Today in the group's time zone (the day plan_until is compared with)."""
    return datetime.now(UTC).astimezone(get_zone(group.timezone or get_default_timezone_name())).date()


def own_plan_active(group: Group, today: date) -> bool:
    """The group has a plan of its own that exists and has not run out."""
    settings = get_plans()
    if not group.plan or group.plan not in settings.plans:
        return False
    return group.plan_until is None or today <= group.plan_until


def effective_plan(group: Group, today: date | None = None) -> Plan:
    settings = get_plans()
    if own_plan_active(group, today or group_today(group)):
        return settings.plans[group.plan]
    return settings.default_plan


MEGABYTE = 1024 * 1024


def receipt_bytes(db: Session, group_id: int) -> int:
    return db.scalar(select(func.coalesce(func.sum(Receipt.bytes), 0)).where(Receipt.group_id == group_id)) or 0


def usage(db: Session, group_id: int) -> dict[str, int | float]:
    """What counts against the limits: active members (also without an account), cars not
    archived, and the receipt photos in megabytes (one decimal)."""
    members = db.scalar(
        select(func.count()).select_from(Membership).where(Membership.group_id == group_id, Membership.active.is_(True))
    )
    cars = db.scalar(select(func.count()).select_from(Car).where(Car.group_id == group_id, Car.archived.is_(False)))
    return {
        "members_per_group": members or 0,
        "cars_per_group": cars or 0,
        "receipt_mb_per_group": round(receipt_bytes(db, group_id) / MEGABYTE, 1),
    }


def plan_info(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "members_per_group": plan.members_per_group,
        "cars_per_group": plan.cars_per_group,
        "receipt_mb_per_group": plan.receipt_mb_per_group,
    }


def group_plan_read(db: Session, group: Group, today: date) -> dict:
    """The plan as the group's members see it: name, limits, usage; never the operator's note."""
    plan = effective_plan(group, today)
    own = own_plan_active(group, today)
    return {
        **plan_info(plan),
        "until": group.plan_until if own else None,
        "usage": usage(db, group.id),
    }


def set_plan(
    db: Session,
    group: Group,
    plan: str | None,
    until: date | None,
    note: str | None,
    *,
    actor: User | None = None,
    by: str = "admin",
) -> None:
    """Set a group's plan (None = the default plan); the caller commits."""
    settings = get_plans()
    if plan is not None and plan not in settings.plans:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "plan_unknown", "Unknown plan", plan=plan)
    until = until if plan is not None else None
    if (group.plan, group.plan_until) != (plan, until):
        details = {
            "group_id": group.id,
            "group": group.name,
            "plan": plan,
            "until": until.isoformat() if until else None,
        }
        security_log.record(db, "plan.changed", actor=actor, commit=False, by=by, **details)
    group.plan = plan
    group.plan_until = until
    group.plan_note = (note or "").strip() or None


def operator_group_read(db: Session, group: Group) -> dict:
    """What an operator sees about a group: plan, counts, admins' names; never entries or amounts."""
    today = group_today(group)
    admins = db.execute(
        select(User.id, User.display_name)
        .join(Membership, Membership.user_id == User.id)
        .where(
            Membership.group_id == group.id,
            Membership.role == ROLE_ADMIN,
            Membership.active.is_(True),
            User.placeholder.is_(False),
            User.deleted_at.is_(None),
        )
        .order_by(User.display_name)
    ).all()
    last_activity = db.scalar(select(func.max(AuditEntry.created_at)).where(AuditEntry.group_id == group.id))
    return {
        "id": group.id,
        "name": group.name,
        "created_at": group.created_at,
        "last_activity_at": last_activity,
        "plan": group.plan,
        "plan_until": group.plan_until,
        "plan_note": group.plan_note,
        "effective_plan": effective_plan(group, today).id,
        "usage": usage(db, group.id),
        "admins": [{"user_id": user_id, "display_name": name} for user_id, name in admins],
    }


def get_group(db: Session, group_id: int) -> Group:
    group = db.get(Group, group_id)
    if group is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "group_not_found", "Group not found")
    return group


def list_groups(db: Session, plan: str | None = None) -> list[dict]:
    query = select(Group).order_by(Group.id)
    if plan is not None:
        query = query.where(Group.plan == plan)
    return [operator_group_read(db, group) for group in db.scalars(query)]

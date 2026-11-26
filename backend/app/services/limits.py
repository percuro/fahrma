"""Limits for hosted instances. MAX_GROUPS_PER_USER applies per account; members, cars and
receipt storage per group come from the group's plan (see app.services.plans), which without
PLANS_FILE simply carries MAX_MEMBERS_PER_GROUP, MAX_CARS_PER_GROUP and MAX_RECEIPT_MB_PER_GROUP.
Unset or 0 = unlimited, the default for self-hosting.

Limits are only checked when something is added: a group above the limits of its plan (after
a plan ran out, or after a move) keeps everything and can work as before."""

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Plan, get_limit, get_plans
from app.errors import AppError
from app.models.group import Membership
from app.services.plans import MEGABYTE, effective_plan, get_group, receipt_bytes, usage


def limits() -> dict[str, int | None]:
    """The instance's limits for /meta: per account, and those of the default plan."""
    default = get_plans().default_plan
    return {
        "groups_per_user": get_limit("MAX_GROUPS_PER_USER"),
        "members_per_group": default.members_per_group,
        "cars_per_group": default.cars_per_group,
        "receipt_mb_per_group": default.receipt_mb_per_group,
    }


def _raise(name: str, maximum: int, plan: Plan | None = None) -> None:
    params: dict = {"limit": name, "max": maximum}
    if plan is not None and get_plans().configured:
        params["plan"] = plan.id
    raise AppError(status.HTTP_409_CONFLICT, "limit_reached", f"Limit reached: at most {maximum}", **params)


def check_count(name: str, count: int, plan: Plan) -> None:
    """``count`` things exist already; refuse one more beyond the plan's limit."""
    maximum = plan.limit(name)
    if maximum is not None and count >= maximum:
        _raise(name, maximum, plan)


def check_new_group(db: Session, user_id: int) -> None:
    """Before someone creates or joins a group (counts active memberships)."""
    maximum = get_limit("MAX_GROUPS_PER_USER")
    if maximum is None:
        return
    count = db.scalar(
        select(func.count()).select_from(Membership).where(Membership.user_id == user_id, Membership.active.is_(True))
    )
    if (count or 0) >= maximum:
        _raise("groups_per_user", maximum)


def _check_group(db: Session, group_id: int, name: str) -> None:
    plan = effective_plan(get_group(db, group_id))
    if plan.limit(name) is not None:
        check_count(name, usage(db, group_id)[name], plan)


def check_new_member(db: Session, group_id: int) -> None:
    _check_group(db, group_id, "members_per_group")


def check_new_car(db: Session, group_id: int) -> None:
    """Archived cars do not count: archive an old car to make room."""
    _check_group(db, group_id, "cars_per_group")


def check_receipt_space(db: Session, group_id: int, new_bytes: int) -> None:
    """Room for one more photo of ``new_bytes``; deleting photos makes room again."""
    plan = effective_plan(get_group(db, group_id))
    maximum = plan.receipt_mb_per_group
    if maximum is not None and receipt_bytes(db, group_id) + new_bytes > maximum * MEGABYTE:
        _raise("receipt_mb_per_group", maximum, plan)

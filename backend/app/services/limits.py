"""Optional limits for hosted instances (MAX_GROUPS_PER_USER, MAX_MEMBERS_PER_GROUP,
MAX_CARS_PER_GROUP). Unset or 0 = unlimited, which is the default for self-hosting."""

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_limit
from app.errors import AppError
from app.models.car import Car
from app.models.group import Membership


def limits() -> dict[str, int | None]:
    return {
        "groups_per_user": get_limit("MAX_GROUPS_PER_USER"),
        "members_per_group": get_limit("MAX_MEMBERS_PER_GROUP"),
        "cars_per_group": get_limit("MAX_CARS_PER_GROUP"),
    }


def _check(name: str, count: int) -> None:
    maximum = limits()[name]
    if maximum is not None and count >= maximum:
        raise AppError(
            status.HTTP_409_CONFLICT, "limit_reached", f"Limit reached: at most {maximum}", limit=name, max=maximum
        )


def check_new_group(db: Session, user_id: int) -> None:
    """Before someone creates or joins a group (counts active memberships)."""
    count = db.scalar(
        select(func.count()).select_from(Membership).where(Membership.user_id == user_id, Membership.active.is_(True))
    )
    _check("groups_per_user", count or 0)


def check_new_member(db: Session, group_id: int) -> None:
    count = db.scalar(
        select(func.count()).select_from(Membership).where(Membership.group_id == group_id, Membership.active.is_(True))
    )
    _check("members_per_group", count or 0)


def check_new_car(db: Session, group_id: int) -> None:
    """Archived cars do not count: archive an old car to make room."""
    count = db.scalar(select(func.count()).select_from(Car).where(Car.group_id == group_id, Car.archived.is_(False)))
    _check("cars_per_group", count or 0)

import secrets
from datetime import date, timedelta

from fastapi import status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_default_timezone_name, get_invite_expiry_days, get_public_url, is_valid_timezone
from app.errors import AppError
from app.models.audit import AuditEntry
from app.models.car import Car
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import ROLE_ADMIN, Group, Invite, Membership
from app.models.idempotency import IdempotencyKey
from app.models.reservation import Reservation
from app.models.settlement import Settlement, SettlementTransfer
from app.models.trip import Trip, TripExternalPayment, TripShare
from app.models.user import User
from app.schemas.group import GroupUpdate
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.auth_service import AuthService, utcnow
from app.services.limits import check_new_group, check_new_member
from app.services.placeholders import delete_orphans, new_placeholder
from app.services.reservation_service import delete_upcoming


def groups_of(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(Membership, Group)
        .join(Group, Group.id == Membership.group_id)
        .filter(Membership.user_id == user.id, Membership.active.is_(True))
        .order_by(Group.name)
        .all()
    )
    return [{"id": group.id, "name": group.name, "role": membership.role} for membership, group in rows]


def create_group(db: Session, user: User, name: str) -> Group:
    check_new_group(db, user.id)
    group = Group(name=name.strip())
    db.add(group)
    db.flush()
    db.add(Membership(group_id=group.id, user_id=user.id, role=ROLE_ADMIN))
    db.commit()
    db.refresh(group)
    return group


def group_read(ctx: GroupContext, today: date) -> dict:
    now = utcnow()
    open_links = {
        row[0]: row[1]
        for row in ctx.db.query(Invite.placeholder_user_id, Invite.expires_at).filter(
            Invite.group_id == ctx.group.id,
            Invite.placeholder_user_id.is_not(None),
            Invite.used_at.is_(None),
            Invite.expires_at > now,
        )
    }
    rows = (
        ctx.db.query(Membership, User)
        .join(User, User.id == Membership.user_id)
        .filter(Membership.group_id == ctx.group.id)
        .order_by(Membership.active.desc(), User.display_name)
        .all()
    )
    return {
        "id": ctx.group.id,
        "name": ctx.group.name,
        "currency": ctx.group.currency,
        "timezone": ctx.group.timezone,
        "effective_timezone": ctx.group.timezone or get_default_timezone_name(),
        "today": today.isoformat(),
        "my_role": ctx.membership.role,
        "members": [
            {
                "user_id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": membership.role,
                "active": membership.active,
                "deleted": user.is_deleted,
                "placeholder": user.placeholder,
                "link_expires_at": open_links.get(user.id) if ctx.is_admin else None,
            }
            for membership, user in rows
        ],
    }


def _has_amounts(ctx: GroupContext) -> bool:
    """Whether the group already has entries with amounts in its currency."""
    gid = ctx.group.id
    return any(
        ctx.db.query(query.exists()).scalar()
        for query in (
            ctx.db.query(FuelEntry.id).filter(FuelEntry.group_id == gid),
            ctx.db.query(Expense.id).filter(Expense.group_id == gid),
            ctx.db.query(TripExternalPayment.id).join(Trip).filter(Trip.group_id == gid),
        )
    )


def update_group(ctx: GroupContext, data: GroupUpdate) -> None:
    ctx.require_admin()
    changes: dict = {}
    if data.name is not None:
        ctx.group.name = changes["name"] = data.name.strip()
    if data.currency is not None and data.currency != ctx.group.currency:
        # Amounts are stored without conversion; switching later would silently relabel them
        if _has_amounts(ctx):
            raise AppError(
                status.HTTP_409_CONFLICT, "currency_locked", "The currency can only be changed before the first amount"
            )
        ctx.group.currency = changes["currency"] = data.currency
    if "timezone" in data.model_fields_set:
        if data.timezone is not None and not is_valid_timezone(data.timezone):
            raise AppError(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "timezone_invalid", "Unknown time zone", timezone=data.timezone
            )
        ctx.group.timezone = changes["timezone"] = data.timezone
    if changes:
        record(ctx, "group", ctx.group.id, "update", changes)
    ctx.db.commit()


def add_placeholder(ctx: GroupContext, display_name: str) -> int:
    """A person without an account; the admins can send them a personal link later."""
    ctx.require_admin()
    check_new_member(ctx.db, ctx.group.id)
    person = new_placeholder(ctx.db, display_name)
    ctx.db.add(Membership(group_id=ctx.group.id, user_id=person.id))
    record(ctx, "member", person.id, "create", {"display_name": person.display_name, "placeholder": True})
    ctx.db.commit()
    return person.id


def count_admins(db: Session, group_id: int) -> int:
    """Active admins who can act; placeholders cannot."""
    return (
        db.query(Membership)
        .join(User, User.id == Membership.user_id)
        .filter(
            Membership.group_id == group_id,
            Membership.role == ROLE_ADMIN,
            Membership.active.is_(True),
            User.placeholder.is_(False),
        )
        .count()
    )


def update_member(
    ctx: GroupContext, user_id: int, role: str | None, active: bool | None, display_name: str | None = None
) -> None:
    ctx.require_admin()
    membership = (
        ctx.db.query(Membership).filter(Membership.group_id == ctx.group.id, Membership.user_id == user_id).first()
    )
    if membership is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "member_not_found", "Member not found")
    if membership.user.is_deleted and (active or role == ROLE_ADMIN):
        raise AppError(status.HTTP_409_CONFLICT, "member_deleted", "This account has been deleted")
    if display_name is not None and not membership.user.placeholder:
        # People with an account choose their own name
        raise AppError(status.HTTP_409_CONFLICT, "member_has_account", "Only names of people without an account")
    if active and not membership.active:
        check_new_member(ctx.db, ctx.group.id)
        check_new_group(ctx.db, user_id)
    if display_name is not None:
        membership.user.display_name = display_name.strip()
    if role is not None:
        membership.role = role
    if active is not None:
        membership.active = active
        if not active:
            # Whoever leaves no longer has the car booked; past reservations stay as history
            delete_upcoming(ctx.db, user_id, utcnow(), ctx.group.id)
    ctx.db.flush()
    if count_admins(ctx.db, ctx.group.id) == 0:
        ctx.db.rollback()
        raise AppError(status.HTTP_409_CONFLICT, "last_admin", "The group needs at least one admin")
    changes = {"role": role, "active": active}
    if display_name is not None:
        changes["display_name"] = display_name.strip()
    record(ctx, "member", user_id, "update", changes)
    ctx.db.commit()


def placeholder_of(ctx: GroupContext, user_id: int) -> User:
    """An active member without an account (for a personal link)."""
    membership = (
        ctx.db.query(Membership).filter(Membership.group_id == ctx.group.id, Membership.user_id == user_id).first()
    )
    if membership is None or not membership.user.placeholder:
        raise AppError(status.HTTP_404_NOT_FOUND, "member_not_found", "Member not found")
    if not membership.active:
        raise AppError(status.HTTP_409_CONFLICT, "member_inactive", "Add the person to the group again first")
    return membership.user


def create_invite(ctx: GroupContext, placeholder_user_id: int | None = None, email: str | None = None) -> dict:
    """One-time link into the group: PUBLIC_URL/invite#<token> (the token never reaches server logs).

    With placeholder_user_id it is a personal link: whoever uses it becomes that member.
    """
    ctx.require_admin()
    if placeholder_user_id is not None:
        placeholder_of(ctx, placeholder_user_id)
        # Only the newest personal link of a person works
        ctx.db.execute(
            delete(Invite).where(Invite.placeholder_user_id == placeholder_user_id, Invite.used_at.is_(None))
        )
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(days=get_invite_expiry_days())
    invite = Invite(
        group_id=ctx.group.id,
        token_hash=AuthService.hash_token(token),
        created_by=ctx.user.id,
        expires_at=expires_at,
        placeholder_user_id=placeholder_user_id,
        email=email,
    )
    ctx.db.add(invite)
    ctx.db.flush()
    record(ctx, "invite", invite.id, "create", {"member": placeholder_user_id} if placeholder_user_id else None)
    ctx.db.commit()
    return {"url": f"{get_public_url()}/invite#{token}", "expires_at": expires_at}


def delete_group_data(db: Session, group_id: int) -> None:
    """Delete a group with everything in it, children first (the caller commits).

    Explicit order instead of ON DELETE CASCADE: expenses may point to trips (RESTRICT),
    and fuel, trips and expenses point to cars and settlements.
    """
    trip_ids = select(Trip.id).where(Trip.group_id == group_id)
    settlement_ids = select(Settlement.id).where(Settlement.group_id == group_id)
    member_ids = list(db.scalars(select(Membership.user_id).where(Membership.group_id == group_id)))
    db.execute(delete(Expense).where(Expense.group_id == group_id))
    db.execute(delete(FuelEntry).where(FuelEntry.group_id == group_id))
    db.execute(delete(TripShare).where(TripShare.trip_id.in_(trip_ids)))
    db.execute(delete(TripExternalPayment).where(TripExternalPayment.trip_id.in_(trip_ids)))
    db.execute(delete(Trip).where(Trip.group_id == group_id))
    db.execute(delete(SettlementTransfer).where(SettlementTransfer.settlement_id.in_(settlement_ids)))
    db.execute(delete(Settlement).where(Settlement.group_id == group_id))
    db.execute(delete(Reservation).where(Reservation.group_id == group_id))
    db.execute(delete(Car).where(Car.group_id == group_id))
    db.execute(delete(AuditEntry).where(AuditEntry.group_id == group_id))
    db.execute(delete(IdempotencyKey).where(IdempotencyKey.group_id == group_id))
    db.execute(delete(Invite).where(Invite.group_id == group_id))
    db.execute(delete(Membership).where(Membership.group_id == group_id))
    db.execute(delete(Group).where(Group.id == group_id))
    delete_orphans(db, member_ids)


def delete_group(ctx: GroupContext, confirm_name: str) -> None:
    ctx.require_admin()
    if confirm_name.strip() != ctx.group.name.strip():
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "group_name_mismatch", "The name does not match the group"
        )
    delete_group_data(ctx.db, ctx.group.id)
    ctx.db.commit()

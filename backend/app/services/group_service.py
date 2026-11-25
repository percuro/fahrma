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
from app.models.settlement import Settlement, SettlementTransfer
from app.models.trip import Trip, TripExternalPayment, TripShare
from app.models.user import User
from app.schemas.group import GroupUpdate
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.auth_service import AuthService, utcnow
from app.services.limits import check_new_group, check_new_member


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


def update_member(ctx: GroupContext, user_id: int, role: str | None, active: bool | None) -> None:
    ctx.require_admin()
    membership = (
        ctx.db.query(Membership).filter(Membership.group_id == ctx.group.id, Membership.user_id == user_id).first()
    )
    if membership is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "member_not_found", "Member not found")
    if membership.user.is_deleted and (active or role == ROLE_ADMIN):
        raise AppError(status.HTTP_409_CONFLICT, "member_deleted", "This account has been deleted")
    if active and not membership.active:
        check_new_member(ctx.db, ctx.group.id)
        check_new_group(ctx.db, user_id)
    if role is not None:
        membership.role = role
    if active is not None:
        membership.active = active
    ctx.db.flush()
    admins = (
        ctx.db.query(Membership)
        .filter(
            Membership.group_id == ctx.group.id,
            Membership.role == ROLE_ADMIN,
            Membership.active.is_(True),
        )
        .count()
    )
    if admins == 0:
        ctx.db.rollback()
        raise AppError(status.HTTP_409_CONFLICT, "last_admin", "The group needs at least one admin")
    record(ctx, "member", user_id, "update", {"role": role, "active": active})
    ctx.db.commit()


def create_invite(ctx: GroupContext) -> dict:
    """One-time link into the group: PUBLIC_URL/invite#<token> (the token never reaches server logs)."""
    ctx.require_admin()
    token = secrets.token_urlsafe(32)
    expires_at = utcnow() + timedelta(days=get_invite_expiry_days())
    invite = Invite(
        group_id=ctx.group.id,
        token_hash=AuthService.hash_token(token),
        created_by=ctx.user.id,
        expires_at=expires_at,
    )
    ctx.db.add(invite)
    ctx.db.flush()
    record(ctx, "invite", invite.id, "create")
    ctx.db.commit()
    return {"url": f"{get_public_url()}/invite#{token}", "expires_at": expires_at}


def delete_group_data(db: Session, group_id: int) -> None:
    """Delete a group with everything in it, children first (the caller commits).

    Explicit order instead of ON DELETE CASCADE: expenses may point to trips (RESTRICT),
    and fuel, trips and expenses point to cars and settlements.
    """
    trip_ids = select(Trip.id).where(Trip.group_id == group_id)
    settlement_ids = select(Settlement.id).where(Settlement.group_id == group_id)
    db.execute(delete(Expense).where(Expense.group_id == group_id))
    db.execute(delete(FuelEntry).where(FuelEntry.group_id == group_id))
    db.execute(delete(TripShare).where(TripShare.trip_id.in_(trip_ids)))
    db.execute(delete(TripExternalPayment).where(TripExternalPayment.trip_id.in_(trip_ids)))
    db.execute(delete(Trip).where(Trip.group_id == group_id))
    db.execute(delete(SettlementTransfer).where(SettlementTransfer.settlement_id.in_(settlement_ids)))
    db.execute(delete(Settlement).where(Settlement.group_id == group_id))
    db.execute(delete(Car).where(Car.group_id == group_id))
    db.execute(delete(AuditEntry).where(AuditEntry.group_id == group_id))
    db.execute(delete(Invite).where(Invite.group_id == group_id))
    db.execute(delete(Membership).where(Membership.group_id == group_id))
    db.execute(delete(Group).where(Group.id == group_id))


def delete_group(ctx: GroupContext, confirm_name: str) -> None:
    ctx.require_admin()
    if confirm_name.strip() != ctx.group.name.strip():
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "group_name_mismatch", "The name does not match the group"
        )
    delete_group_data(ctx.db, ctx.group.id)
    ctx.db.commit()

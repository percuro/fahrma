import secrets
from datetime import date, timedelta

from fastapi import Response, status
from sqlalchemy.orm import Session

from app.config import get_default_timezone_name, get_public_url, is_valid_timezone
from app.errors import AppError
from app.models.expense import Expense
from app.models.fuel import FuelEntry
from app.models.group import ROLE_ADMIN, ROLE_MEMBER, Group, Invite, Membership
from app.models.trip import Trip, TripExternalPayment
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import RegisterRequest
from app.schemas.group import GroupUpdate
from app.services.access import GroupContext
from app.services.audit_service import record
from app.services.auth_service import AccountError, AuthService, utcnow

INVITE_DAYS = 7


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
    ctx.require_admin()
    token = secrets.token_urlsafe(24)
    expires_at = utcnow() + timedelta(days=INVITE_DAYS)
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
    return {"url": f"{get_public_url()}/invite/{token}", "token": token, "expires_at": expires_at}


def _valid_invite(db: Session, token: str) -> Invite | None:
    invite = db.query(Invite).filter(Invite.token_hash == AuthService.hash_token(token)).first()
    if invite is None or invite.used_at is not None or invite.expires_at <= utcnow():
        return None
    return invite


def preview_invite(db: Session, token: str) -> dict:
    invite = _valid_invite(db, token)
    if invite is None:
        return {"group_name": "", "valid": False}
    return {"group_name": invite.group.name, "valid": True}


def _join(db: Session, invite: Invite, user: User) -> None:
    membership = (
        db.query(Membership).filter(Membership.group_id == invite.group_id, Membership.user_id == user.id).first()
    )
    if membership is None:
        db.add(Membership(group_id=invite.group_id, user_id=user.id, role=ROLE_MEMBER))
    else:
        membership.active = True
    invite.used_at = utcnow()
    invite.used_by_user_id = user.id


def accept_invite(db: Session, user: User, token: str) -> int:
    invite = _valid_invite(db, token)
    if invite is None:
        raise AppError(status.HTTP_410_GONE, "invite_invalid", "Invitation is invalid or has expired")
    _join(db, invite, user)
    db.commit()
    return invite.group_id


def register(db: Session, data: RegisterRequest, response: Response) -> User:
    invite = _valid_invite(db, data.token)
    if invite is None:
        raise AppError(status.HTTP_410_GONE, "invite_invalid", "Invitation is invalid or has expired")
    service = AuthService(AuthRepository(db))
    try:
        user = service.create_user(data.username, data.password, data.display_name, commit=False)
    except AccountError as exc:
        db.rollback()
        raise exc.to_http() from exc
    _join(db, invite, user)
    db.commit()
    db.refresh(user)
    service.start_session(user, response)
    return user

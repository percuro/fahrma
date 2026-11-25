from datetime import date

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.api.dependencies.clock import Clock, get_clock, get_group_today
from app.api.dependencies.group import require_member
from app.db.database import get_db
from app.schemas.audit import AuditRead
from app.schemas.group import (
    GroupCreate,
    GroupRead,
    GroupUpdate,
    InviteCreated,
    InvitePreview,
    MemberUpdate,
)
from app.services import audit_service, group_service
from app.services.access import GroupContext, load_group_context

router = APIRouter()
invite_router = APIRouter()


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    data: GroupCreate, user=Depends(require_user), db: Session = Depends(get_db), clock: Clock = Depends(get_clock)
):
    group = group_service.create_group(db, user, data.name)
    return group_service.group_read(load_group_context(db, user, group.id), clock.today(group.timezone))


@router.get("/{group_id}", response_model=GroupRead)
def read_group(ctx: GroupContext = Depends(require_member), today: date = Depends(get_group_today)):
    return group_service.group_read(ctx, today)


@router.patch("/{group_id}", response_model=GroupRead)
def update_group(data: GroupUpdate, ctx: GroupContext = Depends(require_member), clock: Clock = Depends(get_clock)):
    group_service.update_group(ctx, data)
    return group_service.group_read(ctx, clock.today(ctx.group.timezone))


@router.patch("/{group_id}/members/{user_id}", response_model=GroupRead)
def update_member(
    user_id: int,
    data: MemberUpdate,
    ctx: GroupContext = Depends(require_member),
    today: date = Depends(get_group_today),
):
    group_service.update_member(ctx, user_id, data.role, data.active)
    return group_service.group_read(ctx, today)


@router.post("/{group_id}/invites", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(ctx: GroupContext = Depends(require_member)):
    return group_service.create_invite(ctx)


@router.get("/{group_id}/audit", response_model=list[AuditRead])
def audit(ctx: GroupContext = Depends(require_member)):
    return audit_service.list_entries(ctx)


@invite_router.get("/{token}", response_model=InvitePreview)
def preview_invite(token: str, db: Session = Depends(get_db)):
    return group_service.preview_invite(db, token)


@invite_router.post("/{token}/accept")
def accept_invite(token: str, user=Depends(require_user), db: Session = Depends(get_db)):
    return {"group_id": group_service.accept_invite(db, user, token)}

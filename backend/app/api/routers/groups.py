from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.api.dependencies.clock import Clock, get_clock, get_group_today
from app.api.dependencies.group import require_member
from app.db.database import get_db
from app.errors import AppError
from app.models.user import User
from app.schemas.audit import AuditRead
from app.schemas.group import (
    GroupCreate,
    GroupDelete,
    GroupRead,
    GroupUpdate,
    InviteCreate,
    MemberUpdate,
    PlaceholderCreate,
)
from app.schemas.group_import import ImportPreview
from app.schemas.invitation import GroupInviteCreated
from app.schemas.plans import BillingLink
from app.services import audit_service, group_import, group_service
from app.services.access import GroupContext, load_group_context
from app.services.billing_link import billing_link
from app.services.client_address import client_ip
from app.services.group_export import export_group
from app.services.invitation_service import InvitationService
from app.services.mail import check_account_quota, require_mail
from app.services.plans import effective_plan

router = APIRouter()


@router.post("", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def create_group(
    data: GroupCreate, user=Depends(require_user), db: Session = Depends(get_db), clock: Clock = Depends(get_clock)
):
    group = group_service.create_group(db, user, data.name)
    return group_service.group_read(load_group_context(db, user, group.id), clock.today(group.timezone))


async def import_file(request: Request) -> bytes:
    """The raw body, at most MAX_IMPORT_BYTES (checked while reading, not only by the header)."""
    too_large = AppError(
        status.HTTP_413_CONTENT_TOO_LARGE,
        "import_too_large",
        "The file is too large",
        max_mb=group_import.MAX_IMPORT_BYTES // (1024 * 1024),
    )
    length = request.headers.get("content-length", "")
    if length.isdigit() and int(length) > group_import.MAX_IMPORT_BYTES:
        raise too_large
    size, chunks = 0, []
    async for chunk in request.stream():
        size += len(chunk)
        if size > group_import.MAX_IMPORT_BYTES:
            raise too_large
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/import/check", response_model=ImportPreview)
def check_import(raw: bytes = Depends(import_file), user=Depends(require_user)):
    """What a group export file contains; nothing is stored. The body is the file itself."""
    return group_import.preview(group_import.parse(raw))


@router.post("/import", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def import_group(
    member: int = Query(description="user_id of the member in the file who is importing it"),
    raw: bytes = Depends(import_file),
    user=Depends(require_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
):
    """Creates a new group from a "fahrma-group/1" file (body); the importing person becomes its admin."""
    group = group_import.import_group(db, user, group_import.parse(raw), member)
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
    group_service.update_member(ctx, user_id, data.role, data.active, data.display_name)
    return group_service.group_read(ctx, today)


@router.post("/{group_id}/members", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
def add_person_without_account(
    data: PlaceholderCreate, ctx: GroupContext = Depends(require_member), today: date = Depends(get_group_today)
):
    """Adds someone who has no account; others enter their trips. A personal link can follow later."""
    group_service.add_placeholder(ctx, data.display_name)
    return group_service.group_read(ctx, today)


def _invite(
    ctx: GroupContext,
    data: InviteCreate | None,
    request: Request,
    background: BackgroundTasks,
    placeholder: User | None = None,
) -> dict:
    email = data.email if data else None
    if email:
        require_mail()
        ctx.require_admin()
        check_account_quota(ctx.user.id, client_ip(request))
    created = group_service.create_invite(ctx, placeholder.id if placeholder else None, email)
    if email:
        InvitationService(ctx.db, background).send_group_invite(
            ctx.user, ctx.group, created, email, request, placeholder.display_name if placeholder else None
        )
    return {**created, "email_sent": bool(email)}


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_group(data: GroupDelete, ctx: GroupContext = Depends(require_member)):
    """Deletes the group with all cars, entries and settlements (group admins only)."""
    group_service.delete_group(ctx, data.name)


@router.get("/{group_id}/export.json")
def export_json(ctx: GroupContext = Depends(require_member)):
    filename = f"fahrma-group-{ctx.group.id}.json"
    return JSONResponse(export_group(ctx), headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/{group_id}/invites", response_model=GroupInviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(
    request: Request,
    background: BackgroundTasks,
    data: InviteCreate | None = None,
    ctx: GroupContext = Depends(require_member),
):
    """A link anyone can use once to join; optionally sent by e-mail."""
    return _invite(ctx, data, request, background)


@router.post(
    "/{group_id}/members/{user_id}/invite", response_model=GroupInviteCreated, status_code=status.HTTP_201_CREATED
)
def create_personal_invite(
    user_id: int,
    request: Request,
    background: BackgroundTasks,
    data: InviteCreate | None = None,
    ctx: GroupContext = Depends(require_member),
):
    """A personal link for a member without an account: whoever uses it takes over that place."""
    ctx.require_admin()
    placeholder = group_service.placeholder_of(ctx, user_id)
    return _invite(ctx, data, request, background, placeholder)


@router.get("/{group_id}/audit", response_model=list[AuditRead])
def audit(ctx: GroupContext = Depends(require_member)):
    return audit_service.list_entries(ctx)


@router.post("/{group_id}/billing-link", response_model=BillingLink)
def create_billing_link(ctx: GroupContext = Depends(require_member), today: date = Depends(get_group_today)):
    """Where a group admin changes the group's plan: BILLING_URL with the group (and a signed token)."""
    ctx.require_admin()
    return {"url": billing_link(ctx.group, ctx.user, effective_plan(ctx.group, today).id)}

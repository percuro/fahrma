"""Instance administration (users with the role admin)."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_admin
from app.db.database import get_db
from app.models.user import User
from app.repositories.auth_repository import AuthRepository
from app.schemas.admin import AdminUserRead, AdminUserUpdate
from app.schemas.invitation import InvitationCreate, InvitationCreated, InvitationRead, PasswordResetCreate
from app.schemas.plans import OperatorGroupRead, PlanUpdate
from app.services.admin_service import AdminService
from app.services.invitation_service import InvitationService
from app.services.oidc_service import OidcService
from app.services.plans import get_group, list_groups, operator_group_read, set_plan

router = APIRouter()


@router.get("/users", response_model=list[AdminUserRead])
def list_users(db: Session = Depends(get_db)):
    return AdminService(db).list_users()


@router.patch("/users/{user_id}", response_model=AdminUserRead)
def update_user(
    user_id: int, data: AdminUserUpdate, admin: User = Depends(require_admin), db: Session = Depends(get_db)
):
    return AdminService(db).update_user(admin, user_id, data)


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    AdminService(db).delete_user(admin, user_id)


@router.delete("/users/{user_id}/oidc", status_code=status.HTTP_204_NO_CONTENT)
def unlink_oidc(user_id: int, db: Session = Depends(get_db)):
    """Remove an account's link to the provider (e.g. a lost provider account) and log it out everywhere.

    It logs in again with its password, or a password-reset link."""
    user = AdminService(db).get_user(user_id)
    OidcService(db).unlink(user, by="admin")
    AuthRepository(db).delete_sessions(user.id)


@router.post("/users/{user_id}/password-reset", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
def create_password_reset(
    user_id: int,
    request: Request,
    background: BackgroundTasks,
    data: PasswordResetCreate | None = None,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """A one-time link with which the person sets a new password. Admins never see or set passwords.

    With send_email the link also goes to the account's confirmed address.
    """
    target = AdminService(db).get_user(user_id)
    send = bool(data and data.send_email)
    return InvitationService(db, background).create_password_reset(admin, target, send_email=send, request=request)


@router.post("/invitations", response_model=InvitationCreated, status_code=status.HTTP_201_CREATED)
def create_invitation(
    data: InvitationCreate,
    request: Request,
    background: BackgroundTasks,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return InvitationService(db, background).create_signup(admin, data.role, data.note, data.email, request)


@router.get("/invitations", response_model=list[InvitationRead])
def list_invitations(db: Session = Depends(get_db)):
    return InvitationService(db).list_open()


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invitation(invitation_id: int, db: Session = Depends(get_db)):
    InvitationService(db).revoke(invitation_id)


@router.get("/groups", response_model=list[OperatorGroupRead])
def admin_list_groups(db: Session = Depends(get_db)):
    """Groups with plan, counts and admins; never entries or amounts."""
    return list_groups(db)


@router.put("/groups/{group_id}/plan", response_model=OperatorGroupRead)
def admin_update_plan(group_id: int, data: PlanUpdate, db: Session = Depends(get_db)):
    group = get_group(db, group_id)
    set_plan(db, group, data.plan, data.until, data.note)
    db.commit()
    return operator_group_read(db, group)

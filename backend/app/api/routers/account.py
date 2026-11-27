"""The logged-in account: password, e-mail address, devices, data export, deletion."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.config import password_login_enabled
from app.db.database import get_db
from app.errors import AppError
from app.models.user import User
from app.schemas.auth import DeletionPreview, EmailChange, PasswordChange, PasswordConfirmation, SessionRead
from app.services.account_service import AccountService
from app.services.auth_service import clear_session_cookie
from app.services.invitation_service import InvitationService
from app.services.oidc_service import OidcService

router = APIRouter()


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    data: PasswordChange, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    AccountService(db).change_password(
        user, data.current_password, data.new_password, request, request.state.session_id
    )


@router.delete("/password", status_code=status.HTTP_204_NO_CONTENT)
def remove_password(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Log in with the OIDC provider only; needs a login at the provider in the last 10 minutes."""
    AccountService(db).remove_password(user, request.state.session_id)


@router.post("/email", status_code=status.HTTP_202_ACCEPTED)
def change_email(
    data: EmailChange,
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Sends a confirmation link to the new address; it replaces the old one once confirmed."""
    AccountService(db).confirm(user, data.password, request, request.state.session_id)
    InvitationService(db, background).request_email_change(user, data.email, request)
    return {"status": "accepted"}


@router.delete("/email/pending", status_code=status.HTTP_204_NO_CONTENT)
def cancel_email_change(user: User = Depends(require_user), db: Session = Depends(get_db)):
    InvitationService(db).cancel_email_change(user)


@router.delete("/email", status_code=status.HTTP_204_NO_CONTENT)
def remove_email(
    data: PasswordConfirmation, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Without an address there is no "forgot password" by mail for this account."""
    AccountService(db).confirm(user, data.password, request, request.state.session_id)
    user.email = None
    db.commit()


@router.get("/sessions", response_model=list[SessionRead])
def list_sessions(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return AccountService(db).sessions(user, request.state.session_id)


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    AccountService(db).revoke_other_sessions(user, request.state.session_id)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: int,
    request: Request,
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    AccountService(db).revoke_session(user, session_id)
    if session_id == request.state.session_id:
        clear_session_cookie(response)


@router.get("/export.json")
def export_account(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return JSONResponse(
        AccountService(db).export(user),
        headers={"Content-Disposition": 'attachment; filename="fahrma-my-data.json"'},
    )


@router.get("/deletion-preview", response_model=DeletionPreview)
def deletion_preview(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return AccountService(db).deletion_preview(user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    data: PasswordConfirmation,
    request: Request,
    response: Response,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    AccountService(db).delete_own(user, data.password, request, response, request.state.session_id)


@router.delete("/oidc", status_code=status.HTTP_204_NO_CONTENT)
def unlink_oidc(
    data: PasswordConfirmation, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """Remove the link to the provider; only while the account can still log in with its password."""
    if not user.has_password or not password_login_enabled():
        raise AppError(
            status.HTTP_409_CONFLICT,
            "last_login_method",
            "Set a password first; without the provider this account could not log in",
        )
    AccountService(db).confirm(user, data.password, request, request.state.session_id)
    OidcService(db).unlink(user, by="self")

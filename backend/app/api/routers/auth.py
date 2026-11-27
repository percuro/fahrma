from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.api.dependencies.clock import get_today
from app.config import get_default_timezone_name, get_operator_links, get_registration_mode, mail_enabled
from app.db.database import get_db
from app.errors import AppError
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import (
    ForgotPassword,
    LoginRequest,
    MeRead,
    OidcLinkRead,
    ProfileUpdate,
    RegisterRequest,
    RegistrationPending,
)
from app.services import group_service, setup_service
from app.services.auth_service import AccountError, AuthService, require_password_login
from app.services.invitation_service import InvitationService
from app.services.login_rate_limiter import LoginRateLimiter, login_rate_limiter

router = APIRouter()
# Every registration attempt counts (not only failures): at most 5 per IP address and hour
register_rate_limiter = LoginRateLimiter(window_seconds=60 * 60)
register_rate_limiter.ip_limit = 5


def me_response(db: Session, user, today: date) -> MeRead:
    return MeRead(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        locale=user.locale,
        role=user.role,
        email=user.email,
        email_pending=InvitationService(db).pending_email(user),
        groups=group_service.groups_of(db, user),
        today=today.isoformat(),
        timezone=get_default_timezone_name(),
        has_password=user.has_password,
        oidc=(
            OidcLinkRead(
                email=user.oidc_identity.email,
                preferred_username=user.oidc_identity.preferred_username,
                linked_at=user.oidc_identity.created_at,
            )
            if user.oidc_identity is not None
            else None
        ),
    )


@router.post("/login", response_model=MeRead)
def login(
    login_in: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    username = login_in.username.lower()
    ip_address = request.client.host if request.client else "unknown"
    login_rate_limiter.check(username, ip_address)
    try:
        user = AuthService(AuthRepository(db)).login(login_in, request, response)
    except AppError as exc:
        if exc.status_code == status.HTTP_401_UNAUTHORIZED:
            login_rate_limiter.record_failure(username, ip_address)
        raise
    login_rate_limiter.record_success(username)
    return me_response(db, user, today)


@router.post(
    "/register",
    response_model=MeRead,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"model": RegistrationPending, "description": "With e-mail: confirmation link sent"}},
)
def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Only with REGISTRATION=open; otherwise accounts come from invitation links.

    With e-mail set up, the address is required and the account is created when the link in
    the confirmation mail is used (202). Without e-mail the account exists right away (201).
    """
    if get_registration_mode() != "open":
        raise AppError(status.HTTP_403_FORBIDDEN, "registration_closed", "Registration is closed")
    require_password_login()
    if setup_service.needs_setup(db):
        # Otherwise a stranger could take over a fresh instance before its operator runs the setup
        raise AppError(status.HTTP_409_CONFLICT, "setup_required", "The instance has not been set up yet")
    if get_operator_links()["terms_url"] and not data.accept_terms:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "terms_not_accepted", "Please accept the terms")
    with_mail = mail_enabled()
    if with_mail and not data.email:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "email_required", "Please enter your e-mail address")
    ip_address = request.client.host if request.client else "unknown"
    register_rate_limiter.check(ip_address, ip_address)
    register_rate_limiter.record_failure(ip_address, ip_address)
    if with_mail:
        InvitationService(db, background).start_registration(data, request)
        return JSONResponse(
            RegistrationPending(email=data.email or "").model_dump(), status_code=status.HTTP_202_ACCEPTED
        )
    service = AuthService(AuthRepository(db))
    try:
        user = service.create_user(data.username, data.password, data.display_name, locale=data.locale)
    except AccountError as exc:
        raise exc.to_http() from exc
    service.start_session(user, request, response)
    return me_response(db, user, today)


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(data: ForgotPassword, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Mails a link to set a new password if the account has a confirmed address.

    The answer is the same whether the account exists or not.
    """
    require_password_login()
    InvitationService(db, background).request_password_reset(data.login, request)
    return {"status": "accepted"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    AuthService(AuthRepository(db)).logout(request, response)


@router.get("/me", response_model=MeRead)
def me(user=Depends(require_user), db: Session = Depends(get_db), today: date = Depends(get_today)):
    return me_response(db, user, today)


@router.patch("/me", response_model=MeRead)
def update_me(
    data: ProfileUpdate,
    user=Depends(require_user),
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    if data.display_name is not None:
        user.display_name = data.display_name.strip()
    if "locale" in data.model_fields_set:
        user.locale = data.locale
    db.commit()
    return me_response(db, user, today)

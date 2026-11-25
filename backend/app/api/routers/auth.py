from datetime import date

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.api.dependencies.clock import get_today
from app.config import get_default_timezone_name, get_operator_links, get_registration_mode
from app.db.database import get_db
from app.errors import AppError
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import LoginRequest, MeRead, ProfileUpdate, RegisterRequest
from app.services import group_service, setup_service
from app.services.auth_service import AccountError, AuthService
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
        groups=group_service.groups_of(db, user),
        today=today.isoformat(),
        timezone=get_default_timezone_name(),
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


@router.post("/register", response_model=MeRead, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    """Only with REGISTRATION=open; otherwise accounts come from invitation links."""
    if get_registration_mode() != "open":
        raise AppError(status.HTTP_403_FORBIDDEN, "registration_closed", "Registration is closed")
    if setup_service.needs_setup(db):
        # Otherwise a stranger could take over a fresh instance before its operator runs the setup
        raise AppError(status.HTTP_409_CONFLICT, "setup_required", "The instance has not been set up yet")
    if get_operator_links()["terms_url"] and not data.accept_terms:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "terms_not_accepted", "Please accept the terms")
    ip_address = request.client.host if request.client else "unknown"
    register_rate_limiter.check(ip_address, ip_address)
    register_rate_limiter.record_failure(ip_address, ip_address)
    service = AuthService(AuthRepository(db))
    try:
        user = service.create_user(data.username, data.password, data.display_name, locale=data.locale)
    except AccountError as exc:
        raise exc.to_http() from exc
    service.start_session(user, request, response)
    return me_response(db, user, today)


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

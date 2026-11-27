"""First-run setup: create the first account in the browser with the token from the log."""

from datetime import date

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.dependencies.clock import get_today
from app.api.routers.auth import me_response
from app.db.database import get_db
from app.errors import AppError
from app.models.oidc_state import PURPOSE_SETUP
from app.models.user import ROLE_ADMIN
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import MeRead
from app.schemas.oidc import OidcRedirect, SetupOidcStart
from app.services import setup_service
from app.services.auth_service import AccountError, AuthService, normalize_username, require_password_login
from app.services.client_address import client_ip
from app.services.login_rate_limiter import LoginRateLimiter
from app.services.oidc_service import OidcService

router = APIRouter()
# Counted per address: wrong tokens from someone else must not lock the operator out of the setup
setup_rate_limiter = LoginRateLimiter("setup", account_limit=5, ip_limit=5)


class SetupStatus(BaseModel):
    needed: bool


class SetupRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str | None = Field(default=None, max_length=80)
    password: str = Field(min_length=1, max_length=256)


def _already_done() -> AppError:
    return AppError(status.HTTP_409_CONFLICT, "setup_done", "Setup has already been completed")


def _check_token(token: str, request: Request, db: Session) -> None:
    ip_address = client_ip(request)
    setup_rate_limiter.check(ip_address, ip_address)
    if not setup_service.needs_setup(db):
        raise _already_done()
    if not setup_service.token_matches(token.strip()):
        setup_rate_limiter.record_failure(ip_address, ip_address)
        raise AppError(status.HTTP_403_FORBIDDEN, "setup_token_invalid", "Wrong setup token")


@router.get("", response_model=SetupStatus)
def setup_status(db: Session = Depends(get_db)):
    return SetupStatus(needed=setup_service.needs_setup(db))


@router.post("", response_model=MeRead)
def run_setup(
    data: SetupRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    today: date = Depends(get_today),
):
    require_password_login()
    _check_token(data.token, request, db)
    service = AuthService(AuthRepository(db))
    with setup_service.setup_lock():
        if not setup_service.needs_setup(db):
            raise _already_done()
        try:
            user = service.create_user(data.username, data.password, data.display_name, role=ROLE_ADMIN)
        except AccountError as exc:
            raise exc.to_http() from exc
    setup_service.clear_token()
    service.start_session(user, request, response)
    return me_response(db, user, today)


@router.post("/oidc", response_model=OidcRedirect)
def run_setup_with_oidc(data: SetupOidcStart, request: Request, response: Response, db: Session = Depends(get_db)):
    """The first account logs in through the provider; it is created in the callback."""
    _check_token(data.token, request, db)
    try:
        username = normalize_username(data.username)
    except AccountError as exc:
        raise exc.to_http() from exc
    payload = {"username": username, "display_name": data.display_name}
    return OidcRedirect(authorize_url=OidcService(db).start(PURPOSE_SETUP, request, response, payload=payload))

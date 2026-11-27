"""Login through the OIDC provider (OIDC_ISSUER); 404 oidc_disabled without it."""

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from app.config import get_operator_links, get_registration_mode
from app.db.database import get_db
from app.errors import AppError
from app.models.oidc_state import PURPOSE_LINK, PURPOSE_LOGIN, PURPOSE_REGISTER
from app.repositories.auth_repository import AuthRepository
from app.schemas.oidc import OidcRedirect, OidcStart
from app.services import setup_service
from app.services.account_service import AccountService
from app.services.auth_service import AuthService
from app.services.invitation_service import InvitationService
from app.services.oidc_service import OidcService

router = APIRouter()


@router.post("/start", response_model=OidcRedirect)
def start(data: OidcStart, request: Request, response: Response, db: Session = Depends(get_db)):
    """login and register: anyone. link (connect the logged-in account) and reauth (confirm a
    change): logged in."""
    service = OidcService(db)
    if data.purpose == PURPOSE_LOGIN:
        return OidcRedirect(authorize_url=service.start(PURPOSE_LOGIN, request, response))
    if data.purpose == PURPOSE_REGISTER:
        url = service.start(PURPOSE_REGISTER, request, response, payload=_register(data, db))
        return OidcRedirect(authorize_url=url)
    session = AuthService(AuthRepository(db)).current_session(request)
    user = session.user
    if data.purpose == PURPOSE_LINK:
        if user.oidc_identity is not None:
            raise AppError(status.HTTP_409_CONFLICT, "oidc_already_linked", "This account is already linked")
        # Otherwise a stolen session could add a permanent way in
        AccountService(db).confirm(user, data.password, request, session.id)
    url = service.start(data.purpose, request, response, user=user, session_id=session.id, return_to=data.return_to)
    return OidcRedirect(authorize_url=url)


def _register(data: OidcStart, db: Session) -> dict:
    """The same checks as the registration with a password, before the redirect."""
    if get_registration_mode() != "open":
        raise AppError(status.HTTP_403_FORBIDDEN, "registration_closed", "Registration is closed")
    if setup_service.needs_setup(db):
        raise AppError(status.HTTP_409_CONFLICT, "setup_required", "The instance has not been set up yet")
    if get_operator_links()["terms_url"] and not data.accept_terms:
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "terms_not_accepted", "Please accept the terms")
    username = InvitationService(db).check_new_username(data.username) if (data.username or "").strip() else None
    return {"username": username, "display_name": data.display_name, "locale": data.locale}


@router.get("/callback", include_in_schema=False)
def callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """The provider sends the browser here; always answers with a redirect into the web app."""
    return OidcService(db).callback(request, code, state, error)

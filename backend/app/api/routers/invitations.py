"""Public: whoever has a link may use it once. The token travels in the body, never in the URL."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies.auth import optional_user
from app.db.database import get_db
from app.models.oidc_state import PURPOSE_INVITE
from app.models.user import User
from app.schemas.invitation import InvitationAccept, InvitationAccepted, InvitationInfo, InvitationToken
from app.schemas.oidc import InvitationOidcStart, OidcRedirect
from app.services.invitation_service import InvitationService, kind_of
from app.services.oidc_service import OidcService

router = APIRouter()


@router.post("/inspect", response_model=InvitationInfo)
def inspect_invitation(data: InvitationToken, request: Request, db: Session = Depends(get_db)):
    return InvitationService(db).inspect(data.token, request)


@router.post("/accept", response_model=InvitationAccepted)
def accept_invitation(
    data: InvitationAccept,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
):
    """Group link: joins with the logged-in account, or creates one. Other links: signup, new password,
    confirming an e-mail address, finishing a registration."""
    return InvitationService(db, background).accept(data, request, response, user)


@router.post("/oidc", response_model=OidcRedirect)
def accept_invitation_with_oidc(
    data: InvitationOidcStart, request: Request, response: Response, db: Session = Depends(get_db)
):
    """Use a link through the provider: a new account without a password, or (password-reset
    link) linking the account instead of setting a new password. The link is used up in the
    callback, not here."""
    service = InvitationService(db)
    found = service.find_for_provider(data.token, request)
    payload = None
    if kind_of(found) != "password_reset":
        payload = {
            "username": service.check_new_username(data.username),
            "display_name": data.display_name,
            "locale": data.locale,
        }
    url = OidcService(db).start(PURPOSE_INVITE, request, response, found=found, payload=payload)
    return OidcRedirect(authorize_url=url)

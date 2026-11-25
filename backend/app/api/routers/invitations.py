"""Public: whoever has a link may use it once. The token travels in the body, never in the URL."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.dependencies.auth import optional_user
from app.db.database import get_db
from app.models.user import User
from app.schemas.invitation import InvitationAccept, InvitationAccepted, InvitationInfo, InvitationToken
from app.services.invitation_service import InvitationService

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

"""Operator API: for the operator's own tools, e.g. a billing service that sets a group's plan
after payment. Authenticated with the bearer token OPERATOR_TOKEN, never with a login; off
(404) unless the token is configured. It sees plans and counts, never entries or amounts."""

import hmac
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_operator_token
from app.db.database import get_db
from app.errors import AppError
from app.models.group import ROLE_ADMIN, Group, Membership
from app.models.user import User
from app.schemas.plans import BillingTokenCheck, BillingTokenRead, OperatorGroupRead, PlanUpdate
from app.services.billing_link import verify_token
from app.services.plans import get_group, list_groups, operator_group_read, set_plan


def require_operator(request: Request) -> str:
    token = get_operator_token()
    if token is None:
        raise AppError(status.HTTP_404_NOT_FOUND, "operator_api_disabled", "The operator API is not enabled")
    scheme, _, given = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(given.strip().encode(), token.encode()):
        raise AppError(status.HTTP_401_UNAUTHORIZED, "operator_unauthorized", "Wrong or missing operator token")
    return token


router = APIRouter(dependencies=[Depends(require_operator)])


@router.get("/groups", response_model=list[OperatorGroupRead])
def operator_list_groups(plan: str | None = None, db: Session = Depends(get_db)):
    """All groups with plan and counts; ?plan=<id> only those with that plan stored."""
    return list_groups(db, plan)


@router.get("/groups/{group_id}", response_model=OperatorGroupRead)
def read_group(group_id: int, db: Session = Depends(get_db)):
    return operator_group_read(db, get_group(db, group_id))


@router.put("/groups/{group_id}/plan", response_model=OperatorGroupRead)
def update_plan(group_id: int, data: PlanUpdate, db: Session = Depends(get_db)):
    group = get_group(db, group_id)
    set_plan(db, group, data.plan, data.until, data.note)
    db.commit()
    return operator_group_read(db, group)


@router.post("/billing-link/verify", response_model=BillingTokenRead)
def verify_billing_link(
    data: BillingTokenCheck, operator_token: str = Depends(require_operator), db: Session = Depends(get_db)
):
    """Checks a token from a billing link: who (still an admin of the group) wants to change which group."""
    claims = verify_token(data.token, datetime.now(UTC), operator_token)
    group = db.get(Group, claims.get("g"))
    user = db.get(User, claims.get("u"))
    is_admin = (
        group is not None
        and user is not None
        and user.is_active
        and not user.is_deleted
        and db.scalar(
            select(Membership.id).where(
                Membership.group_id == group.id,
                Membership.user_id == user.id,
                Membership.role == ROLE_ADMIN,
                Membership.active.is_(True),
            )
        )
        is not None
    )
    if not is_admin:
        raise AppError(status.HTTP_409_CONFLICT, "billing_not_admin", "The person is no longer an admin of the group")
    return {
        "group": operator_group_read(db, group),
        "user": {"user_id": user.id, "display_name": user.display_name, "email": user.email, "locale": user.locale},
        "expires_at": datetime.fromtimestamp(claims["exp"], UTC),
    }

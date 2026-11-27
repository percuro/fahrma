from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import __version__
from app.config import (
    get_billing_url,
    get_inactive_delete_months,
    get_oidc_settings,
    get_operator_links,
    get_plans,
    get_registration_mode,
    mail_enabled,
    password_login_enabled,
    receipts_enabled,
)
from app.db.database import get_db
from app.schemas.invitation import MetaRead
from app.schemas.oidc import OidcMeta
from app.services import push, setup_service
from app.services.limits import limits
from app.services.plans import plan_info

router = APIRouter()


@router.get("/meta", response_model=MetaRead)
def meta(db: Session = Depends(get_db)):
    """Public facts the app needs: registration mode, operator links, limits, plans, e-mail, Web Push."""
    plans = get_plans()
    oidc = get_oidc_settings()
    return MetaRead(
        version=__version__,
        registration=get_registration_mode(),
        setup_needed=setup_service.needs_setup(db),
        links=get_operator_links(),
        limits=limits(),
        mail=mail_enabled(),
        vapid_public_key=push.vapid_public_key(db),
        plans=[plan_info(plan) for plan in plans.plans.values()] if plans.configured else None,
        default_plan=plans.default if plans.configured else None,
        billing=get_billing_url() is not None,
        inactive_delete_months=get_inactive_delete_months(),
        receipts=receipts_enabled(),
        password_login=password_login_enabled(),
        oidc=OidcMeta(label=oidc.label) if oidc is not None else None,
    )

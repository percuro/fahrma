"""Push notifications of the logged-in account: which ones, and which devices receive them."""

from fastapi import APIRouter, BackgroundTasks, Depends, Request, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import require_user
from app.api.dependencies.clock import Clock, get_clock
from app.config import PushSettings, get_push_settings
from app.db.database import get_db
from app.errors import AppError
from app.models.push import PushSubscription
from app.models.user import User
from app.schemas.notifications import (
    NotificationsRead,
    NotifySettings,
    PushSubscriptionDelete,
    PushSubscriptionWrite,
)
from app.services import notification_service, push
from app.services.login_rate_limiter import LoginRateLimiter
from app.services.mail_texts import LOCALES

router = APIRouter()

# Test messages: a handful per hour and account is plenty
push_test_limiter = LoginRateLimiter(window_seconds=60 * 60)
push_test_limiter.account_limit = 10
push_test_limiter.ip_limit = 60


def _require_push() -> PushSettings:
    settings = get_push_settings()
    if settings is None:
        raise AppError(status.HTTP_409_CONFLICT, "push_disabled", "Push notifications are switched off here")
    return settings


def _read(db: Session, user: User, session_id: int) -> NotificationsRead:
    rows = db.execute(
        select(PushSubscription.session_id, func.count())
        .where(PushSubscription.user_id == user.id)
        .group_by(PushSubscription.session_id)
    ).all()
    return NotificationsRead(
        settings=notification_service.settings_of(user),
        this_device=any(sid == session_id for sid, _count in rows),
        devices=len(rows),
    )


@router.get("/notifications", response_model=NotificationsRead)
def read_notifications(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _read(db, user, request.state.session_id)


@router.put("/notifications", response_model=NotificationsRead)
def update_notifications(
    data: NotifySettings, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    notification_service.store_settings(db, user, data)
    return _read(db, user, request.state.session_id)


@router.post("/push-subscription", response_model=NotificationsRead)
def subscribe(
    data: PushSubscriptionWrite, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)
):
    """This device receives notifications; the same browser logged in again takes its subscription along."""
    settings = _require_push()
    if not push.endpoint_allowed(data.endpoint, settings):
        raise AppError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "push_service_unknown",
            "This browser's push service is not allowed on this instance",
        )
    if not push.keys_valid(data.keys.p256dh, data.keys.auth):
        raise AppError(status.HTTP_422_UNPROCESSABLE_CONTENT, "push_subscription_invalid", "Invalid subscription")
    subscription = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == data.endpoint))
    if subscription is None:
        subscription = PushSubscription(endpoint=data.endpoint)
        db.add(subscription)
    subscription.user_id = user.id
    subscription.session_id = request.state.session_id
    subscription.p256dh = data.keys.p256dh
    subscription.auth = data.keys.auth
    subscription.locale = data.locale if data.locale in LOCALES else None
    db.commit()
    return _read(db, user, request.state.session_id)


@router.delete("/push-subscription", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(data: PushSubscriptionDelete, user: User = Depends(require_user), db: Session = Depends(get_db)):
    db.execute(
        delete(PushSubscription).where(PushSubscription.endpoint == data.endpoint, PushSubscription.user_id == user.id)
    )
    db.commit()


@router.post("/push-test", status_code=status.HTTP_202_ACCEPTED)
def send_test(
    request: Request,
    background: BackgroundTasks,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    clock: Clock = Depends(get_clock),
):
    """A test notification to this device."""
    _require_push()
    ip_address = request.client.host if request.client else "unknown"
    push_test_limiter.check(str(user.id), ip_address)
    items = notification_service.push_test_items(db, user, request.state.session_id, clock.now())
    if not items:
        raise AppError(status.HTTP_409_CONFLICT, "push_not_subscribed", "This device does not receive notifications")
    push_test_limiter.record_failure(str(user.id), ip_address)  # counts every test, not only failures
    notification_service.deliver_later(background, db, items)
    return {"devices": len(items)}

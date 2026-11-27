"""Security log: logins and changes to accounts, for instance admins and the account itself.

- Entries copy the usernames involved, so they stay readable after an account is deleted.
- They never contain passwords, tokens or links, and no username that has no account.
- IP addresses are stored only shortened (IPv4 /24, IPv6 /48) and only for failed attempts
  and blocks; a block is logged once, not for every refused request.
- Entries older than SECURITY_LOG_DAYS are removed when a new one is written, at most once an hour.

Group contents and group membership are in the group's own change log, not here.
"""

import json
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.config import get_security_log_days
from app.models.security_event import SecurityEvent
from app.models.user import User
from app.services.client_address import client_ip, ip_prefix
from app.services.login_rate_limiter import LoginRateLimiter

# Events that mean someone tried and failed; shown highlighted, filterable, with the address
FAILURE_EVENTS = (
    "auth.login_failed",
    "auth.confirm_failed",
    "auth.oidc_failed",
    "auth.rate_limited",
    "setup.failed",
)

PRUNE_INTERVAL_SECONDS = 60 * 60
_prune_lock = Lock()
_last_prune: float | None = None


def utcnow() -> datetime:
    # naive UTC like the rest of the database (auth_service imports this module, so not from there)
    return datetime.now(UTC).replace(tzinfo=None)


def record(
    db: Session,
    event: str,
    *,
    actor: User | None = None,
    target: User | None = None,
    request: Request | None = None,
    commit: bool = True,
    **details: Any,
) -> None:
    """Add an entry. With commit=False it is stored together with the caller's next commit.

    Pass `request` only for failed attempts and blocks: then the shortened address is stored.
    """
    db.add(
        SecurityEvent(
            created_at=utcnow(),
            event=event,
            actor_user_id=actor.id if actor is not None else None,
            actor_username=actor.username if actor is not None else None,
            target_user_id=target.id if target is not None else None,
            target_username=target.username if target is not None else None,
            ip_prefix=ip_prefix(client_ip(request)) if request is not None else None,
            details=json.dumps(details, ensure_ascii=False, sort_keys=True) if details else None,
        )
    )
    # Write the row now, before e.g. the account is anonymized in the same transaction
    db.flush()
    _maybe_prune(db)
    if commit:
        db.commit()


def count_failure(
    db: Session,
    limiter: LoginRateLimiter,
    key: str,
    request: Request,
    *,
    ip_key: str | None = None,
    target: User | None = None,
) -> None:
    """Count a failed or limited attempt; log `auth.rate_limited` once, when it reaches the limit."""
    if limiter.record_failure(key, ip_key if ip_key is not None else client_ip(request)):
        record(db, "auth.rate_limited", target=target, request=request, limiter=limiter.name)


def prune(db: Session, now: datetime | None = None) -> int:
    cutoff = (now or utcnow()) - timedelta(days=get_security_log_days())
    return db.execute(delete(SecurityEvent).where(SecurityEvent.created_at < cutoff)).rowcount


def _maybe_prune(db: Session) -> None:
    global _last_prune
    with _prune_lock:
        now = monotonic()
        if _last_prune is not None and now - _last_prune < PRUNE_INTERVAL_SECONDS:
            return
        _last_prune = now
    prune(db)


def reset_prune_timer() -> None:
    """Tests: let the next entry prune again."""
    global _last_prune
    with _prune_lock:
        _last_prune = None


def list_events(
    db: Session,
    *,
    before_id: int | None = None,
    limit: int = 50,
    user_id: int | None = None,
    failures: bool = False,
) -> list[SecurityEvent]:
    """Newest first; `user_id` keeps the entries in which the account acted or was acted on."""
    query = select(SecurityEvent).order_by(SecurityEvent.id.desc()).limit(limit)
    if before_id is not None:
        query = query.where(SecurityEvent.id < before_id)
    if user_id is not None:
        query = query.where((SecurityEvent.actor_user_id == user_id) | (SecurityEvent.target_user_id == user_id))
    if failures:
        query = query.where(SecurityEvent.event.in_(FAILURE_EVENTS))
    return list(db.scalars(query))


def details_of(event: SecurityEvent) -> dict[str, Any]:
    return json.loads(event.details) if event.details else {}


def own_events(db: Session, user: User, *, before_id: int | None = None, limit: int = 50) -> list[SecurityEvent]:
    """The entries about the account itself; what an admin did elsewhere (other accounts, plans) is not here."""
    query = select(SecurityEvent).where(SecurityEvent.target_user_id == user.id).order_by(SecurityEvent.id.desc())
    query = query.limit(limit)
    if before_id is not None:
        query = query.where(SecurityEvent.id < before_id)
    return list(db.scalars(query))


def export_rows(db: Session, user: User) -> list[dict[str, Any]]:
    """The account's own entries for "My data", as the account sees them."""
    rows = [own_view(event, user.id) for event in own_events(db, user, limit=100_000)]
    return [{**row, "created_at": row["created_at"].isoformat()} for row in rows]


def own_view(event: SecurityEvent, user_id: int) -> dict[str, Any]:
    """An entry as the account itself sees it: an instance admin who acted stays unnamed."""
    if event.actor_user_id is None:
        actor = None
    elif event.actor_user_id == user_id:
        actor = "self"
    else:
        actor = "admin"
    return {
        "id": event.id,
        "created_at": event.created_at,
        "event": event.event,
        "actor": actor,
        "ip_prefix": event.ip_prefix,
        "details": details_of(event),
    }

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class SecurityEventRead(BaseModel):
    """An entry as instance admins see it."""

    id: int
    created_at: datetime
    # e.g. auth.login, auth.login_failed, auth.rate_limited, account.password_changed, admin.role_changed
    event: str
    actor_user_id: int | None
    actor_username: str | None
    target_user_id: int | None
    target_username: str | None
    # Only for failed attempts and blocks, shortened: IPv4 /24, IPv6 /48
    ip_prefix: str | None
    details: dict[str, Any]


class SecurityEventPage(BaseModel):
    events: list[SecurityEventRead]
    # Pass as before_id for the next (older) page; None = no older entries
    next_before_id: int | None
    # SECURITY_LOG_DAYS: how long entries are kept
    retention_days: int


class OwnSecurityEventRead(BaseModel):
    """An entry about the own account: "self" or an instance "admin" did it, or nobody (None)."""

    id: int
    created_at: datetime
    event: str
    actor: Literal["self", "admin"] | None
    ip_prefix: str | None
    details: dict[str, Any]


class OwnSecurityEventPage(BaseModel):
    events: list[OwnSecurityEventRead]
    next_before_id: int | None

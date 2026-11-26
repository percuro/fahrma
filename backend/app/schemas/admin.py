from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.auth import RoleLiteral


class AdminUserRead(BaseModel):
    """What an instance admin sees about an account: no trips, no amounts."""

    id: int
    username: str
    display_name: str
    # Confirmed address, so admins can reach the person and mail a reset link
    email: str | None = None
    role: RoleLiteral
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None
    group_count: int
    # INACTIVE_DELETE_MONTHS: the day this account will be deleted unless it is used again
    deletion_due: date | None = None


class AdminUserUpdate(BaseModel):
    role: RoleLiteral | None = None
    is_active: bool | None = None

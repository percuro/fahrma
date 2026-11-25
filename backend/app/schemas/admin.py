from datetime import datetime

from pydantic import BaseModel

from app.schemas.auth import RoleLiteral


class AdminUserRead(BaseModel):
    """What an instance admin sees about an account: no trips, no amounts."""

    id: int
    username: str
    display_name: str
    role: RoleLiteral
    is_active: bool
    created_at: datetime
    last_seen_at: datetime | None
    group_count: int


class AdminUserUpdate(BaseModel):
    role: RoleLiteral | None = None
    is_active: bool | None = None

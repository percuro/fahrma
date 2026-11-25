from datetime import datetime

from pydantic import BaseModel, Field


class GroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class GroupUpdate(BaseModel):
    """Only the fields that are sent change; timezone null = the instance default."""

    name: str | None = Field(default=None, min_length=1, max_length=80)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    timezone: str | None = Field(default=None, max_length=64)


class MemberRead(BaseModel):
    user_id: int
    username: str
    display_name: str
    role: str
    active: bool


class MemberUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(admin|member)$")
    active: bool | None = None


class GroupRead(BaseModel):
    id: int
    name: str
    currency: str
    timezone: str | None
    effective_timezone: str
    today: str
    my_role: str
    members: list[MemberRead]


class InviteCreated(BaseModel):
    url: str
    token: str
    expires_at: datetime


class InvitePreview(BaseModel):
    group_name: str
    valid: bool

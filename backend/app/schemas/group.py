from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.auth import Email


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
    # The account was deleted; the bookings stay under an anonymous name
    deleted: bool = False
    # A person without an account (imported or added by an admin)
    placeholder: bool = False
    # Admins only: until when the open personal link of a placeholder works
    link_expires_at: datetime | None = None


class MemberUpdate(BaseModel):
    role: str | None = Field(default=None, pattern=r"^(admin|member)$")
    active: bool | None = None
    # Only for people without an account
    display_name: str | None = Field(default=None, min_length=1, max_length=80)


class PlaceholderCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)


class InviteCreate(BaseModel):
    """Optional body of a new group link: send it by e-mail as well."""

    email: Email | None = None


class GroupRead(BaseModel):
    id: int
    name: str
    currency: str
    timezone: str | None
    effective_timezone: str
    today: str
    my_role: str
    members: list[MemberRead]


class GroupDelete(BaseModel):
    # The group's name, typed again as confirmation
    name: str = Field(min_length=1, max_length=80)

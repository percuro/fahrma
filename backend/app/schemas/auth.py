from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

RoleLiteral = Literal["admin", "user"]
LOCALE_PATTERN = r"^(de|en)$"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    """Open registration (REGISTRATION=open); the username rules are checked by the service."""

    username: str = Field(min_length=1, max_length=80)
    display_name: str | None = Field(default=None, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)
    # Required when the operator set TERMS_URL
    accept_terms: bool = False


class GroupBrief(BaseModel):
    id: int
    name: str
    role: str


class MeRead(BaseModel):
    id: int
    username: str
    display_name: str
    locale: str | None
    role: RoleLiteral
    groups: list[GroupBrief]
    today: str
    timezone: str


class ProfileUpdate(BaseModel):
    """Only the fields that are sent change; locale null = follow the browser."""

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)


class PasswordConfirmation(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SessionRead(BaseModel):
    id: int
    created_at: datetime
    last_seen_at: datetime | None
    # e.g. "iPhone · Safari"; None if the browser could not be recognised
    device: str | None
    current: bool


class GroupRef(BaseModel):
    id: int
    name: str


class AdminHandover(BaseModel):
    group_id: int
    group_name: str
    new_admin_name: str


class DeletionPreview(BaseModel):
    """What deleting the account does to the groups (shown before confirming)."""

    # Groups without any other active member are deleted with the account
    groups_deleted: list[GroupRef]
    # Groups where the account is the last admin: the longest-standing member takes over
    admin_handover: list[AdminHandover]
    # Groups that keep the bookings under an anonymous name
    groups_kept: list[GroupRef]

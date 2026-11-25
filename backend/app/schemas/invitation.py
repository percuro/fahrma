from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import LOCALE_PATTERN, Email, RoleLiteral

PurposeLiteral = Literal["signup", "password_reset", "verify_email", "registration"]
KindLiteral = Literal["group", "signup", "password_reset", "verify_email", "registration"]


class InvitationCreate(BaseModel):
    role: RoleLiteral = "user"
    # e.g. "for Anna", so the admin can tell open invitations apart
    note: str | None = Field(default=None, max_length=80)
    # Send the link to this address as well (needs e-mail on the instance)
    email: Email | None = None

    @field_validator("note")
    @classmethod
    def strip_note(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None


class InvitationCreated(BaseModel):
    id: int
    purpose: PurposeLiteral
    # Shown only now; the token is only stored as a hash
    url: str
    expires_at: datetime
    email_sent: bool = False


class PasswordResetCreate(BaseModel):
    # Mail the link to the account's confirmed address instead of only showing it
    send_email: bool = False


class InvitationRead(BaseModel):
    id: int
    purpose: PurposeLiteral
    role: RoleLiteral | None
    note: str | None
    # signup: the address the link was sent to
    email: str | None = None
    # password_reset: the account whose password is set
    target_username: str | None
    created_by_username: str | None
    created_at: datetime
    expires_at: datetime


class InvitationToken(BaseModel):
    token: str = Field(min_length=1, max_length=200)


class InvitationInfo(BaseModel):
    kind: KindLiteral
    # group: the group the link leads to
    group_name: str | None = None
    # group, personal link: the member without an account whose place the link takes over
    member_name: str | None = None
    # password_reset, registration: the account
    username: str | None = None
    # verify_email, registration: the address being confirmed
    email: str | None = None
    expires_at: datetime


class InvitationAccept(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    # New account (signup, or a group invitation without being logged in)
    username: str | None = Field(default=None, max_length=80)
    display_name: str | None = Field(default=None, max_length=80)
    # New account or password reset; not needed to join a group while logged in
    password: str | None = Field(default=None, max_length=256)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)


class InvitationAccepted(BaseModel):
    kind: KindLiteral
    # group: where to go next
    group_id: int | None


class GroupInviteCreated(BaseModel):
    url: str
    expires_at: datetime
    email_sent: bool = False


class OperatorLinks(BaseModel):
    imprint_url: str | None
    privacy_url: str | None
    terms_url: str | None


class Limits(BaseModel):
    groups_per_user: int | None
    members_per_group: int | None
    cars_per_group: int | None


class MetaRead(BaseModel):
    version: str
    registration: Literal["invite", "open"]
    setup_needed: bool
    links: OperatorLinks
    limits: Limits
    # E-mail is set up: forgotten password, addresses, links by mail
    mail: bool
    # Web Push: the key for PushManager.subscribe(); None = push notifications are off
    vapid_public_key: str | None = None

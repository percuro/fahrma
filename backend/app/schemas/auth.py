from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

RoleLiteral = Literal["admin", "user"]
LOCALE_PATTERN = r"^(de|en)$"

# A plausible address; whether it works shows when the confirmation link arrives.
# No whitespace, so it can never break the header of a mail. Stored in lower case.
EMAIL_PATTERN = r"^[^@\s]{1,64}@[^@\s.]+(\.[^@\s.]+)+$"
Email = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=254, pattern=EMAIL_PATTERN),
    AfterValidator(str.lower),
]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    """Open registration (REGISTRATION=open); the username rules are checked by the service."""

    username: str = Field(min_length=1, max_length=80)
    display_name: str | None = Field(default=None, max_length=80)
    password: str = Field(min_length=1, max_length=256)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)
    # Required when e-mail is set up: the account is created once the address is confirmed
    email: Email | None = None
    # Required when the operator set TERMS_URL
    accept_terms: bool = False


class RegistrationPending(BaseModel):
    """Open registration with e-mail: a link was sent, the account follows on confirmation."""

    email: str


class ForgotPassword(BaseModel):
    # Username or confirmed e-mail address
    login: str = Field(min_length=1, max_length=254)


class EmailChange(BaseModel):
    email: Email
    # Accounts without a password confirm at the provider instead (reauth)
    password: str | None = Field(default=None, min_length=1, max_length=256)


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
    # Confirmed address, and one waiting for confirmation
    email: str | None = None
    email_pending: str | None = None
    groups: list[GroupBrief]
    today: str
    timezone: str
    # False: the account logs in through the OIDC provider only (since 0.11)
    has_password: bool = True
    oidc: "OidcLinkRead | None" = None


class OidcLinkRead(BaseModel):
    """The account's link to the OIDC provider, as the provider last described it."""

    email: str | None
    preferred_username: str | None
    linked_at: datetime


class ProfileUpdate(BaseModel):
    """Only the fields that are sent change; locale null = follow the browser."""

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)


class PasswordConfirmation(BaseModel):
    # Accounts without a password confirm at the provider instead (reauth)
    password: str | None = Field(default=None, min_length=1, max_length=256)


class PasswordChange(BaseModel):
    # None: an account without a password sets its first one (after a fresh login at the provider)
    current_password: str | None = Field(default=None, min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SessionRead(BaseModel):
    id: int
    created_at: datetime
    last_seen_at: datetime | None
    # e.g. "iPhone · Safari"; None if the browser could not be recognised
    device: str | None
    current: bool
    # "password" or "oidc" (since 0.11)
    auth_method: str = "password"


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


MeRead.model_rebuild()

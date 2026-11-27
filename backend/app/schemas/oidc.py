from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.auth import LOCALE_PATTERN


class OidcStart(BaseModel):
    purpose: Literal["login", "register", "link", "reauth"] = "login"
    # link/reauth: where to return in the web app ("/profile", "/admin" or "/")
    return_to: str | None = Field(default=None, max_length=64)
    # link: accounts with a password confirm it first
    password: str | None = Field(default=None, min_length=1, max_length=256)
    # register: the new account (the username is suggested from the provider when empty)
    username: str | None = Field(default=None, max_length=80)
    display_name: str | None = Field(default=None, max_length=80)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)
    # register: required when the operator set TERMS_URL
    accept_terms: bool = False


class OidcRedirect(BaseModel):
    """Send the browser here (window.location), it comes back through the callback."""

    authorize_url: str


class InvitationOidcStart(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    # New account (group link, personal link, instance invitation); not for a password reset
    username: str | None = Field(default=None, max_length=80)
    display_name: str | None = Field(default=None, max_length=80)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)


class SetupOidcStart(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    username: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str | None = Field(default=None, max_length=80)


class OidcMeta(BaseModel):
    # Name on the button; None = the app's translated "single sign-on"
    label: str | None

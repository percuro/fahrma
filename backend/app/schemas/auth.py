from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    token: str = Field(min_length=10, max_length=200)
    username: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    display_name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class GroupBrief(BaseModel):
    id: int
    name: str
    role: str


LOCALE_PATTERN = r"^(de|en)$"


class MeRead(BaseModel):
    id: int
    username: str
    display_name: str
    locale: str | None
    groups: list[GroupBrief]
    today: str
    timezone: str


class ProfileUpdate(BaseModel):
    """Only the fields that are sent change; locale null = follow the browser."""

    display_name: str | None = Field(default=None, min_length=1, max_length=80)
    locale: str | None = Field(default=None, pattern=LOCALE_PATTERN)

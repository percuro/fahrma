from typing import Literal

from pydantic import BaseModel, Field

LEAD_MINUTES = (15, 60, 180)


class NotifySettings(BaseModel):
    """Which push notifications an account wants; every one can be switched off."""

    # Before the own reservation starts
    reservation_reminder: bool = True
    lead_minutes: Literal[15, 60, 180] = 60
    # Someone else reserved, moved or cancelled a reservation for me
    reservation_changes: bool = True
    # A trip I started is still running (12 hours, or my reservation is over)
    open_trip: bool = True
    # A new settlement in one of my groups
    settlements: bool = True


class NotificationsRead(BaseModel):
    settings: NotifySettings
    # This device (the current login) receives push notifications
    this_device: bool
    # Devices of the account that receive them
    devices: int


class SubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=80, max_length=100)
    auth: str = Field(min_length=16, max_length=50)


class PushSubscriptionWrite(BaseModel):
    """What PushSubscription.toJSON() gives in the browser, plus the interface language."""

    endpoint: str = Field(min_length=10, max_length=1000)
    keys: SubscriptionKeys
    locale: str | None = Field(default=None, max_length=5)


class PushSubscriptionDelete(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)

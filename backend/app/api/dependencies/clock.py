from datetime import UTC, date, datetime

from fastapi import Depends

from app.api.dependencies.group import require_member
from app.config import get_default_timezone_name, get_zone
from app.services.access import GroupContext


class Clock:
    """Current time; replaceable in tests via dependency_overrides[get_clock]."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self, timezone: str | None = None) -> date:
        """Today in the given IANA time zone (default: DEFAULT_TIMEZONE), never the server clock's date."""
        return self.now().astimezone(get_zone(timezone or get_default_timezone_name())).date()


class FixedClock(Clock):
    def __init__(self, day: date):
        self.day = day

    def now(self) -> datetime:
        return datetime(self.day.year, self.day.month, self.day.day, 12, tzinfo=UTC)

    def today(self, timezone: str | None = None) -> date:
        return self.day


def get_clock() -> Clock:
    return Clock()


def get_today(clock: Clock = Depends(get_clock)) -> date:
    """Today in the instance's default time zone."""
    return clock.today()


def get_group_today(ctx: GroupContext = Depends(require_member), clock: Clock = Depends(get_clock)) -> date:
    """Today in the group's time zone (falls back to the instance default)."""
    return clock.today(ctx.group.timezone)

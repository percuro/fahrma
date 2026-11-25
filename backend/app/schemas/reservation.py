import datetime as dt

from pydantic import BaseModel, Field


class ReservationWrite(BaseModel):
    """Times are wall-clock times in the group's time zone, e.g. "2026-12-03T08:00".

    A time with an offset ("…+01:00", "…Z") is taken as that moment instead.
    """

    car_id: int
    user_id: int
    starts_at: dt.datetime
    ends_at: dt.datetime
    note: str | None = Field(default=None, max_length=200)


class ReservationRead(BaseModel):
    id: int
    car_id: int
    user_id: int
    # In the group's time zone, without offset
    starts_at: dt.datetime
    ends_at: dt.datetime
    # The same moments in UTC, with offset
    starts_at_utc: dt.datetime
    ends_at_utc: dt.datetime
    note: str | None
    created_by: int

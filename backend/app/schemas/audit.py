import datetime as dt

from pydantic import BaseModel


class AuditRead(BaseModel):
    id: int
    user_id: int
    entity: str
    entity_id: int
    action: str
    diff: dict | None
    created_at: dt.datetime

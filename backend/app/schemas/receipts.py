from datetime import datetime

from pydantic import BaseModel


class ReceiptRead(BaseModel):
    """A receipt photo; the image is at GET /v1/groups/{group_id}/receipts/{id}."""

    id: int
    content_type: str
    bytes: int
    width: int
    height: int
    created_by: int
    created_at: datetime

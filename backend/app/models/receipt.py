from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

# Content types accepted for receipt photos, with the file extension they are stored under
RECEIPT_TYPES = {"image/jpeg": "jpg", "image/webp": "webp"}
# Photos per entry: enough for a multi-page invoice
MAX_RECEIPTS_PER_ENTRY = 5


class Receipt(Base):
    """A photo of a receipt, attached to exactly one fuel entry or expense.

    The image itself is a file in the receipts directory (app.services.receipt_store), named by
    ``file``; the row holds what the app needs without reading it.
    """

    __tablename__ = "receipts"
    __table_args__ = (
        CheckConstraint("(fuel_id IS NULL) != (expense_id IS NULL)", name="ck_receipt_owner"),
        CheckConstraint("bytes > 0", name="ck_receipt_bytes"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    fuel_id: Mapped[int | None] = mapped_column(
        ForeignKey("fuel_entries.id", ondelete="CASCADE"), nullable=True, index=True
    )
    expense_id: Mapped[int | None] = mapped_column(
        ForeignKey("expenses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Random file name inside the group's directory, e.g. "3f2a….jpg"
    file: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    content_type: Mapped[str] = mapped_column(String(20), nullable=False)
    bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

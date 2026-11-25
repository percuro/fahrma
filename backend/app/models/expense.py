import datetime as dt
from datetime import datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

CATEGORIES = (
    "insurance",
    "tax",
    "service",
    "repair",
    "inspection",  # periodic roadworthiness test
    "tires",
    "vignette",  # motorway toll sticker
    "parking",
    "toll",
    "wash",
    "other",
)

# by_km: by driven km · equal: equally among active members
# single: one person · trip: like the shares of the linked trip
ALLOCATIONS = ("by_km", "equal", "single", "trip")


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="ck_expense_amount"),
        CheckConstraint("allocation IN ('by_km', 'equal', 'single', 'trip')", name="ck_expense_allocation"),
        CheckConstraint("allocation != 'single' OR allocated_user_id IS NOT NULL", name="ck_expense_single"),
        CheckConstraint("allocation != 'trip' OR trip_id IS NOT NULL", name="ck_expense_trip"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    car_id: Mapped[int | None] = mapped_column(ForeignKey("cars.id"), nullable=True, index=True)
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trips.id", ondelete="RESTRICT"), nullable=True, index=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    paid_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    allocation: Mapped[str] = mapped_column(String(10), nullable=False)
    allocated_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("settlements.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

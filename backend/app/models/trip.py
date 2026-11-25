import datetime as dt
from datetime import datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Trip(Base):
    """A trip between two odometer readings. end_km NULL = the trip is still running."""

    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("start_km >= 0", name="ck_trip_start_km"),
        CheckConstraint("end_km IS NULL OR end_km >= start_km", name="ck_trip_end_km"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    car_id: Mapped[int] = mapped_column(ForeignKey("cars.id"), nullable=False, index=True)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False, index=True)
    start_km: Mapped[int] = mapped_column(Integer, nullable=False)
    end_km: Mapped[int | None] = mapped_column(Integer, nullable=True)
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    settlement_id: Mapped[int | None] = mapped_column(ForeignKey("settlements.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    shares: Mapped[list["TripShare"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripShare.id"
    )
    external_payments: Mapped[list["TripExternalPayment"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="TripExternalPayment.id"
    )

    @property
    def km(self) -> int | None:
        return None if self.end_km is None else self.end_km - self.start_km


class TripShare(Base):
    """Who bears a trip. Several rows = a shared trip, split by weight."""

    __tablename__ = "trip_shares"
    __table_args__ = (
        UniqueConstraint("trip_id", "user_id", name="uq_trip_share_user"),
        CheckConstraint("weight >= 1", name="ck_trip_share_weight"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    trip: Mapped[Trip] = relationship(back_populates="shares")


class TripExternalPayment(Base):
    """Money from someone outside the group (a passenger) that a member received for the trip."""

    __tablename__ = "trip_external_payments"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="ck_external_amount"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), nullable=False, index=True)
    payer_name: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    received_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    trip: Mapped[Trip] = relationship(back_populates="external_payments")

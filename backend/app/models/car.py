from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Car(Base):
    __tablename__ = "cars"
    __table_args__ = (CheckConstraint("energy_unit IN ('l', 'kWh')", name="ck_car_energy_unit"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    plate: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # odometer when the car was added: trips are expected from here on
    start_odometer_km: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # What fuel entries of this car measure: litres (combustion) or kWh (electric)
    energy_unit: Mapped[str] = mapped_column(String(8), nullable=False, default="l", server_default="l")
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

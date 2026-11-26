from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.user import User

ROLE_ADMIN = "admin"
ROLE_MEMBER = "member"


class Group(Base):
    """A group of people sharing one or more cars."""

    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    # IANA time zone that defines "today" for this group; NULL = the instance's DEFAULT_TIMEZONE
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    # Hosting: the group's plan (an id from PLANS_FILE); NULL = the default plan
    plan: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Last day the plan is valid (inclusive, in the group's time zone); NULL = no end
    plan_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # For the operator only (e.g. an invoice number); never shown to the group
    plan_note: Mapped[str | None] = mapped_column(String(200), nullable=True)

    memberships: Mapped[list["Membership"]] = relationship(back_populates="group", cascade="all, delete-orphan")


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_membership_group_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_MEMBER)
    # Members who left stay for old entries but no longer count for "equal" splits
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    group: Mapped[Group] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship()


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Personal link for a placeholder member: whoever uses it becomes that member
    placeholder_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Address the link was sent to, if any
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    group: Mapped[Group] = relationship()

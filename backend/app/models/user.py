from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

# Role on the instance; separate from the role within a group (Membership.role)
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_ADMIN, ROLE_USER)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Confirmed address only (an unconfirmed one waits in an Invitation); used for links by e-mail
    email: Mapped[str | None] = mapped_column(String(254), nullable=True, unique=True, index=True)
    # Interface language ("de", "en"); NULL = follow the browser
    locale: Mapped[str | None] = mapped_column(String(5), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=ROLE_USER, server_default=ROLE_USER)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Deleted accounts stay as an anonymous row, because the bookings of a group refer to them
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A member of an imported group who has no account yet; cannot log in, can be claimed by link
    placeholder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # Which push notifications the account wants (JSON, see schemas/notifications.py); NULL = defaults
    notify: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class UserSession(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    # Updated at most every few minutes, not on every request
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Only to tell devices apart in the device list; no IP address is stored
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")

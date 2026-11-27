from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base

# Role on the instance; separate from the role within a group (Membership.role)
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLES = (ROLE_ADMIN, ROLE_USER)
# How a session was started
AUTH_PASSWORD = "password"
AUTH_OIDC = "oidc"
# password_hash of accounts without a password (placeholders, deleted accounts, OIDC only);
# matches no password
NO_PASSWORD = "!"


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
    # INACTIVE_DELETE_MONTHS: when the account was warned that it will be deleted; a later
    # login (last_seen_at) makes the warning void
    inactivity_warned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Deleted accounts stay as an anonymous row, because the bookings of a group refer to them
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # A member of an imported group who has no account yet; cannot log in, can be claimed by link
    placeholder: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    # Which push notifications the account wants (JSON, see schemas/notifications.py); NULL = defaults
    notify: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    # At most one link to the OIDC provider per account
    oidc_identity: Mapped["OidcIdentity | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    @property
    def has_password(self) -> bool:
        return self.password_hash != NO_PASSWORD

    @property
    def oidc_linked(self) -> bool:
        return self.oidc_identity is not None


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
    auth_method: Mapped[str] = mapped_column(
        String(16), nullable=False, default=AUTH_PASSWORD, server_default=AUTH_PASSWORD
    )
    # Last time the person proved who they are in this session (login, or a fresh OIDC
    # confirmation); accounts without a password confirm sensitive changes this way.
    # None = sessions from before 0.11; created_at counts instead
    authenticated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class OidcIdentity(Base):
    """Link between an account and the provider's subject. Never matched by e-mail address."""

    __tablename__ = "oidc_identities"
    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_oidc_identities_issuer_subject"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # Only shown to tell the link apart; refreshed on every login
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="oidc_identity")

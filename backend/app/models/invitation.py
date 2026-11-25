from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

PURPOSE_SIGNUP = "signup"
PURPOSE_PASSWORD_RESET = "password_reset"
# Confirms an e-mail address of an existing account (target_user_id, email)
PURPOSE_VERIFY_EMAIL = "verify_email"
# Open registration with e-mail: the account is created when the address is confirmed
PURPOSE_REGISTRATION = "registration"


class Invitation(Base):
    """One-time link outside of groups: create an account, set a new password, confirm an
    e-mail address, or finish an open registration.

    Invitations into a group are a separate thing (Invite). Only the SHA-256 hash of
    the token is stored; the link is shown or sent once.
    """

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    purpose: Mapped[str] = mapped_column(String(16), nullable=False)
    # signup: role of the new account
    role: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # password_reset: the account whose password is set
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    note: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # signup: address the link was sent to · verify_email, registration: the address to confirm
    email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    # registration: the account that is created on confirmation
    username: Mapped[str | None] = mapped_column(String(80), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(5), nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    used_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
